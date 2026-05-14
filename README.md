# homelab-monitoring

Infrastructure and observability scripts for the homelab.

This repository includes the Discord monitoring panel, Grafana alert receiver, Prometheus-based reports, Speedtest Pushgateway exporter script, Unbound log report, weekly report, anomaly detector, and the public dashboard iframe page.

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
| `DISCORD_WEBHOOK` | For reports | Discord webhook used by monitoring reports. |
| `ALERT_WEBHOOK` | For alert receiver | Discord webhook used by Grafana alert forwarding. |
| `ALERT_MSG_FILE` | No | Local file that stores the alert message ID. |
| `PROMETHEUS_BASE` | No | Prometheus base URL used by shared helpers. |
| `PROMETHEUS_URL` | No | Prometheus query endpoint used by the unified panel. |
| `PUBLIC_DASHBOARD_URL` | No | Public dashboard URL shown in Discord output. |
| `OLLAMA_URL` | No | Ollama endpoint for optional generated summaries. |
| `OLLAMA_MODEL` | No | Default Ollama model for reports. |
| `ANOMALY_OLLAMA_MODEL` | No | Ollama model used by the anomaly detector. |
| `KUMA_URL` | No | Uptime Kuma URL used by the unified panel. |
| `KUMA_USER` | No | Uptime Kuma username. |
| `KUMA_PASS` | No | Uptime Kuma password. |
| `HISTORY_FILE` | No | Local monitor history JSON path. |
| `MONITOR_MESSAGE_FILE` | No | Local message ID file for the network monitor. |
| `UNIFIED_MESSAGE_ID_FILE` | No | Local message ID file for the unified panel. |
| `UNBOUND_LOG_MESSAGE_FILE` | No | Local message ID file for the Unbound report. |
| `WEEKLY_MESSAGE_FILE` | No | Local message ID file for the weekly report. |
| `ANOMALY_MESSAGE_FILE` | No | Local message ID file for anomaly reports. |

## Runtime State

Production state is intentionally not tracked:

- message ID files
- history JSON files
- logs
- real env files
- Grafana/Prometheus/Uptime Kuma databases and generated state

## Validation

These checks compile Python files and verify package discovery without running the scripts, starting the Flask receiver, or posting to Discord:

```bash
python -m compileall src
PYTHONPATH=src python -c "import importlib.util; assert importlib.util.find_spec('homelab_monitoring.grafana_alert_receiver')"
```

## Production Notes

Current production still runs from `/usr/local/bin`, `/home/daniel/network-monitor`, cron, and systemd. This repo is not wired into production yet.

The files under `cron/` and `systemd/` are examples only. Do not copy them into production, edit real cron entries, or reload services without an explicit deployment step.

## Security Notes

Do not commit real secrets or runtime state. Keep `.env`, logs, databases, histories, generated caches, message ID files, and local monitoring state out of Git.
