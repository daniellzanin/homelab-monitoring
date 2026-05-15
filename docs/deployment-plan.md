# Deployment Plan: homelab-monitoring

This is a controlled migration plan only. Do not execute it without an explicit deployment window.

Observed date: 2026-05-14 UTC.

## Current Production State

Production currently uses a mix of legacy paths:

- `/usr/local/bin/homelab-discord-unified.py`
- `/usr/local/bin/homelab_lib.py`
- `/usr/local/bin/anomaly-detector.py`
- `/usr/local/bin/unbound-log-report.py`
- `/usr/local/bin/weekly-report.py`
- `/usr/local/bin/speedtest-prometheus.sh`
- `/usr/local/bin/grafana-alert-receiver.py`
- `/home/daniel/network-monitor/monitor.py`

Backup or dead legacy files were also observed in `/usr/local/bin`, including `.bak` and `_dead_*` files. Do not migrate those as active workloads without a separate review.

Observed state and history files:

- `/home/daniel/network-monitor/history.json`
- `/home/daniel/network-monitor/discord_message_id.txt`
- `/home/daniel/network-monitor/monitor.log`
- `/var/lib/homelab-bot/unified_message_id.txt`

Observed logs:

- `/var/log/anomaly-detector.log`
- `/var/log/homelab-discord-unified.log`
- `/var/log/homelab-discord.log`
- `/var/log/uptime-discord.log`
- `/var/log/weekly-report.log`
- `/var/log/speedtest-discord.log`
- `/var/log/speedtest.log`
- `/var/log/unbound-log-report.log`

The active systemd unit observed for this repo is:

- Unit: `/etc/systemd/system/grafana-alert-receiver.service`
- Current command: `/usr/bin/python3 /usr/local/bin/grafana-alert-receiver.py`
- Service state observed: enabled and running
- User: `root`

The Grafana alert receiver should be treated carefully because it listens on port `9999`.

No custom jobs were observed in the current user's crontab, and no matching custom cron file was observed in `/etc/cron.d` during the read-only scan. Before migration, verify root's crontab and any external scheduler:

```bash
sudo crontab -l
sudo rg -n "homelab|network-monitor|discord|unbound|weekly|anomaly|speedtest|grafana-alert" /etc/cron* /etc/systemd/system
```

Environment variables required by the versioned repo:

- `DISCORD_BOT_TOKEN`
- `DISCORD_CHANNEL_ID`
- `DISCORD_WEBHOOK`
- `ALERT_WEBHOOK`
- `ALERT_MSG_FILE`
- `MONITOR_MESSAGE_FILE`
- `UNIFIED_MESSAGE_ID_FILE`
- `UNBOUND_LOG_MESSAGE_FILE`
- `WEEKLY_MESSAGE_FILE`
- `ANOMALY_MESSAGE_FILE`
- `HISTORY_FILE`
- `PROMETHEUS_BASE`
- `PROMETHEUS_URL`
- `PUBLIC_DASHBOARD_URL`
- `OLLAMA_URL`
- `OLLAMA_MODEL`
- `ANOMALY_OLLAMA_MODEL`
- `KUMA_URL`
- `KUMA_USER`
- `KUMA_PASS`

## Recommended Migration Strategy

Use a new definitive path and keep production state outside Git:

- Repo path: `/opt/homelab-monitoring`
- Real env file: `/etc/homelab-monitoring.env`
- State directory: `/var/lib/homelab-monitoring`
- Optional venv: `/opt/homelab-monitoring/.venv`

Preserve current state before changing any scheduler:

- Copy `/home/daniel/network-monitor/history.json`.
- Copy `/home/daniel/network-monitor/discord_message_id.txt`.
- Preserve `/var/lib/homelab-bot/unified_message_id.txt` or deliberately move it to `/var/lib/homelab-monitoring/unified_message_id.txt`.
- Keep all old scripts in `/usr/local/bin` and `/home/daniel/network-monitor` untouched for rollback.

Recommended state layout:

- `/var/lib/homelab-monitoring/history.json`
- `/var/lib/homelab-monitoring/discord_message_id.txt`
- `/var/lib/homelab-monitoring/unified_message_id.txt`
- `/var/lib/homelab-monitoring/unbound-log-message-id.txt`
- `/var/lib/homelab-monitoring/weekly-message-id.txt`
- `/var/lib/homelab-monitoring/anomaly-message-id.txt`
- `/var/lib/homelab-monitoring/alert-message-id.txt`

Recommended service/cron model:

- Use `WorkingDirectory=/opt/homelab-monitoring`.
- Use `EnvironmentFile=/etc/homelab-monitoring.env`.
- Use `PYTHONPATH=/opt/homelab-monitoring/src` for Python module execution.
- Keep the Grafana alert receiver as a systemd service.
- Move recurring report scripts one at a time, starting with the least critical.

Do not run old and new monitoring jobs at the same time. Duplicate runs can edit the same Discord message, post duplicate reports, or duplicate alerts.

## Safe Execution Order

Proposed future commands, not executed:

```bash
sudo install -d -o root -g root /opt/homelab-monitoring
sudo install -d -o root -g root /var/lib/homelab-monitoring
sudo rsync -a --delete /home/daniel/repos/homelab-monitoring/ /opt/homelab-monitoring/
sudo cp -a /home/daniel/network-monitor/history.json /var/lib/homelab-monitoring/history.json
sudo cp -a /home/daniel/network-monitor/discord_message_id.txt /var/lib/homelab-monitoring/discord_message_id.txt
sudo cp -a /var/lib/homelab-bot/unified_message_id.txt /var/lib/homelab-monitoring/unified_message_id.txt
```

