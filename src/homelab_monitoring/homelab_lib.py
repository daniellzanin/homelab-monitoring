#!/usr/bin/env python3
"""homelab_lib.py — funções e constantes compartilhadas entre os scripts do homelab."""

import json
import os
import requests

# ── Constantes globais ────────────────────────────────────────
PROMETHEUS_BASE    = os.environ.get("PROMETHEUS_BASE",    "http://localhost:9090")
OLLAMA_URL         = os.environ.get("OLLAMA_URL",         "http://localhost:11434")
OLLAMA_MODEL       = os.environ.get("OLLAMA_MODEL",       "qwen2.5:3b")
DISCORD_WEBHOOK    = os.environ.get("DISCORD_WEBHOOK",    "")
HISTORY_FILE       = os.environ.get("HISTORY_FILE",       "./data/history.json")
ROUTERBOARD_NAME   = os.environ.get("ROUTERBOARD_NAME",   "RouterCasa")
TIMEOUT_PROMETHEUS = int(os.environ.get("TIMEOUT_PROMETHEUS", "10"))
TIMEOUT_OLLAMA     = int(os.environ.get("TIMEOUT_OLLAMA",     "180"))
MAX_HISTORY        = int(os.environ.get("MAX_HISTORY",        "30"))

# Contexto de infraestrutura reutilizado nos prompts Ollama
SYSTEM_CONTEXT = (
    "- Roteador: MikroTik ({})\n"
    "- DNS: AdGuard Home + Unbound recursivo com DNSSEC\n"
    "- Servidor: Debian 12 no Proxmox (Xeon E5-2680 v4, 64GB RAM)\n"
    "- ISP: fibra óptica em Pato Branco PR"
).format(ROUTERBOARD_NAME)

# ── Queries PromQL compartilhadas ─────────────────────────────
Q_LAT_IPV4   = 'avg(probe_icmp_duration_seconds{job="blackbox_icmp",phase="rtt"})*1000'
Q_LAT_IPV6   = 'avg(probe_icmp_duration_seconds{job="blackbox_icmp_v6",phase="rtt"})*1000'
Q_JITTER     = 'avg(stddev_over_time((probe_icmp_duration_seconds{job="blackbox_icmp",phase="rtt"}*1000)[5m:]))'
Q_PERDA      = 'avg(sum_over_time((1-probe_success{job="blackbox_icmp"})[5m:10s])/count_over_time(probe_success{job="blackbox_icmp"}[5m:10s]))*100'
Q_DNS_RESP   = 'avg(probe_dns_duration_seconds{job="blackbox_dns",phase="request"})*1000'
Q_CACHE_HIT  = (
    'sum(rate(unbound_cache_hits_total[5m]))'
    ' / clamp_min(sum(rate(unbound_cache_hits_total[5m])) + sum(rate(unbound_cache_misses_total[5m])), 0.001)'
    ' * 100'
)
Q_RECURSAO   = 'unbound_recursion_time_seconds_avg*1000'
Q_EXCEEDED   = 'rate(unbound_request_list_exceeded_total[5m])'
Q_UPTIME_24H = 'avg_over_time(probe_success{job="blackbox_icmp",instance="Cloudflare"}[24h])*100'
Q_RB_TEMP    = f'mktxp_system_cpu_temperature{{routerboard_name="{ROUTERBOARD_NAME}"}}'
Q_RB_CPU     = f'mktxp_system_cpu_load{{routerboard_name="{ROUTERBOARD_NAME}"}}'
Q_RB_CONN    = f'mktxp_ip_connections_total{{routerboard_name="{ROUTERBOARD_NAME}"}}'


# ── Prometheus ────────────────────────────────────────────────

def query_prometheus(query: str, timeout: int = None):
    """Executa uma query no Prometheus e retorna o primeiro valor como float, ou None."""
    timeout = timeout if timeout is not None else TIMEOUT_PROMETHEUS
    try:
        resp = requests.get(
            "{}/api/v1/query".format(PROMETHEUS_BASE),
            params={"query": query},
            timeout=timeout,
        )
        data = resp.json()
        if data["status"] == "success" and data["data"]["result"]:
            return float(data["data"]["result"][0]["value"][1])
    except Exception as e:
        print("  Erro Prometheus: {}".format(e))
    return None


# ── Ollama ────────────────────────────────────────────────────

