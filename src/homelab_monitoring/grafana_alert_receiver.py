#!/usr/bin/env python3

import os
import threading
from datetime import datetime
from flask import Flask, request, jsonify

from .homelab_lib import (
    call_ollama,
    load_history,
    query_prometheus,
    webhook_send_or_edit,
)

app = Flask(__name__)

ALERT_WEBHOOK = os.environ.get("ALERT_WEBHOOK", "")
ALERT_MSG_FILE = os.environ.get("ALERT_MSG_FILE", "./data/alert-message-id.txt")


def get_context_metrics():
    queries = {
        "Latencia IPv4": 'avg(probe_icmp_duration_seconds{job="blackbox_icmp",phase="rtt"})*1000',
        "Jitter":        'avg(stddev_over_time((probe_icmp_duration_seconds{job="blackbox_icmp",phase="rtt"}*1000)[5m:]))',
        "Perda Pacotes": 'avg(sum_over_time((1-probe_success{job="blackbox_icmp"})[5m:10s])/count_over_time(probe_success{job="blackbox_icmp"}[5m:10s]))*100',
        "DNS Response":  'avg(probe_dns_duration_seconds{job="blackbox_dns",phase="request"})*1000',
        "Cache Hit":     'sum(rate(unbound_cache_hits_total[5m]))/(sum(rate(unbound_cache_hits_total[5m]))+sum(rate(unbound_cache_misses_total[5m])))*100',
        "MikroTik Temp": 'mktxp_system_cpu_temperature{routerboard_name="RouterCasa"}',
        "MikroTik CPU":  'mktxp_system_cpu_load{routerboard_name="RouterCasa"}',
    }
    lines = []
    for label, query in queries.items():
        val = query_prometheus(query)
        lines.append("- {}: {:.2f}".format(label, val) if val is not None else "- {}: N/A".format(label))
    return "\n".join(lines)


def get_historical_context():
    history = load_history()
    if len(history) < 2:
        return "Sem historico."
    last = history[-1]["metrics"]
    prev = history[-2]["metrics"]
    lines = []
    for key in last:
        if key in prev and last[key] is not None and prev[key] is not None:
            diff = last[key] - prev[key]
            if abs(diff) > 1:
                lines.append("- {}: {} {:.1f} vs ontem".format(key, "subiu" if diff > 0 else "caiu", abs(diff)))
    return "\n".join(lines) if lines else "Estaveis vs ontem."


def send_discord(analysis, alert_name, state, severity):
    now_str = datetime.now().strftime("%d/%m/%Y as %H:%M")
    if state in ["alerting", "firing"]:
        color, icon = 0xef4444, "🔴"
    elif state in ["ok", "resolved", "normal"]:
        color, icon = 0x10b981, "✅"
    else:
        color, icon = 0xf59e0b, "⚠️"

    payload = {
        "embeds": [{
            "title": "{} {}".format(icon, alert_name),
            "description": analysis,
            "color": color,
            "footer": {"text": "{} • {} • {}".format(now_str, state.upper(), severity.upper())}
        }]
    }
    webhook_send_or_edit(payload, ALERT_MSG_FILE, ALERT_WEBHOOK)


def process_alert(data):
    try:
        for alert in data.get("alerts", []):
            alert_name  = alert.get("labels", {}).get("alertname", "Alerta")
            state       = alert.get("status", "unknown")
            severity    = alert.get("labels", {}).get("severity", "unknown")
            summary     = alert.get("annotations", {}).get("summary", "")
            value       = alert.get("values", {})

            prompt = """Analise este alerta do homelab de Daniel (Pato Branco PR) em 2 frases curtas apenas:
Alerta: {alert_name} | Estado: {state} | {summary} | Valor: {value}
Metricas agora: {metricas}
Historico: {historico}
Responda: 1) O que e e gravidade. 2) Agir agora ou ignorar. Sem titulos. Maximo 2 frases.""".format(
                alert_name=alert_name, state=state, summary=summary,
                value=value, metricas=get_context_metrics(), historico=get_historical_context()
            )

            print("Analisando: {}".format(alert_name))
            analysis = call_ollama(prompt, temperature=0.4, num_predict=80)
            send_discord(analysis, alert_name, state, severity)
    except Exception as e:
        print("Erro: {}".format(e))


@app.route("/alert", methods=["POST"])
def receive_alert():
    try:
        data = request.get_json(force=True)
        threading.Thread(target=process_alert, args=(data,), daemon=True).start()
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    print("Grafana Alert Receiver na porta 9999...")
    app.run(host="0.0.0.0", port=9999, debug=False)
