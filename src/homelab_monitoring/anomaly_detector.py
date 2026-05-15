#!/usr/bin/env python3
# =============================================================
# Anomaly Detector
# Compara metricas atuais com historico e detecta anomalias
# =============================================================

import math
import os
import sys
from datetime import datetime

from .homelab_lib import (
    OLLAMA_MODEL as DEFAULT_OLLAMA_MODEL,
    call_ollama,
    load_history,
    query_prometheus,
    webhook_send_or_edit,
)

MESSAGE_FILE    = os.environ.get("ANOMALY_MESSAGE_FILE", "./data/anomaly-message-id.txt")
OLLAMA_MODEL    = os.environ.get("ANOMALY_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
THRESHOLD_SIGMA = 2.0

METRICS_QUERIES = {
    "Latencia IPv4":  'avg(probe_icmp_duration_seconds{job="blackbox_icmp",phase="rtt"})*1000',
    "Latencia IPv6":  'avg(probe_icmp_duration_seconds{job="blackbox_icmp_v6",phase="rtt"})*1000',
    "Jitter":         'avg(stddev_over_time((probe_icmp_duration_seconds{job="blackbox_icmp",phase="rtt"}*1000)[5m:]))',
    "Perda Pacotes":  'avg(sum_over_time((1-probe_success{job="blackbox_icmp"})[5m:10s])/count_over_time(probe_success{job="blackbox_icmp"}[5m:10s]))*100',
    "DNS Response":   'avg(probe_dns_duration_seconds{job="blackbox_dns",phase="request"})*1000',
    "Cache Hit":      'sum(rate(unbound_cache_hits_total[5m]))/(sum(rate(unbound_cache_hits_total[5m]))+sum(rate(unbound_cache_misses_total[5m])))*100',
    "Recursao avg":   'unbound_recursion_time_seconds_avg*1000',
    "MikroTik Temp":  'mktxp_system_cpu_temperature{routerboard_name="RouterCasa"}',
    "MikroTik CPU":   'mktxp_system_cpu_load{routerboard_name="RouterCasa"}',
}

INVERTED_METRICS = {"Cache Hit"}


def calcular_stats(valores):
    if not valores:
        return None, None
    n    = len(valores)
    mean = sum(valores) / n
    if n < 2:
        return mean, 0
    variance = sum((x - mean) ** 2 for x in valores) / (n - 1)
    return mean, math.sqrt(variance)


def detectar_anomalias(current_metrics, history):
    if len(history) < 3:
        return []

    anomalias = []
    for label in current_metrics:
        valor_atual = current_metrics[label]
        if valor_atual is None:
            continue

        historicos = [
            entry.get("metrics", {}).get(label)
            for entry in history[-14:]
            if entry.get("metrics", {}).get(label) is not None
        ]
        if len(historicos) < 3:
            continue

        mean, std = calcular_stats(historicos)
        if std is None or std == 0:
            continue

        sigma = abs(valor_atual - mean) / std
        if label in INVERTED_METRICS:
            e_anomalia = (valor_atual < mean) and (sigma >= THRESHOLD_SIGMA)
        else:
            e_anomalia = (valor_atual > mean) and (sigma >= THRESHOLD_SIGMA)

        if e_anomalia:
            anomalias.append({
                "label": label, "atual": valor_atual,
                "media": mean, "std": std, "sigma": sigma,
            })

    return anomalias


def build_prompt(anomalias):
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    linhas = [
        "- {}: atual={:.2f}, media_historica={:.2f}, desvio={:.2f}, sigma={:.1f}x".format(
            a["label"], a["atual"], a["media"], a["std"], a["sigma"]
        )
        for a in anomalias
    ]
    return """Especialista em redes analisando anomalias detectadas no homelab de Daniel em Pato Branco PR.

DATA: {}

ANOMALIAS DETECTADAS (valores fora do padrao historico):
{}

CONTEXTO:
- Roteador: MikroTik
- DNS: AdGuard Home + Unbound recursivo com DNSSEC
- ISP: fibra optica

Analise as anomalias em 3 linhas curtas:
1. O que esta fora do normal e o quanto (ex: latencia 3x acima da media)
2. Causa provavel
3. Agir agora, monitorar ou ignorar

Sem titulos. Direto ao ponto. Formate para Discord com **negrito** no essencial.""".format(
        now, "\n".join(linhas)
    )


def send_discord(analysis, anomalias):
    now_str  = datetime.now().strftime("%d/%m/%Y as %H:%M")
    max_sigma = max(a["sigma"] for a in anomalias)
    if max_sigma >= 3.0:
        color, icon, severity = 0xef4444, "🔴", "CRITICO"
    else:
        color, icon, severity = 0xf59e0b, "⚠️", "ATENCAO"

    resumo = "\n".join([
        "{} **{}**: `{:.1f}` vs media `{:.1f}` ({:.1f}σ)".format(
            "📈" if a["label"] not in INVERTED_METRICS else "📉",
            a["label"], a["atual"], a["media"], a["sigma"]
        )
        for a in anomalias
    ])

    payload = {
        "embeds": [{
            "title": "{} Anomalia Detectada — {}".format(icon, severity),
            "description": "{}\n\n{}".format(resumo, analysis),
            "color": color,
            "footer": {"text": "{} • Detector de Anomalias • {}".format(now_str, OLLAMA_MODEL)}
        }]
    }
    webhook_send_or_edit(payload, MESSAGE_FILE)


def main():
    print("=" * 50)
    print("Anomaly Detector — {}".format(datetime.now().strftime("%d/%m/%Y %H:%M")))
    print("=" * 50)

    history = load_history()
    print("Historico: {} entradas".format(len(history)))

    if len(history) < 3:
        print("Historico insuficiente — precisa de pelo menos 3 dias.")
        return

    print("Coletando metricas atuais...")
    current = {}
    for label, query in METRICS_QUERIES.items():
        val = query_prometheus(query)
        current[label] = val
        print("  {}: {}".format(label, "{:.2f}".format(val) if val is not None else "N/A"))

    print("Analisando anomalias...")
    anomalias = detectar_anomalias(current, history)

    if not anomalias:
        print("Nenhuma anomalia detectada. Tudo dentro do padrao historico.")
        return

    print("\n{} anomalia(s) detectada(s):".format(len(anomalias)))
    for a in anomalias:
        print("  ⚠️ {}: atual={:.2f}, media={:.2f}, sigma={:.1f}x".format(
            a["label"], a["atual"], a["media"], a["sigma"]
        ))

    print("\nGerando analise com Ollama ({})...".format(OLLAMA_MODEL))
    analysis = call_ollama(build_prompt(anomalias), model=OLLAMA_MODEL, temperature=0.5, num_predict=200)

    print("\nAnalise:")
    print("-" * 40)
    print(analysis)
    print("-" * 40)

    send_discord(analysis, anomalias)
    print("Concluido!")


if __name__ == "__main__":
    main()
