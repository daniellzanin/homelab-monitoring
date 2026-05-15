#!/usr/bin/env python3
# =============================================================
# Homelab Network Monitor
# Prometheus -> Ollama -> Discord
# =============================================================

import json
import os
import sys
from datetime import datetime

from .homelab_lib import (
    DISCORD_WEBHOOK,
    OLLAMA_MODEL,
    call_ollama,
    load_history,
    query_prometheus,
    webhook_send_or_edit,
    write_state,
)

# ── Configuração local ────────────────────────────────────────
HISTORY_FILE = os.environ.get("HISTORY_FILE", "./data/history.json")
MESSAGE_FILE = os.environ.get("MONITOR_MESSAGE_FILE", "./data/discord_message_id.txt")
DAILY_STATE_FILE = os.environ.get("DAILY_STATE_FILE", "./data/state/daily_analysis.json")

# ── Métricas ──────────────────────────────────────────────────
METRICS = [
    {
        "label": "Latencia IPv4",
        "query": 'avg(probe_icmp_duration_seconds{job="blackbox_icmp",phase="rtt"})*1000',
        "unit": "ms", "warn": 40, "crit": 80, "invert": False
    },
    {
        "label": "Latencia IPv6",
        "query": 'avg(probe_icmp_duration_seconds{job="blackbox_icmp_v6",phase="rtt"})*1000',
        "unit": "ms", "warn": 40, "crit": 80, "invert": False
    },
    {
        "label": "Jitter IPv4",
        "query": 'avg(stddev_over_time((probe_icmp_duration_seconds{job="blackbox_icmp",phase="rtt"}*1000)[5m:]))',
        "unit": "ms", "warn": 5, "crit": 15, "invert": False
    },
    {
        "label": "Perda de Pacotes",
        "query": 'avg(sum_over_time((1-probe_success{job="blackbox_icmp"})[5m:10s])/count_over_time(probe_success{job="blackbox_icmp"}[5m:10s]))*100',
        "unit": "%", "warn": 0.5, "crit": 2, "invert": False
    },
    {
        "label": "DNS Response",
        "query": 'avg(probe_dns_duration_seconds{job="blackbox_dns",phase="request"})*1000',
        "unit": "ms", "warn": 10, "crit": 50, "invert": False
    },
    {
        "label": "Cache Hit Rate",
        "query": 'sum(rate(unbound_cache_hits_total[5m]))/(sum(rate(unbound_cache_hits_total[5m]))+sum(rate(unbound_cache_misses_total[5m])))*100',
        "unit": "%", "warn": 50, "crit": 25, "invert": True
    },
    {
        "label": "Recursao avg",
        "query": "unbound_recursion_time_seconds_avg*1000",
        "unit": "ms", "warn": 500, "crit": 800, "invert": False
    },
    {
        "label": "Queries Exceeded",
        "query": "rate(unbound_request_list_exceeded_total[5m])",
        "unit": "/s", "warn": 0.1, "crit": 1, "invert": False
    },
    {
        "label": "MikroTik Temp",
        "query": 'mktxp_system_cpu_temperature{routerboard_name="RouterCasa"}',
        "unit": "C", "warn": 60, "crit": 75, "invert": False
    },
    {
        "label": "MikroTik CPU",
        "query": 'mktxp_system_cpu_load{routerboard_name="RouterCasa"}',
        "unit": "%", "warn": 70, "crit": 90, "invert": False
    },
    {
        "label": "Conexoes Ativas",
        "query": 'mktxp_ip_connections_total{routerboard_name="RouterCasa"}',
        "unit": "", "warn": 5000, "crit": 15000, "invert": False
    },
    {
        "label": "Uptime 24h",
        "query": 'avg_over_time(probe_success{job="blackbox_icmp",instance="Cloudflare"}[24h])*100',
        "unit": "%", "warn": 99, "crit": 95, "invert": True
    },
]

# ── Funções ───────────────────────────────────────────────────

def classify(value, warn, crit, invert):
    if value is None:
        return "sem dados"
    if invert:
        if value < crit:  return "CRITICO"
        if value < warn:  return "ATENCAO"
        return "OK"
    else:
        if value >= crit: return "CRITICO"
        if value >= warn: return "ATENCAO"
        return "OK"

def embed_color(results):
    statuses = [r["status"] for r in results]
    if "CRITICO" in statuses: return 0xef4444
    if "ATENCAO" in statuses: return 0xf59e0b
    return 0x10b981

def fmt(value, unit, decimals=2):
    if value is None:
        return "N/A"
    return "{:.{}f}{}".format(value, decimals, unit)

