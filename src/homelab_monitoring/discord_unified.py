#!/usr/bin/env python3
"""
homelab-discord-unified.py
"""

import os
import sys
from datetime import datetime, timezone, timedelta

from .homelab_lib import (
    Q_CACHE_HIT,
    ROUTERBOARD_NAME,
    bot_send_or_edit,
    query_prometheus,
    read_state,
    truncate_field,
)

try:
    from uptime_kuma_api import UptimeKumaApi
except ImportError:
    UptimeKumaApi = None


DISCORD_TOKEN        = os.environ.get("DISCORD_BOT_TOKEN", "")
CHANNEL_ID           = os.environ.get("DISCORD_CHANNEL_ID", "")
PUBLIC_DASHBOARD_URL = os.environ.get("PUBLIC_DASHBOARD_URL", "https://mubola.com.br/homelab/index.html")
KUMA_URL = os.environ.get("KUMA_URL", "http://localhost:3001")
KUMA_USER = os.environ.get("KUMA_USER", "kuma")
KUMA_PASS = os.environ.get("KUMA_PASS", "")
MESSAGE_ID_FILE    = os.environ.get("UNIFIED_MESSAGE_ID_FILE", "./data/unified_message_id.txt")
DAILY_STATE_FILE   = os.environ.get("DAILY_STATE_FILE",   "./data/state/daily_analysis.json")
ANOMALY_STATE_FILE = os.environ.get("ANOMALY_STATE_FILE", "./data/state/anomaly_state.json")
UNBOUND_STATE_FILE = os.environ.get("UNBOUND_STATE_FILE", "./data/state/unbound_report.json")
WEEKLY_STATE_FILE  = os.environ.get("WEEKLY_STATE_FILE",  "./data/state/weekly_summary.json")
GRAFANA_STATE_FILE = os.environ.get("GRAFANA_STATE_FILE", "./data/state/grafana_alerts.json")

if not DISCORD_TOKEN:
    print("ERRO: variável de ambiente DISCORD_BOT_TOKEN não definida.")
    sys.exit(1)


def safe_round(v, decimals=1):
    return round(v, decimals) if v is not None else "N/A"


def fmt_mbps(bps):
    if bps is None:
        return "N/A"
    return f"{bps / 1_000_000:.1f} Mbps"


def fmt_ms(v, decimals=1):
    if v is None:
        return "N/A"
    return f"{v:.{decimals}f} ms"



SCORE_QUERY = (
    'clamp('
    '(clamp(100'
    ' - clamp_max(avg(stddev_over_time((probe_icmp_duration_seconds{job="blackbox_icmp",phase="rtt"} * 1000)[5m:])) * 3, 40)'
    ' - clamp_max((1 - avg(probe_success{job="blackbox_icmp"})) * 100, 50)'
    ' - clamp_max((avg(probe_icmp_duration_seconds{job="blackbox_icmp",phase="rtt"}) * 1000 - 15) * 0.5, 10)'
    ', 0, 100)) * 0.5'
    ' + (clamp(100'
    ' - clamp_max((1 - avg(probe_success{job="blackbox_http"})) * 100, 60)'
    ' - clamp_max((avg(probe_duration_seconds{job="blackbox_http"}) * 1000 - 200) * 0.05, 40)'
    ', 0, 100)) * 0.3'
    ' + (clamp(100'
    ' - clamp_max(avg(probe_dns_duration_seconds{job="blackbox_dns",phase="request"}) * 1000 * 5, 60)'
    ' - clamp_max((1 - (sum(rate(unbound_cache_hits_total[5m])) / clamp_min(sum(rate(unbound_cache_hits_total[5m])) + sum(rate(unbound_cache_misses_total[5m])), 0.001))) * 20, 20)'
    ', 0, 100)) * 0.2'
    ', 0, 100)'
)


def get_network_metrics():
    return {
        "score": safe_round(query_prometheus(SCORE_QUERY), 1),
        "uptime": safe_round((query_prometheus('avg_over_time(probe_success{job="blackbox_icmp",instance="Cloudflare"}[24h])') or 0) * 100, 2),
        "latencia": safe_round(query_prometheus('avg(probe_icmp_duration_seconds{job="blackbox_icmp",phase="rtt"}) * 1000'), 2),
        "jitter": safe_round(query_prometheus('avg(stddev_over_time((probe_icmp_duration_seconds{job="blackbox_icmp",phase="rtt"} * 1000)[5m:]))'), 3),
        "dns": safe_round(query_prometheus('probe_dns_duration_seconds{job="blackbox_dns",phase="request"} * 1000'), 3),
        "cache": safe_round(query_prometheus(Q_CACHE_HIT), 1),
        "tcp_discord": safe_round(query_prometheus('avg(probe_duration_seconds{job="blackbox_tcp",instance=~"Discord.*"}) * 1000'), 1),
        "tcp_steam": safe_round(query_prometheus('probe_duration_seconds{job="blackbox_tcp",instance="Steam TCP"} * 1000'), 1),
    }


