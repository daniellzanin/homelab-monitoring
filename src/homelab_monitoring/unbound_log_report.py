#!/usr/bin/env python3
# =============================================================
# Unbound Log Report
# Analisa logs do Unbound e escreve state file para o unified
# Executa somente quando métricas DNS indicam degradação
# =============================================================

import subprocess
import os
from datetime import datetime

from .homelab_lib import (
    Q_CACHE_HIT,
    Q_EXCEEDED,
    call_ollama,
    query_prometheus,
    write_state,
)

UNBOUND_STATE_FILE = os.environ.get("UNBOUND_STATE_FILE", "./data/state/unbound_report.json")


def dns_needs_inspection():
    cache_hit        = query_prometheus(Q_CACHE_HIT)
    queries_exceeded = query_prometheus(Q_EXCEEDED)
    degraded_cache   = cache_hit is not None and cache_hit < 60
    has_exceeded     = queries_exceeded is not None and queries_exceeded > 0
    return degraded_cache or has_exceeded, cache_hit, queries_exceeded


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


def main():
    print("=" * 50)
    print("Unbound Log Report — {}".format(datetime.now().strftime("%d/%m/%Y %H:%M")))
    print("=" * 50)

    needs, cache_hit, exceeded = dns_needs_inspection()
    if not needs:
        print("  DNS saudavel (cache {}, exceeded {}) — analise de logs ignorada.".format(
            "{:.1f}%".format(cache_hit) if cache_hit is not None else "N/A",
            "{:.4f}/s".format(exceeded) if exceeded is not None else "0",
        ))
        write_state(UNBOUND_STATE_FILE, {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "has_issues": False,
            "analysis": "DNS normal (verificado via métricas Prometheus).",
        })
        print("  State file escrito: {}".format(UNBOUND_STATE_FILE))
        return

    print("  DNS com sinais de degradacao — coletando logs...")
    logs = get_logs()
    print("  {} linhas coletadas".format(len(logs.splitlines())))

    print("Analisando com Ollama...")
    analysis = call_ollama(build_prompt(logs), temperature=0.3, num_predict=300)

    print("Analise:")
    print("-" * 40)
    print(analysis)
    print("-" * 40)

    # Métricas já indicavam degradação — sempre exibir análise no painel
    write_state(UNBOUND_STATE_FILE, {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "has_issues": True,
        "analysis": analysis,
    })
    print("  State file escrito: {}".format(UNBOUND_STATE_FILE))
    print("Concluido!")


if __name__ == "__main__":
    main()
