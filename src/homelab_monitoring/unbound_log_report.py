#!/usr/bin/env python3
# =============================================================
# Unbound Log Report
# Analisa logs da noite e manda resumo no Discord
# =============================================================

import subprocess
import os
from datetime import datetime

from .homelab_lib import (
    DISCORD_WEBHOOK,
    call_ollama,
    webhook_send_or_edit,
)

MESSAGE_FILE = os.environ.get("UNBOUND_LOG_MESSAGE_FILE", "./data/unbound-log-message-id.txt")


def get_logs():
    try:
        result = subprocess.run(
            ["journalctl", "-u", "unbound", "--since", "8 hours ago", "--no-pager"],
            capture_output=True, text=True, timeout=15
        )
        lines = result.stdout.strip().splitlines()
        if len(lines) > 300:
            lines = lines[-300:]
        return "\n".join(lines)
    except Exception as e:
        return "Erro ao coletar logs: {}".format(e)


def build_prompt(logs):
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    return """Voce e um especialista em DNS analisando logs do Unbound de um homelab.

DATA: {}

LOGS DAS ULTIMAS 8 HORAS:
{}

Analise os logs e responda em portugues:
1. Se tudo estiver normal, diga isso em UMA linha curta
2. Se houver erros, warnings ou eventos incomuns, liste apenas esses com uma breve explicacao do que significa
3. Se houver padroes suspeitos (muitos SERVFAIL, queries repetidas, timeouts), mencione
4. Ignore mensagens normais de operacao como cache hits, queries comuns, starts/stops de servico

Seja direto. Se nao houver nada relevante, diga apenas: Logs normais, nenhum evento relevante nas ultimas 8 horas.
Maximo 10 linhas. Formate para Discord.""".format(now, logs)


def send_discord(analysis):
    now_str = datetime.now().strftime("%d/%m/%Y as %H:%M")
    payload = {
        "embeds": [{
            "title": "📋 Logs Unbound — Últimas 8h",
            "description": analysis,
            "color": 0x3b82f6,
            "footer": {"text": "{} • Homelab Monitor".format(now_str)}
        }]
    }
    webhook_send_or_edit(payload, MESSAGE_FILE)


def main():
    print("=" * 50)
    print("Unbound Log Report — {}".format(datetime.now().strftime("%d/%m/%Y %H:%M")))
    print("=" * 50)

    print("Coletando logs...")
    logs = get_logs()
    print("  {} linhas coletadas".format(len(logs.splitlines())))

    print("Analisando com Ollama...")
    analysis = call_ollama(build_prompt(logs), temperature=0.3, num_predict=300)

    print("Analise:")
    print("-" * 40)
    print(analysis)
    print("-" * 40)

    send_discord(analysis)
    print("Concluido!")


if __name__ == "__main__":
    main()