def call_ollama(
    prompt: str,
    model: str = None,
    temperature: float = 0.7,
    num_predict: int = 300,
    timeout: int = None,
) -> str:
    """Envia um prompt ao Ollama e retorna o texto gerado."""
    model   = model or OLLAMA_MODEL
    timeout = timeout if timeout is not None else TIMEOUT_OLLAMA
    try:
        resp = requests.post(
            "{}/api/generate".format(OLLAMA_URL),
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": num_predict},
            },
            timeout=timeout,
        )
        data = resp.json()
        if "error" in data:
            msg = "Ollama erro ({}): {}".format(model, data["error"][:120])
            print("  " + msg)
            return msg
        return data.get("response", "Ollama sem resposta.").strip()
    except requests.exceptions.Timeout:
        msg = "Ollama timeout após {}s ({})".format(timeout, model)
        print("  " + msg)
        return msg
    except Exception as e:
        msg = "Erro ao chamar Ollama: {}".format(e)
        print("  " + msg)
        return msg


# ── Histórico ─────────────────────────────────────────────────

def load_history(path: str = None) -> list:
    """Carrega o histórico JSON de métricas. Retorna lista vazia se não existir ou inválido."""
    path = path or HISTORY_FILE
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            print("  Aviso: history.json inválido (esperava lista, encontrou {}), ignorando.".format(
                type(data).__name__
            ))
        except Exception as e:
            print("  Aviso: falha ao carregar history.json ({}), retornando vazio.".format(e))
    return []


def write_state(path: str, data: dict) -> None:
    """Escreve dados de estado em JSON para consumo pelo discord_unified."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def read_state(path: str) -> dict:
    """Lê arquivo de estado JSON. Retorna dict vazio se não existir ou inválido."""
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def truncate_field(text: str, max_len: int, suffix: str = "…") -> str:
    """Trunca texto para o limite de campo do Discord, adicionando sufixo se necessário."""
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


# ── Discord helpers (internos) ────────────────────────────────

def _load_msg_id(path: str):
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip() or None
    return None


def _save_msg_id(path: str, msg_id: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(msg_id)


# ── Discord — Webhook (scripts cron) ─────────────────────────

def webhook_send_or_edit(payload: dict, message_file: str, webhook_url: str = None) -> None:
    """Edita a mensagem existente via PATCH ou posta uma nova via POST (webhook)."""
    webhook_url = webhook_url or DISCORD_WEBHOOK
    msg_id = _load_msg_id(message_file)
    try:
        if msg_id:
            resp = requests.patch(
                "{}/messages/{}".format(webhook_url, msg_id),
                json=payload,
                timeout=10,
            )
            if resp.status_code == 200:
                print("  Mensagem editada (ID: {})".format(msg_id))
                return
            print("  Falha ao editar ({}), enviando nova...".format(resp.status_code))

        resp = requests.post("{}?wait=true".format(webhook_url), json=payload, timeout=10)
        data = resp.json()
        if "id" in data:
            _save_msg_id(message_file, data["id"])
            print("  Nova mensagem enviada (ID: {})".format(data["id"]))
        else:
            print("  Erro Discord: {}".format(data))
    except Exception as e:
        print("  Erro ao enviar Discord: {}".format(e))


# ── Discord — Bot API (scripts com token) ────────────────────

def bot_send_or_edit(
    payload: dict,
    channel_id: str,
    token: str,
    message_file: str,
) -> None:
    """Edita a mensagem existente via PATCH ou posta uma nova via POST (bot token)."""
    headers = {"Authorization": "Bot {}".format(token), "Content-Type": "application/json"}
    base = "https://discord.com/api/v10/channels/{}".format(channel_id)
    msg_id = _load_msg_id(message_file)
    try:
        if msg_id:
            resp = requests.patch(
                "{}/messages/{}".format(base, msg_id),
                headers=headers,
                json=payload,
                timeout=10,
            )
            if resp.status_code == 200:
                print("  Mensagem editada (ID: {})".format(msg_id))
                return
            print("  Falha ao editar ({}), enviando nova...".format(resp.status_code))

        resp = requests.post(
            "{}/messages".format(base),
            headers=headers,
            json=payload,
            timeout=10,
        )
        data = resp.json()
        if "id" in data:
            _save_msg_id(message_file, data["id"])
            print("  Nova mensagem enviada (ID: {})".format(data["id"]))
        else:
            print("  Erro Discord: {}".format(data))
    except Exception as e:
        print("  Erro ao enviar Discord: {}".format(e))
