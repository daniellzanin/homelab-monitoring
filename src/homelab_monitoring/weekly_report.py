#!/usr/bin/env python3
# =============================================================
# Weekly Network Report
# Todo domingo analisa os 7 dias e manda resumo no Discord
# =============================================================

import os
from datetime import datetime

from .homelab_lib import (
    DISCORD_WEBHOOK,
    HISTORY_FILE,
    OLLAMA_MODEL,
    SYSTEM_CONTEXT,
    call_ollama,
    load_history,
    webhook_send_or_edit,
    write_state,
)

MESSAGE_FILE      = os.environ.get("WEEKLY_MESSAGE_FILE", "./data/weekly-message-id.txt")
WEEKLY_STATE_FILE = os.environ.get("WEEKLY_STATE_FILE", "./data/state/weekly_summary.json")


def build_prompt(history):
    now = datetime.now().strftime("%d/%m/%Y")

    semana = history[-7:] if len(history) >= 7 else history

    dias = []
    for entry in semana:
        ts  = entry.get("timestamp", "")[:10]
        m   = entry.get("metrics", {})
        dia = "Data: {}\n".format(ts)
        for key, val in m.items():
            if val is not None:
                dia += "  {}: {:.2f}\n".format(key, val)
        dias.append(dia)

    dados = "\n".join(dias)

    all_metrics = {}
    for entry in semana:
        for key, val in entry.get("metrics", {}).items():
            if val is not None:
                if key not in all_metrics:
                    all_metrics[key] = []
                all_metrics[key].append(val)

    medias = []
    for key, vals in all_metrics.items():
        medias.append("- {}: media {:.2f}, min {:.2f}, max {:.2f}".format(
            key, sum(vals)/len(vals), min(vals), max(vals)
        ))
    medias_text = "\n".join(medias)

    return """Voce e um especialista em redes fazendo o relatorio semanal do homelab de Daniel em Pato Branco PR.

SEMANA ENCERRADA EM: {}
DIAS ANALISADOS: {}

DADOS DIA A DIA:
{}

RESUMO ESTATISTICO DA SEMANA:
{}

INFRAESTRUTURA:
{}

Gere um relatorio semanal em portugues com:
1. Resumo geral da semana em uma linha (use emoji de clima)
2. Conectividade — como se comportou a latencia e jitter ao longo da semana, picos e estabilidade
3. DNS — cache hit rate, recursao, tendencia
4. Infraestrutura — temperatura e comportamento do MikroTik
5. Comparacao com semanas anteriores se tiver dados
6. Ponto de atencao para a proxima semana

Seja direto e tecnico mas acessivel. Use **negrito** nos valores importantes. Maximo 400 palavras. Formate bem para Discord.""".format(
        now, len(semana), dados, medias_text, SYSTEM_CONTEXT
    )


def send_discord(analysis):
    now_str = datetime.now().strftime("%d/%m/%Y")
    payload = {
        "embeds": [{
            "title": "📊 Relatório Semanal — Homelab Pato Branco",
            "description": analysis,
            "color": 0x6366f1,
            "footer": {
                "text": "Semana encerrada em {} • {} • Homelab Monitor".format(now_str, OLLAMA_MODEL)
            }
        }]
    }
    webhook_send_or_edit(payload, MESSAGE_FILE)


def main():
    print("=" * 50)
    print("Weekly Report — {}".format(datetime.now().strftime("%d/%m/%Y %H:%M")))
    print("=" * 50)

    history = load_history()
    print("Entradas no historico: {}".format(len(history)))

    if len(history) < 2:
        print("Historico insuficiente — precisa de pelo menos 2 dias de dados.")
        return

    prompt = build_prompt(history)
    if not prompt:
        print("Erro ao montar prompt.")
        return

    print("Gerando analise semanal com Ollama...")
    analysis = call_ollama(prompt, temperature=0.7, num_predict=400)

    print("\nAnalise:")
    print("-" * 40)
    print(analysis)
    print("-" * 40)

    summary_line = analysis.splitlines()[0] if analysis.splitlines() else analysis[:120]
    write_state(WEEKLY_STATE_FILE, {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "summary_line": summary_line,
        "full_analysis": analysis,
    })
    print("  State file escrito: {}".format(WEEKLY_STATE_FILE))

    send_discord(analysis)
    print("Concluido!")


if __name__ == "__main__":
    main()