DIAG_QUERY = '''clamp_max(
  max(
    (1 - min_over_time(probe_success{job="blackbox_icmp",instance="Gateway"}[1m])) * 5
    or
    (avg_over_time(probe_duration_seconds{job="blackbox_icmp_interno"}[2m]) * 1000 > bool 3)
      * (min_over_time(probe_success{job="blackbox_icmp",instance="Gateway"}[2m]) == bool 1) * 4
    or
    ((1 - avg_over_time(probe_success{job="blackbox_icmp"}[3m])) > bool 0.3)
      * (min_over_time(probe_success{job="blackbox_icmp",instance="Gateway"}[3m]) == bool 1)
      * (avg_over_time(probe_duration_seconds{job="blackbox_icmp_interno"}[3m]) * 1000 < bool 3) * 3
    or
    (
      (avg_over_time(probe_duration_seconds{job="blackbox_http"}[3m]) * 1000 > bool 800)
      or
      (avg_over_time(probe_duration_seconds{job="blackbox_tcp"}[3m]) * 1000 > bool 150)
    )
      * (avg_over_time(probe_success{job="blackbox_icmp"}[3m]) >= bool 0.8) * 2
    or
    (
      quantile_over_time(0.95, probe_dns_duration_seconds{job="blackbox_dns",phase="request"}[5m]) * 1000 > bool 30
    )
      * (avg_over_time(probe_success{job="blackbox_icmp"}[2m]) >= bool 0.8) * 1
    or vector(0)
  ), 5)'''

DIAG_MAP = {
    5: ("🚨", "Gateway inacessível — rede interna sem saída"),
    4: ("🔴", "Rede interna — latência alta no lab"),
    3: ("🔴", "ISP/WAN — internet degradada"),
    2: ("🟡", "Serviço externo lento — rede local ok"),
    1: ("🟡", "DNS instável — Unbound acima do normal"),
}


def get_diagnostico():
    val = query_prometheus(DIAG_QUERY)
    if val is not None and int(val) > 0:
        return (*DIAG_MAP[int(val)], int(val))
    return "✅", "Normal", 0


def get_eventos_recentes():
    eventos = []

    http_pico = query_prometheus('max_over_time(avg(probe_duration_seconds{job="blackbox_http"})[30m:1m]) * 1000')
    if http_pico is not None and http_pico > 2000:
        eventos.append(f"📈 HTTP teve pico de `{round(http_pico)}ms`")

    tcp_pico = query_prometheus('max_over_time(avg(probe_duration_seconds{job="blackbox_tcp"})[30m:1m]) * 1000')
    if tcp_pico is not None and tcp_pico > 300:
        eventos.append(f"📈 TCP teve pico de `{round(tcp_pico)}ms`")

    dns_pico = query_prometheus('max_over_time(probe_dns_duration_seconds{job="blackbox_dns",phase="request"}[30m]) * 1000')
    if dns_pico is not None and dns_pico > 150:
        eventos.append(f"🔍 DNS teve pico de `{round(dns_pico, 1)}ms`")

    return eventos


