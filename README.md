# homelab-monitoring

Infrastructure and observability scripts for the homelab.

This repository includes the Discord monitoring panel, Grafana alert receiver, Prometheus-based reports, Speedtest Pushgateway exporter script, Unbound log report, weekly report, anomaly detector, and the public dashboard iframe page.

## Runtime State

Production state is intentionally not tracked:

- message ID files
- history JSON files
- logs
- real env files
- Grafana/Prometheus/Uptime Kuma databases and generated state

## Production Notes

Current production still runs from `/usr/local/bin`, `/home/daniel/network-monitor`, cron, and systemd. This repo is not wired into production yet.

