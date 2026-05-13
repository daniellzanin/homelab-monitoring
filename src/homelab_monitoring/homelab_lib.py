#!/usr/bin/env python3
"""homelab_lib.py — funções e constantes compartilhadas entre os scripts do homelab."""

import json
import os
import requests

# ── Constantes globais ────────────────────────────────────────
PROMETHEUS_BASE = os.environ.get("PROMETHEUS_BASE", "http://localhost:9090")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
HISTORY_FILE = os.environ.get("HISTORY_FILE", "./data/history.json")


# ── Prometheus ────────────────────────────────────────────────

def query_prometheus(query: str, timeout: int = 10):
    """Executa uma query no Prometheus e retorna o primeiro valor como float, ou None."""
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
    timeout: int = 180,
) -> str:
    """Envia um prompt ao Ollama e retorna o texto gerado."""
    model = model or OLLAMA_MODEL
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
    """Carrega o histórico JSON de métricas. Retorna lista vazia se não existir."""
    path = path or HISTORY_FILE
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return []


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