def check_alerts(metrics):
    alerts = []

    loss = query_prometheus('avg_over_time((sum_over_time((1 - probe_success{job="blackbox_icmp"})[5m:10s]) / count_over_time(probe_success{job="blackbox_icmp"}[5m:10s]))[2m:30s])')
    if loss is not None and loss > 0.03:
        alerts.append(f"🔴 Perda de pacotes: `{round(loss * 100, 1)}%`")

    jitter_avg = query_prometheus('avg_over_time(avg(stddev_over_time((probe_icmp_duration_seconds{job="blackbox_icmp",phase="rtt"} * 1000)[5m:]))[3m:30s])')
    if jitter_avg is not None and jitter_avg > 10:
        alerts.append(f"🟡 Jitter alto: `{round(jitter_avg, 1)}ms`")

    lat_avg = query_prometheus('avg_over_time(avg(probe_icmp_duration_seconds{job="blackbox_icmp",phase="rtt"})[3m:30s]) * 1000')
    if lat_avg is not None and lat_avg > 80:
        alerts.append(f"🔴 Latência alta: `{round(lat_avg, 1)}ms`")

    dns_current = metrics.get("dns")
    dns_p95 = query_prometheus('quantile_over_time(0.95, probe_dns_duration_seconds{job="blackbox_dns",phase="request"}[5m]) * 1000')
    if isinstance(dns_current, float) and isinstance(dns_p95, float) and dns_current > 10 and dns_p95 > 30:
        alerts.append(f"🟡 DNS instável: `{round(dns_current, 1)}ms` (p95 {round(dns_p95, 1)}ms)")

    cache = metrics.get("cache")
    cache_samples_15m = query_prometheus('sum(increase(unbound_cache_hits_total[15m])) + sum(increase(unbound_cache_misses_total[15m]))')
    if isinstance(cache, float) and cache < 50 and isinstance(cache_samples_15m, float) and cache_samples_15m > 100:
        alerts.append(f"🟡 Cache DNS baixo: `{cache}%`")

    cpu = query_prometheus(f'avg_over_time(mktxp_system_cpu_load{{routerboard_name="{ROUTERBOARD_NAME}"}}[2m])')
    if cpu is not None and cpu > 70:
        alerts.append(f"🔴 MikroTik CPU: `{round(cpu)}%`")

    temp = query_prometheus(f'avg_over_time(mktxp_system_cpu_temperature{{routerboard_name="{ROUTERBOARD_NAME}"}}[3m])')
    if temp is not None and temp > 70:
        alerts.append(f"🟡 MikroTik temp: `{round(temp)}°C`")

    drops = query_prometheus(f'avg_over_time(sum(rate(mktxp_interface_rx_drop_total{{routerboard_name="{ROUTERBOARD_NAME}"}}[1m]))[2m:30s])')
    if drops is not None and drops > 10:
        alerts.append(f"🔴 Drops MikroTik: `{round(drops)}/s`")

    for job, label in [
        ("blackbox_http", "HTTP"),
        ("blackbox_icmp", "ICMP"),
        ("blackbox_tcp", "TCP"),
    ]:
        down = query_prometheus(f'count(avg_over_time(probe_success{{job="{job}"}}[3m]) < 0.5)')
        if down is not None and down > 0:
            alerts.append(f"🔴 {label} offline: `{int(down)}` item(ns)")

    return alerts


def get_kuma_summary():
    if UptimeKumaApi is None:
        return {"total": 0, "online": 0, "offline": 0, "unknown": 0, "offline_names": ["uptime_kuma_api não instalado"], "avg_ping": None}

    if not KUMA_PASS:
        return {"total": 0, "online": 0, "offline": 0, "unknown": 0, "offline_names": ["KUMA_PASS não definido"], "avg_ping": None}

    api = UptimeKumaApi(KUMA_URL)
    try:
        api.login(KUMA_USER, KUMA_PASS)
        monitors = api.get_monitors()
        heartbeats = api.get_heartbeats()

        online = offline = unknown = 0
        offline_names = []
        pings = []

        for m in monitors:
            hb = heartbeats.get(m["id"], [])
            last = hb[-1] if hb else None
            status = last.get("status") if last else None
            ping = last.get("ping") if last else None

            if status == 1:
                online += 1
            elif status == 0:
                offline += 1
                offline_names.append(m["name"])
            else:
                unknown += 1

            if isinstance(ping, (int, float)):
                pings.append(float(ping))

        return {
            "total": len(monitors),
            "online": online,
            "offline": offline,
            "unknown": unknown,
            "offline_names": offline_names,
            "avg_ping": sum(pings) / len(pings) if pings else None,
        }

    except Exception as e:
        print(f"[WARN] Erro ao consultar Uptime Kuma: {e}")
        return {"total": 0, "online": 0, "offline": 0, "unknown": 0, "offline_names": ["erro ao consultar Kuma"], "avg_ping": None}
    finally:
        api.disconnect()


def get_speedtest_metrics():
    return {
        "dl_last": query_prometheus("speedtest_download_bps"),
        "ul_last": query_prometheus("speedtest_upload_bps"),
        "ping_last": query_prometheus("speedtest_ping_ms"),
        "dl_7d": query_prometheus("avg_over_time(speedtest_download_bps[7d])"),
        "ul_7d": query_prometheus("avg_over_time(speedtest_upload_bps[7d])"),
        "dl_7d_min": query_prometheus("min_over_time(speedtest_download_bps[7d])"),
        "ul_7d_min": query_prometheus("min_over_time(speedtest_upload_bps[7d])"),
    }