Create and populate the virtualenv:

```bash
cd /opt/homelab-monitoring
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Create `/etc/homelab-monitoring.env`:

```bash
DISCORD_BOT_TOKEN=...
DISCORD_CHANNEL_ID=...
DISCORD_WEBHOOK=...
ALERT_WEBHOOK=...
ALERT_MSG_FILE=/var/lib/homelab-monitoring/alert-message-id.txt
MONITOR_MESSAGE_FILE=/var/lib/homelab-monitoring/discord_message_id.txt
UNIFIED_MESSAGE_ID_FILE=/var/lib/homelab-monitoring/unified_message_id.txt
UNBOUND_LOG_MESSAGE_FILE=/var/lib/homelab-monitoring/unbound-log-message-id.txt
WEEKLY_MESSAGE_FILE=/var/lib/homelab-monitoring/weekly-message-id.txt
ANOMALY_MESSAGE_FILE=/var/lib/homelab-monitoring/anomaly-message-id.txt
HISTORY_FILE=/var/lib/homelab-monitoring/history.json
PROMETHEUS_BASE=http://localhost:9090
PROMETHEUS_URL=http://localhost:9090/api/v1/query
PUBLIC_DASHBOARD_URL=...
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
ANOMALY_OLLAMA_MODEL=qwen2.5:3b
KUMA_URL=http://localhost:3001
KUMA_USER=...
KUMA_PASS=...
```

Protect the env file:

```bash
sudo chown root:root /etc/homelab-monitoring.env
sudo chmod 600 /etc/homelab-monitoring.env
```

Pre-switch validation:

```bash
cd /opt/homelab-monitoring
.venv/bin/python -m compileall src
PYTHONPATH=/opt/homelab-monitoring/src .venv/bin/python -c "import importlib.util; assert importlib.util.find_spec('homelab_monitoring.grafana_alert_receiver')"
PYTHONPATH=/opt/homelab-monitoring/src .venv/bin/python -c "import importlib.util; assert importlib.util.find_spec('homelab_monitoring.monitor')"
```

Suggested migration order:

1. Migrate non-alerting scheduled reports first, one at a time.
2. Migrate `monitor.py` after `history.json` and `discord_message_id.txt` are confirmed.
3. Migrate `homelab-discord-unified.py` only after preserving `unified_message_id.txt`.
4. Migrate `speedtest-prometheus.sh` after confirming Pushgateway labels and log path.
5. Migrate `grafana-alert-receiver.py` last, because it is a live receiver on port `9999`.

Example future cron command shape:

```cron
0 9 * * 0 cd /opt/homelab-monitoring && PYTHONPATH=/opt/homelab-monitoring/src /opt/homelab-monitoring/.venv/bin/python -m homelab_monitoring.weekly_report >> /var/log/weekly-report.log 2>&1
```

Example future alert receiver service shape:

```ini
[Service]
Type=simple
User=root
EnvironmentFile=/etc/homelab-monitoring.env
Environment="PYTHONPATH=/opt/homelab-monitoring/src"
WorkingDirectory=/opt/homelab-monitoring
ExecStart=/opt/homelab-monitoring/.venv/bin/python -m homelab_monitoring.grafana_alert_receiver
Restart=always
RestartSec=10
```

Checkpoint after each migrated job:

- Only one scheduler path exists for that job.
- No duplicate Discord message/report appears.
- The expected message ID file is reused.
- Logs continue at the expected path.
- No import errors occur.
- State files remain outside Git.

Special checkpoint for Grafana alert receiver:

```bash
sudo ss -ltnp | grep ':9999'
sudo systemctl status grafana-alert-receiver.service --no-pager
journalctl -u grafana-alert-receiver.service -n 100 --no-pager
```

Rollback:

- Restore the previous cron line for the migrated job.
- Restore the previous systemd unit for `grafana-alert-receiver.service`.
- Run `sudo systemctl daemon-reload` only after restoring a service unit.
- Restart only the affected service during a maintenance window.
- Keep old scripts and old state files until every migrated job has run successfully at least once.

## Risks

- Tokens and webhooks must live in `/etc/homelab-monitoring.env`, never in Git.
- Duplicate scheduled jobs can post duplicate Discord reports.
- Duplicate alert receivers can conflict on port `9999` or double-send alerts.
- Message ID files must be preserved to avoid creating new fixed Discord messages.
- `history.json` must be preserved for continuity of reports and anomaly detection.
- Absolute paths in old scripts may not match the repo layout.
- `src/` layout requires `PYTHONPATH=/opt/homelab-monitoring/src` unless the package is installed.
- Root/user permissions must allow reads of env/state and writes to message ID/history files.
- Uptime Kuma, Prometheus, Ollama, and Grafana endpoints must be validated without sending Discord output.

## Product-Specific Plan

This repo should migrate last because it has multiple independent scripts, shared state, webhooks, fixed Discord messages, and a live Flask receiver on port `9999`.

Recommended low-risk path:

1. Inventory all real cron entries, including root's crontab.
2. Prepare `/opt/homelab-monitoring`, venv, `/etc/homelab-monitoring.env`, and `/var/lib/homelab-monitoring`.
3. Copy `history.json`, `discord_message_id.txt`, and `unified_message_id.txt`.
4. Validate compile/import only.
5. Migrate one scheduled report at a time, starting with the least critical.
6. Observe one full scheduled run per migrated script.
7. Migrate the unified Discord panel after message ID preservation is confirmed.
8. Migrate `grafana-alert-receiver.service` last and verify port `9999`.
9. Roll back individual jobs or service units if any duplicate alert/report appears.
