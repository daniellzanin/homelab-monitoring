#!/usr/bin/env python3
# =============================================================
# Anomaly Detector
# Compara metricas atuais com historico e detecta anomalias
# =============================================================

import math
import os
from datetime import datetime

from .homelab_lib import (
    OLLAMA_MODEL as DEFAULT_OLLAMA_MODEL,
    Q_CACHE_HIT,
    Q_DNS_RESP,
    Q_JITTER,
    Q_LAT_IPV4,
    Q_LAT_IPV6,
    Q_PERDA,
    Q_RB_CPU,
    Q_RB_TEMP,
    Q_RECURSAO,
    Q_UPTIME_24H,
    SYSTEM_CONTEXT,
    call_ollama,
    load_history,
    query_prometheus,
    write_state,
)

OLLAMA_MODEL       = os.environ.get("ANOMALY_OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
ANOMALY_STATE_FILE = os.environ.get("ANOMALY_STATE_FILE", "./data/state/anomaly_state.json")
THRESHOLD_SIGMA    = float(os.environ.get("THRESHOLD_SIGMA", "3.0"))

MIN_DELTA = {
    "Latencia IPv4":   10.0,
    "Latencia IPv6":   10.0,
    "Jitter IPv4":      3.0,
    "Perda de Pacotes": 1.0,
    "DNS Response":     5.0,
    "Cache Hit Rate":  10.0,
    "Recursao avg":    20.0,
    "MikroTik Temp":    5.0,
    "MikroTik CPU":    20.0,
    "Uptime 24h":       2.0,
}

METRICS_QUERIES = {
    "Latencia IPv4":    Q_LAT_IPV4,
    "Latencia IPv6":    Q_LAT_IPV6,
    "Jitter IPv4":      Q_JITTER,
    "Perda de Pacotes": Q_PERDA,
    "DNS Response":     Q_DNS_RESP,
    "Cache Hit Rate":   Q_CACHE_HIT,
    "Recursao avg":     Q_RECURSAO,
    "MikroTik Temp":    Q_RB_TEMP,
    "MikroTik CPU":     Q_RB_CPU,
    "Uptime 24h":       Q_UPTIME_24H,
}

# Métricas onde valor abaixo da média é anomalia (ex: cache caindo, uptime caindo)
INVERTED_METRICS = {"Cache Hit Rate", "Uptime 24h"}


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

        if abs(valor_atual - mean) < MIN_DELTA.get(label, 0):
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
{}

Analise as anomalias em 3 linhas curtas:
1. O que esta fora do normal e o quanto (ex: latencia 3x acima da media)
2. Causa provavel
3. Agir agora, monitorar ou ignorar

Sem titulos. Direto ao ponto. Formate para Discord com **negrito** no essencial.""".format(
        now, "\n".join(linhas), SYSTEM_CONTEXT
    )


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
        write_state(ANOMALY_STATE_FILE, {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "has_anomalies": False,
            "anomalies": [],
            "analysis": "",
        })
        print("  State file escrito: {}".format(ANOMALY_STATE_FILE))
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

    write_state(ANOMALY_STATE_FILE, {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "has_anomalies": True,
        "anomalies": [
            {"label": a["label"], "atual": a["atual"], "media": a["media"], "sigma": round(a["sigma"], 2)}
            for a in anomalias
        ],
        "analysis": analysis,
    })
    print("  State file escrito: {}".format(ANOMALY_STATE_FILE))
    print("Concluido!")


if __name__ == "__main__":
    main()
