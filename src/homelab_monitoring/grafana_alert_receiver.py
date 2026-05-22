#!/usr/bin/env python3

import os
import threading
from datetime import datetime
from flask import Flask, request, jsonify

from .homelab_lib import (
    Q_CACHE_HIT,
    Q_DNS_RESP,
    Q_JITTER,
    Q_LAT_IPV4,
    Q_PERDA,
    Q_RB_CPU,
    Q_RB_TEMP,
    SYSTEM_CONTEXT,
    call_ollama,
    load_history,
    query_prometheus,
    read_state,
    write_state,
)

app = Flask(__name__)

GRAFANA_STATE_FILE = os.environ.get("GRAFANA_STATE_FILE", "./data/state/grafana_alerts.json")

# Lock para evitar race condition quando múltiplos alertas chegam ao mesmo tempo
_alert_lock = threading.Lock()


def get_context_metrics():
    queries = {
        "Latencia IPv4": Q_LAT_IPV4,
        "Jitter":        Q_JITTER,
        "Perda Pacotes": Q_PERDA,
        "DNS Response":  Q_DNS_RESP,
        "Cache Hit":     Q_CACHE_HIT,
        "MikroTik Temp": Q_RB_TEMP,
        "MikroTik CPU":  Q_RB_CPU,
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


def process_alert(data):
    with _alert_lock:
        try:
            state_data = read_state(GRAFANA_STATE_FILE)
            active_alerts = state_data.get("active_alerts", [])

            for alert in data.get("alerts", []):
                alert_name = alert.get("labels", {}).get("alertname", "Alerta")
                state      = alert.get("status", "unknown")
                severity   = alert.get("labels", {}).get("severity", "unknown")
                summary    = alert.get("annotations", {}).get("summary", "")
                value      = alert.get("values", {})

                if state in ("resolved", "ok", "normal"):
                    active_alerts = [a for a in active_alerts if a.get("name") != alert_name]
                    print("Alerta '{}' resolvido — removido da lista.".format(alert_name))
                else:
                    prompt = """Analise este alerta do homelab de Daniel (Pato Branco PR) em 2 frases curtas apenas:
Alerta: {alert_name} | Estado: {state} | {summary} | Valor: {value}
Metricas agora: {metricas}
Historico: {historico}

CONTEXTO:
{contexto}

Responda: 1) O que e e gravidade. 2) Agir agora ou ignorar. Sem titulos. Maximo 2 frases.""".format(
                        alert_name=alert_name, state=state, summary=summary,
                        value=value, metricas=get_context_metrics(),
                        historico=get_historical_context(), contexto=SYSTEM_CONTEXT,
                    )

                    print("Analisando: {}".format(alert_name))
                    analysis = call_ollama(prompt, temperature=0.4, num_predict=80)
                    active_alerts = [a for a in active_alerts if a.get("name") != alert_name]
                    active_alerts.append({
                        "name": alert_name,
                        "severity": severity,
                        "state": state,
                        "analysis": analysis,
                    })

            write_state(GRAFANA_STATE_FILE, {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "active_alerts": active_alerts,
            })
            print("  State file escrito: {}".format(GRAFANA_STATE_FILE))
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