def maior_melhor(v, thresholds):
    if not isinstance(v, float):
        return ""
    for limit, label, emoji in thresholds:
        if v >= limit:
            return f" {emoji} ({label})"
    return ""


def menor_melhor(v, thresholds):
    if not isinstance(v, float):
        return ""
    for limit, label, emoji in thresholds:
        if v < limit:
            return f" {emoji} ({label})"
    return ""


def ctx_score(v): return maior_melhor(v, [(95, "excelente", "🟢"), (90, "muito bom", "🟢"), (75, "bom", "🟡"), (60, "ok", "🟠"), (0, "ruim", "🔴")])
def ctx_uptime(v): return maior_melhor(v, [(99.9, "excelente", "🟢"), (99.0, "bom", "🟢"), (95.0, "ok", "🟡"), (0, "ruim", "🔴")])
def ctx_latencia(v): return menor_melhor(v, [(15, "excelente", "🟢"), (30, "ótima", "🟢"), (50, "normal", "🟡"), (80, "alta", "🟠"), (float("inf"), "muito alta", "🔴")])
def ctx_jitter(v): return menor_melhor(v, [(1, "estável", "🟢"), (3, "bom", "🟢"), (8, "ok", "🟡"), (15, "instável", "🟠"), (float("inf"), "muito instável", "🔴")])
def ctx_dns(v): return menor_melhor(v, [(1, "rápido", "🟢"), (5, "bom", "🟢"), (15, "ok", "🟡"), (30, "lento", "🟠"), (float("inf"), "muito lento", "🔴")])
def ctx_cache(v): return maior_melhor(v, [(95, "excelente", "🟢"), (90, "ótimo", "🟢"), (80, "bom", "🟡"), (70, "ok", "🟡"), (50, "baixo", "🟠"), (0, "ruim", "🔴")])
def ctx_tcp(v): return menor_melhor(v, [(30, "ótimo", "🟢"), (60, "bom", "🟢"), (100, "normal", "🟡"), (150, "elevado", "🟠"), (float("inf"), "alto", "🔴")])


def score_emoji(score):
    if not isinstance(score, float): return "❓"
    if score >= 90: return "🟢"
    if score >= 70: return "🟡"
    return "🔴"


def embed_color(score, alerts, kuma):
    if any("🔴" in a for a in alerts) or kuma["offline"] > 0:
        return 0xff4444
    if any("🟡" in a for a in alerts) or kuma["unknown"] > 0:
        return 0xffaa00
    if isinstance(score, float) and score >= 90:
        return 0x00cc66
    if isinstance(score, float) and score >= 70:
        return 0xffaa00
    return 0xff4444


def resumo_humano(metrics, diag_val, eventos, alerts, kuma):
    if kuma["offline"] > 0: return "🔴 Serviço offline detectado no homelab"
    if diag_val == 5: return "🚨 Rede interna sem saída — verificar urgente"
    if diag_val == 4: return "🔴 Problema detectado na rede local"
    if diag_val == 3: return "🔴 Internet degradada — provável problema no provedor"
    if diag_val == 2: return "🟡 Serviços externos lentos — rede local ok"
    if diag_val == 1: return "🟡 DNS instável — pode afetar navegação"
    if alerts: return "🟡 Anomalia ativa em monitoramento"

    lat, jitter = metrics.get("latencia"), metrics.get("jitter")
    tcp_discord, tcp_steam = metrics.get("tcp_discord"), metrics.get("tcp_steam")
    cache = metrics.get("cache")

    if isinstance(cache, float) and cache < 70:
        return "🟡 Cache DNS baixo — sem impacto grave, mas vale observar"

    if all(isinstance(v, float) for v in [lat, jitter, tcp_discord, tcp_steam]):
        if lat < 20 and jitter < 3 and tcp_discord < 60 and tcp_steam < 60:
            return "🟢 Ótima para jogos, voz e uso geral"
        if lat < 40 and jitter < 8 and tcp_discord < 100 and tcp_steam < 100:
            return "🟢 Internet estável, sem impacto perceptível"
        if lat < 80 and jitter < 15:
            return "🟡 Pequena degradação, possível impacto leve em jogos/voz"

    if eventos:
        return "🟡 Oscilações pontuais detectadas, já normalizaram"

    return "🟢 Internet estável, sem impacto perceptível"