def collect_metrics():
    print("Coletando metricas do Prometheus...")
    results = []
    for m in METRICS:
        value  = query_prometheus(m["query"])
        status = classify(value, m["warn"], m["crit"], m["invert"])
        results.append({
            "label":  m["label"],
            "value":  value,
            "unit":   m["unit"],
            "status": status,
            "warn":   m["warn"],
            "crit":   m["crit"],
        })
        icons = {"OK": "OK", "ATENCAO": "ATENCAO", "CRITICO": "CRITICO", "sem dados": "?"}
        print("  [{}] {}: {}".format(icons.get(status, "?"), m["label"], fmt(value, m["unit"])))
    return results

def save_history(results):
    history = load_history(HISTORY_FILE)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "metrics": {r["label"]: r["value"] for r in results}
    }
    history.append(entry)
    if len(history) > 30:
        history = history[-30:]
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)
    return history

def build_prompt(results, history):
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    lines = []
    for r in results:
        lines.append("- {}: {} [{}]".format(
            r["label"], fmt(r["value"], r["unit"]), r["status"]
        ))
    metrics_text = "\n".join(lines)

    historical_text = ""
    if len(history) >= 2:
        yesterday = history[-2]["metrics"]
        comparisons = []
        for r in results:
            label = r["label"]
            if label in yesterday and r["value"] is not None and yesterday[label] is not None:
                diff = r["value"] - yesterday[label]
                if abs(diff) > 0.5:
                    direction = "subiu" if diff > 0 else "caiu"
                    comparisons.append("- {}: {} {:.1f}{} vs ontem".format(
                        label, direction, abs(diff), r["unit"]
                    ))
        if comparisons:
            historical_text = "\nVARIACOES VS ONTEM:\n" + "\n".join(comparisons)

    return """Voce e um especialista em redes analisando o homelab de Daniel em Pato Branco, PR.

DATA: {}

METRICAS:
{}
{}

CONTEXTO:
- Roteador: MikroTik
- DNS: AdGuard Home + Unbound recursivo com DNSSEC
- Servidor: Debian 12 no Proxmox (Xeon E5-2680 v4, 64GB RAM)
- ISP: fibra optica

Escreva UM PARAGRAFO CURTO de avaliacao da rede, estilo previsao do tempo. Seja direto e natural, como se estivesse conversando com Daniel. Comece com um emoji de clima indicando o estado geral. Mencione apenas o que for relevante — se tudo estiver normal, diga isso de forma tranquila. Se houver algo fora do padrao, explique brevemente o que e e o que pode ter causado. Nao liste metricas, nao use topicos, nao repita os numeros todos — apenas interprete e converse. Maximo 4 linhas.""".format(
        now, metrics_text, historical_text
    )

def send_discord(analysis, results):
    print("Enviando para Discord...")

    ok    = sum(1 for r in results if r["status"] == "OK")
    warn  = sum(1 for r in results if r["status"] == "ATENCAO")
    crit  = sum(1 for r in results if r["status"] == "CRITICO")
    total = len(results)

    now_str = datetime.now().strftime("%d/%m/%Y as %H:%M")

    if crit > 0:
        status_line = "⛈️ {} problema(s) critico(s) detectado(s)".format(crit)
    elif warn > 0:
        status_line = "🌥️ {} item(ns) em atencao".format(warn)
    else:
        status_line = "☀️ Tudo dentro do normal ({}/{} OK)".format(ok, total)

    payload = {
        "embeds": [{
            "title": "📡 Analise Diaria — Homelab Pato Branco",
            "description": "{}\n\n{}".format(status_line, analysis),
            "color": embed_color(results),
            "footer": {
                "text": "{} • {} • Homelab Monitor".format(now_str, OLLAMA_MODEL)
            },
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        }]
    }
    webhook_send_or_edit(payload, MESSAGE_FILE, DISCORD_WEBHOOK)

def main():
    print("=" * 50)
    print("Homelab Monitor — {}".format(datetime.now().strftime("%d/%m/%Y %H:%M")))
    print("=" * 50)

    results  = collect_metrics()
    history  = save_history(results)
    prompt   = build_prompt(results, history)
    analysis = call_ollama(prompt, temperature=0.8, num_predict=200)

    print("\nAnalise gerada:")
    print("-" * 40)
    print(analysis)
    print("-" * 40)

    ok   = sum(1 for r in results if r["status"] == "OK")
    warn = sum(1 for r in results if r["status"] == "ATENCAO")
    crit = sum(1 for r in results if r["status"] == "CRITICO")
    overall = "CRITICO" if crit > 0 else ("ATENCAO" if warn > 0 else "OK")
    write_state(DAILY_STATE_FILE, {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "analysis": analysis,
        "status": overall,
        "ok": ok,
        "warn": warn,
        "crit": crit,
    })
    print("  State file escrito: {}".format(DAILY_STATE_FILE))

    send_discord(analysis, results)

    print("=" * 50)
    print("Concluido!")

if __name__ == "__main__":
    main()
