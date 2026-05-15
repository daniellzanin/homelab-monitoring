# homelab-monitoring

Infrastructure and observability scripts for the homelab.

## Architecture

All output flows through a single Discord panel (`discord_unified.py`). The other scripts are background workers that write state files — they have no Discord output of their own.

```
discord_unified.py  (*/3 min)  — único painel Discord, lê Prometheus + state files
monitor.py          (2×/dia)   — coleta snapshot, salva history.json + state file
anomaly_detector.py (*/4h)     — detecção estatística (σ), salva state file
unbound_log_report  (7h diário)— analisa logs DNS, salva state file (condicional)
weekly_report.py    (domingo)  — relatório semanal, mensagem Discord própria + state file
grafana_alert_receiver.py      — Flask :9999, recebe alertas Grafana, salva state file
speedtest-prometheus.sh        — push Pushgateway → Prometheus (sem Discord)
```

## Configuration

Copy the example environment file and fill in local values:

```bash
cp .env.example .env
```

Variables used by the scripts:

| Variable | Required | Description |
|---|---:|---|
| `DISCORD_BOT_TOKEN` | For bot panel | Discord bot token used by the unified Discord panel. |
| `DISCORD_CHANNEL_ID` | For bot panel | Discord channel used by the unified panel. |
| `DISCORD_WEBHOOK` | For weekly report | Discord webhook used by the weekly report. |
| `PROMETHEUS_BASE` | No | Prometheus base URL (default: `http://localhost:9090`). |
| `PUBLIC_DASHBOARD_URL` | No | Public dashboard URL shown in Discord output. |
| `OLLAMA_URL` | No | Ollama endpoint for generated summaries. |
| `OLLAMA_MODEL` | No | Default Ollama model for reports. |
| `ANOMALY_OLLAMA_MODEL` | No | Ollama model used by the anomaly detector. |
| `KUMA_URL` | No | Uptime Kuma URL used by the unified panel. |
| `KUMA_USER` | No | Uptime Kuma username. |
| `KUMA_PASS` | No | Uptime Kuma password. |
| `HISTORY_FILE` | No | Monitor history JSON path. |
| `UNIFIED_MESSAGE_ID_FILE` | No | Message ID file for the unified panel. |
| `WEEKLY_MESSAGE_FILE` | No | Message ID file for the weekly report. |
| `DAILY_STATE_FILE` | No | State file written by `monitor.py`. |
| `ANOMALY_STATE_FILE` | No | State file written by `anomaly_detector.py`. |
| `UNBOUND_STATE_FILE` | No | State file written by `unbound_log_report.py`. |
| `WEEKLY_STATE_FILE` | No | State file written by `weekly_report.py`. |
| `GRAFANA_STATE_FILE` | No | State file written by `grafana_alert_receiver.py`. |

## Runtime State

Production state is intentionally not tracked:

- `data/state/` — state files written by background workers
- `data/history.json` — rolling 30-day metric history
- message ID files, logs, real env files

## Validation

```bash
python -m compileall src
PYTHONPATH=src python -c "import importlib.util; assert importlib.util.find_spec('homelab_monitoring.grafana_alert_receiver')"
```

## Production Notes

Current production still runs from `/usr/local/bin`, `/home/daniel/network-monitor`, cron, and systemd. This repo is not wired into production yet.

The files under `cron/` and `systemd/` are examples only. Do not copy them into production, edit real cron entries, or reload services without an explicit deployment step.

See `docs/deployment-plan.md` for the full migration strategy.

## Security Notes

Do not commit real secrets or runtime state. Keep `.env`, logs, databases, histories, generated caches, message ID files, and local monitoring state out of Git.