def build_services_text(kuma):
    if kuma["total"] <= 0:
        return "⚪ Kuma indisponível ou sem dados"

    text = f"{kuma['online']}/{kuma['total']} online"
    details = []

    if kuma["offline"] > 0:
        details.append("🔴 Offline: " + ", ".join(kuma["offline_names"][:5]))
    if kuma["unknown"] > 0:
        details.append(f"🟡 Desconhecido: {kuma['unknown']}")
    if kuma["avg_ping"] is not None:
        details.append(f"Ping médio: {kuma['avg_ping']:.1f} ms")

    return text + ("\n" + "\n".join(details) if details else "")


def build_speedtest_text(speed):
    return (
        f"**Agora:** ↓ {fmt_mbps(speed['dl_last'])} | ↑ {fmt_mbps(speed['ul_last'])} | Ping {fmt_ms(speed['ping_last'], 1)}\n"
        f"**7d:** ↓ {fmt_mbps(speed['dl_7d'])} | ↑ {fmt_mbps(speed['ul_7d'])}\n"
        f"**Mín:** ↓ {fmt_mbps(speed['dl_7d_min'])} | ↑ {fmt_mbps(speed['ul_7d_min'])}"
    )


def _state_age_hours(ts_str: str) -> float:
    """Retorna quantas horas se passaram desde o timestamp ISO do state file."""
    try:
        ts = datetime.fromisoformat(ts_str)
        return (datetime.now() - ts).total_seconds() / 3600
    except Exception:
        return float("inf")


def load_state_data() -> dict:
    """Lê todos os state files e retorna dict com os dados relevantes."""
    daily   = read_state(DAILY_STATE_FILE)
    anomaly = read_state(ANOMALY_STATE_FILE)
    unbound = read_state(UNBOUND_STATE_FILE)
    weekly  = read_state(WEEKLY_STATE_FILE)
    grafana = read_state(GRAFANA_STATE_FILE)
    return {
        "daily":   daily   if daily   and _state_age_hours(daily.get("timestamp",   "")) < 13  else {},
        "anomaly": anomaly if anomaly else {},
        "unbound": unbound if unbound else {},
        "weekly":  weekly  if weekly  and _state_age_hours(weekly.get("timestamp",  "")) < 168 else {},
        "grafana": grafana if grafana else {},
    }


