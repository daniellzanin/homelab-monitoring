#!/usr/bin/env python3
# =============================================================
# Homelab Network Monitor
# Prometheus -> Ollama -> state file
# =============================================================

import json
import os
from datetime import datetime

from .homelab_lib import (
    MAX_HISTORY,
    OLLAMA_MODEL,
    Q_CACHE_HIT,
    Q_DNS_RESP,
    Q_EXCEEDED,
    Q_JITTER,
    Q_LAT_IPV4,
    Q_LAT_IPV6,
    Q_PERDA,
    Q_RB_CONN,
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

# ── Configuração local ────────────────────────────────────────
HISTORY_FILE     = os.environ.get("HISTORY_FILE",       "./data/history.json")
DAILY_STATE_FILE = os.environ.get("DAILY_STATE_FILE",   "./data/state/daily_analysis.json")

# ── Métricas ──────────────────────────────────────────────────
METRICS = [
    {"label": "Latencia IPv4",    "query": Q_LAT_IPV4,   "unit": "ms", "warn": 40,    "crit": 80,    "invert": False},
    {"label": "Latencia IPv6",    "query": Q_LAT_IPV6,   "unit": "ms", "warn": 40,    "crit": 80,    "invert": False},
    {"label": "Jitter IPv4",      "query": Q_JITTER,     "unit": "ms", "warn": 5,     "crit": 15,    "invert": False},
    {"label": "Perda de Pacotes", "query": Q_PERDA,      "unit": "%",  "warn": 0.5,   "crit": 2,     "invert": False},
    {"label": "DNS Response",     "query": Q_DNS_RESP,   "unit": "ms", "warn": 10,    "crit": 50,    "invert": False},
    {"label": "Cache Hit Rate",   "query": Q_CACHE_HIT,  "unit": "%",  "warn": 50,    "crit": 25,    "invert": True},
    {"label": "Recursao avg",     "query": Q_RECURSAO,   "unit": "ms", "warn": 500,   "crit": 800,   "invert": False},
    {"label": "Queries Exceeded", "query": Q_EXCEEDED,   "unit": "/s", "warn": 0.1,   "crit": 1,     "invert": False},
    {"label": "MikroTik Temp",    "query": Q_RB_TEMP,    "unit": "C",  "warn": 60,    "crit": 75,    "invert": False},
    {"label": "MikroTik CPU",     "query": Q_RB_CPU,     "unit": "%",  "warn": 70,    "crit": 90,    "invert": False},
    {"label": "Conexoes Ativas",  "query": Q_RB_CONN,    "unit": "",   "warn": 5000,  "crit": 15000, "invert": False},
    {"label": "Uptime 24h",       "query": Q_UPTIME_24H, "unit": "%",  "warn": 99,    "crit": 95,    "invert": True},
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
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
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
{}

Escreva UM PARAGRAFO CURTO de avaliacao da rede, estilo previsao do tempo. Seja direto e natural, como se estivesse conversando com Daniel. Comece com um emoji de clima indicando o estado geral. Mencione apenas o que for relevante — se tudo estiver normal, diga isso de forma tranquila. Se houver algo fora do padrao, explique brevemente o que e e o que pode ter causado. Nao liste metricas, nao use topicos, nao repita os numeros todos — apenas interprete e converse. Maximo 4 linhas.""".format(
        now, metrics_text, historical_text, SYSTEM_CONTEXT
    )

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

    print("=" * 50)
    print("Concluido!")

if __name__ == "__main__":
    main()