def build_embed(metrics, diag_emoji, diag_texto, diag_val, eventos, alerts, kuma, speed, state=None):
    state = state or {}
    now = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y às %H:%M")
    score = metrics["score"]
    resumo = resumo_humano(metrics, diag_val, eventos, alerts, kuma)

    weekly_line = state.get("weekly", {}).get("summary_line", "")

    fields = [
        {
            "name": "📊 Geral",
            "value": (
                f"**Score:** `{score}/100{ctx_score(score)}`\n"
                f"**Uptime 24h:** `{metrics['uptime']}%{ctx_uptime(metrics['uptime'])}`\n"
                f"**Diagnóstico:** {diag_emoji} {diag_texto}\n"
                f"**Resumo:** {resumo}"
            ),
            "inline": False,
        },
        {"name": "​", "value": "─" * 38, "inline": False},
        {
            "name": "📡 Internet",
            "value": (
                f"**Latência:** `{metrics['latencia']} ms{ctx_latencia(metrics['latencia'])}`\n"
                f"**Jitter:** `{metrics['jitter']} ms{ctx_jitter(metrics['jitter'])}`"
            ),
            "inline": True,
        },
        {
            "name": "🎮 Jogos / Tempo real",
            "value": (
                f"**Discord:** `{metrics['tcp_discord']} ms{ctx_tcp(metrics['tcp_discord'])}`\n"
                f"**Steam:** `{metrics['tcp_steam']} ms{ctx_tcp(metrics['tcp_steam'])}`"
            ),
            "inline": True,
        },
        {
            "name": "🔍 DNS",
            "value": (
                f"**Resposta:** `{metrics['dns']} ms{ctx_dns(metrics['dns'])}`\n"
                f"**Cache:** `{metrics['cache']}%{ctx_cache(metrics['cache'])}`"
            ),
            "inline": True,
        },
        {"name": "🖥️ Serviços", "value": build_services_text(kuma), "inline": True},
        {"name": "🚀 Speedtest", "value": build_speedtest_text(speed), "inline": False},
    ]

    daily   = state.get("daily",   {})
    anomaly = state.get("anomaly", {})
    unbound = state.get("unbound", {})
    grafana = state.get("grafana", {})

    has_conditional = bool(
        eventos or alerts
        or daily.get("analysis")
        or anomaly.get("has_anomalies")
        or (unbound.get("has_issues") and unbound.get("analysis"))
        or grafana.get("active_alerts")
    )

    if has_conditional:
        fields.append({"name": "​", "value": "─" * 38, "inline": False})

    if eventos:
        fields.append({"name": "🕐 Eventos recentes — 30min", "value": "\n".join(f"• {e}" for e in eventos), "inline": False})

    if alerts:
        fields.append({"name": "⚠️ Alertas ativos", "value": "\n".join(f"• {a}" for a in alerts), "inline": False})

    if daily.get("analysis"):
        ts_hora = daily["timestamp"][11:16] if len(daily.get("timestamp", "")) >= 16 else "?"
        fields.append({
            "name": f"🤖 Análise IA — última às {ts_hora}",
            "value": truncate_field(daily["analysis"], 900),
            "inline": False,
        })

    if anomaly.get("has_anomalies"):
        ts_hora = anomaly["timestamp"][11:16] if len(anomaly.get("timestamp", "")) >= 16 else "?"
        linhas = [
            "📈 **{}**: `{:.1f}` vs média `{:.1f}` ({:.1f}σ)".format(
                a["label"], a["atual"], a["media"], a["sigma"]
            )
            for a in anomaly.get("anomalies", [])
        ]
        resumo_an = "\n".join(linhas)
        analise_an = truncate_field(anomaly.get("analysis", ""), 600)
        fields.append({
            "name": f"⚠️ Anomalias Detectadas — {ts_hora}",
            "value": truncate_field((resumo_an + "\n" + analise_an).strip(), 1024),
            "inline": False,
        })

    if unbound.get("has_issues") and unbound.get("analysis"):
        ts_hora = unbound["timestamp"][11:16] if len(unbound.get("timestamp", "")) >= 16 else "?"
        fields.append({
            "name": f"📋 DNS Logs — {ts_hora}",
            "value": truncate_field(unbound["analysis"], 800),
            "inline": False,
        })

    if grafana.get("active_alerts"):
        linhas = [
            "🔴 **{}** ({}) — {}".format(
                a.get("name", "?"), a.get("severity", "?"),
                truncate_field(a.get("analysis", ""), 120)
            )
            for a in grafana["active_alerts"][:5]
        ]
        fields.append({
            "name": "🔔 Alertas Grafana",
            "value": truncate_field("\n".join(linhas), 400),
            "inline": False,
        })

    description = f"Atualizado em **{now}**\n[📊 Ver dashboard ao vivo]({PUBLIC_DASHBOARD_URL})"
    if weekly_line:
        description += f"\n{weekly_line}"

    return {
        "embeds": [{
            "title": f"{score_emoji(score)} Homelab Monitor — Pato Branco, PR",
            "description": description,
            "color": embed_color(score, alerts, kuma),
            "fields": fields,
            "footer": {"text": "Prometheus • Grafana • Blackbox Exporter • Unbound • MikroTik • Uptime Kuma • Speedtest"},
        }]
    }




if __name__ == "__main__":
    print("Coletando métricas de rede...")
    metrics = get_network_metrics()
    print(metrics)

    print("Verificando diagnóstico...")
    diag_emoji, diag_texto, diag_val = get_diagnostico()
    print(f"Nível {diag_val}: {diag_emoji} {diag_texto}")

    print("Verificando eventos recentes...")
    eventos = get_eventos_recentes()
    print(eventos or "nenhum")

    print("Verificando alertas ativos...")
    alerts = check_alerts(metrics)
    print(alerts or "nenhum")

    print("Consultando Uptime Kuma...")
    kuma = get_kuma_summary()
    print(kuma)

    print("Coletando Speedtest...")
    speed = get_speedtest_metrics()
    print(speed)

    print("Lendo state files...")
    state = load_state_data()
    print({k: bool(v) for k, v in state.items()})

    print("Montando embed...")
    payload = build_embed(metrics, diag_emoji, diag_texto, diag_val, eventos, alerts, kuma, speed, state)

    print("Enviando para Discord...")
    bot_send_or_edit(payload, CHANNEL_ID, DISCORD_TOKEN, MESSAGE_ID_FILE)
    print("Feito.")
