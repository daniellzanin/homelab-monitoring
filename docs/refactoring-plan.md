# Plano de Refatoramento — Super Unified Discord Panel

Registrado em 2026-05-15. Não executar sem leitura completa deste documento.

## Objetivo

Consolidar 6 mensagens Discord independentes em um único painel (`discord_unified.py`).
Os scripts existentes viram **trabalhadores de fundo** que escrevem arquivos de estado.
O unified lê esses arquivos e exibe tudo em um único embed rico.

## Arquitetura alvo

```
Scripts (sem output Discord próprio após refatoramento):
├── monitor.py          (2×/dia)     → data/state/daily_analysis.json
├── anomaly_detector.py (a cada 4h)  → data/state/anomaly_state.json
├── unbound_log_report.py (condicional) → data/state/unbound_report.json
├── weekly_report.py    (domingo)    → data/state/weekly_summary.json
│                                       + mantém mensagem Discord separada (doc longo)
└── grafana_alert_receiver.py (Flask) → data/state/grafana_alerts.json
                                         + notificação Discord direta (evento crítico)

discord_unified.py (a cada 3 min):
├── Prometheus queries (tempo real)
├── Uptime Kuma (tempo real)
├── lê state/daily_analysis.json    → campo "🤖 Análise IA" (se fresco, < 13h)
├── lê state/anomaly_state.json     → campo "⚠️ Anomalias" (somente se has_anomalies)
├── lê state/unbound_report.json    → campo "📋 DNS Logs" (somente se has_issues)
├── lê state/weekly_summary.json    → linha na description (se < 7 dias)
└── lê state/grafana_alerts.json    → campo "🔔 Alertas Grafana" (se lista não vazia)
```

## Schemas dos arquivos de estado

Todos os arquivos vivem em `data/state/` (fora do Git — adicionar ao .gitignore).

### `data/state/daily_analysis.json`
```json
{
  "timestamp": "2026-05-15T08:00:12",
  "analysis": "☀️ Rede está excelente hoje...",
  "status": "OK",
  "ok": 11,
  "warn": 1,
  "crit": 0
}
```

### `data/state/anomaly_state.json`
```json
{
  "timestamp": "2026-05-15T12:00:05",
  "has_anomalies": true,
  "anomalies": [
    {"label": "Latencia IPv4", "atual": 45.2, "media": 12.1, "sigma": 3.2}
  ],
  "analysis": "**Latência** acima do normal..."
}
```

### `data/state/unbound_report.json`
```json
{
  "timestamp": "2026-05-15T07:00:18",
  "has_issues": false,
  "analysis": "Logs normais, nenhum evento relevante"
}
```

### `data/state/weekly_summary.json`
```json
{
  "timestamp": "2026-05-11T09:00:42",
  "summary_line": "☀️ Semana estável — latência média 12ms, cache 91%",
  "full_analysis": "..."
}
```

### `data/state/grafana_alerts.json`
```json
{
  "timestamp": "2026-05-15T14:22:10",
  "active_alerts": [
    {
      "name": "HighCPU",
      "severity": "warning",
      "state": "alerting",
      "analysis": "CPU do Proxmox acima de 90% por 10 minutos..."
    }
  ]
}
```

## Função a adicionar em homelab_lib.py

```python
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
```

## Variáveis de ambiente a adicionar (.env.example)

```
DAILY_STATE_FILE=./data/state/daily_analysis.json
ANOMALY_STATE_FILE=./data/state/anomaly_state.json
UNBOUND_STATE_FILE=./data/state/unbound_report.json
WEEKLY_STATE_FILE=./data/state/weekly_summary.json
GRAFANA_STATE_FILE=./data/state/grafana_alerts.json
DISCORD_SILENT=0
```

## Novos campos no embed do discord_unified

Adicionar ao `build_embed()`, após os campos existentes, somente se conteúdo presente:

**Campo análise IA** (sempre que arquivo existir e timestamp < 13h):
```
🤖 Análise IA — última às HH:MM
<analysis text, truncado em 900 chars>
```

**Campo anomalias** (somente se `has_anomalias: true`):
```
⚠️ Anomalias Detectadas — HH:MM
📈 Latencia IPv4: 45.2ms vs média 12.1ms (3.2σ)
<analysis, truncado em 600 chars>
```

**Campo DNS logs** (somente se `has_issues: true`):
```
📋 DNS Logs — HH:MM
<analysis, truncado em 800 chars>
```

**Campo alertas Grafana** (somente se `active_alerts` não vazio):
```
🔔 Alertas Grafana
🔴 HighCPU (warning) — <analysis>
```

**Linha semanal na description** (somente se `weekly_summary.json` < 7 dias):
Adicionar à description existente: `\n<summary_line>`

---

## FASE 1 — Adicionar escrita de estado (sem remover nada)

**Regra:** nada é removido. Scripts continuam enviando ao Discord normalmente.
Apenas adicionamos escrita de estado E leitura no unified.

### Checklist Fase 1

- [x] Adicionar `write_state()` e `read_state()` em `homelab_lib.py`
- [x] Adicionar `data/state/` ao `.gitignore`
- [x] Adicionar variáveis `*_STATE_FILE` ao `.env.example`
- [x] `monitor.py`: chamar `write_state(DAILY_STATE_FILE, {...})` após gerar analysis
- [x] `anomaly_detector.py`: chamar `write_state(ANOMALY_STATE_FILE, {...})` sempre (com `has_anomalies: false` quando limpo)
- [x] `unbound_log_report.py`: chamar `write_state(UNBOUND_STATE_FILE, {...})` com `has_issues` baseado na analysis
- [x] `weekly_report.py`: chamar `write_state(WEEKLY_STATE_FILE, {...})` com `summary_line` (1ª linha da analysis) e `full_analysis`
- [x] `grafana_alert_receiver.py`: chamar `write_state(GRAFANA_STATE_FILE, {...})` ao receber alerta; limpar lista ao receber resolved
- [x] `discord_unified.py`: adicionar leitura dos state files e novos campos no embed
- [x] Rodar cada script uma vez manualmente e confirmar os campos aparecem no unified

**Validação da Fase 1:**
```bash
# Rodar monitor manualmente e verificar
cd /opt/homelab-monitoring
PYTHONPATH=src python3 -m homelab_monitoring.monitor

# Confirmar arquivo criado
cat data/state/daily_analysis.json

# Aguardar próxima execução do unified (até 3 min) e verificar no Discord
```

---

## FASE 2 — Validação em paralelo

**Duração recomendada:** 1 semana completa (para cobrir o ciclo do weekly report).
**Ação:** nenhuma alteração de código. Apenas observar.

### Checklist Fase 2

- [ ] Confirmar campo "🤖 Análise IA" aparece às 08:00 e 20:00
- [ ] Forçar anomalia manualmente (alterar threshold temporariamente) e confirmar campo no unified
- [ ] Confirmar campo "📋 DNS Logs" quando `unbound_log_report.py` rodar (07:00)
- [ ] Aguardar domingo: confirmar linha semanal na description do unified
- [ ] Simular alerta Grafana via `curl` e confirmar campo no unified

```bash
# Simular alerta Grafana para teste
curl -X POST http://localhost:9999/alert \
  -H "Content-Type: application/json" \
  -d '{"alerts":[{"labels":{"alertname":"Teste","severity":"warning"},"status":"alerting","annotations":{"summary":"Teste de integração"},"values":{}}]}'
```

---

## FASE 3 — Silenciar Discord nos scripts individuais (um por vez)

Adicionar suporte a `DISCORD_SILENT=1` em cada script.
Quando `DISCORD_SILENT=1`, o script executa tudo normalmente mas pula o `send_discord()`.

**Ordem segura (do menos ao mais crítico):**

1. `unbound_log_report.py` → aguardar 2 dias → confirmar unified mostra DNS issues
2. `anomaly_detector.py` → aguardar 2 dias → confirmar unified mostra anomalias
3. `monitor.py` → aguardar 3 dias → confirmar unified mostra análise IA
4. `grafana_alert_receiver.py` → decisão: manter notificação direta OU só estado
5. `weekly_report.py` → **manter envio próprio** (relatório completo é documento de leitura)

### Implementação do DISCORD_SILENT

Em cada script, antes do `send_discord()`:
```python
if os.environ.get("DISCORD_SILENT", "0") == "1":
    print("  DISCORD_SILENT=1 — envio suprimido.")
    return
```

No cron/env, ativar um por vez:
```bash
# Exemplo: silenciar unbound no cron
0 7 * * * ... DISCORD_SILENT=1 python3 -m homelab_monitoring.unbound_log_report ...
```

### Checklist Fase 3

- [ ] Implementar DISCORD_SILENT em todos os scripts
- [ ] Silenciar unbound_log_report → observar 2 dias
- [ ] Silenciar anomaly_detector → observar 2 dias
- [ ] Silenciar monitor → observar 3 dias
- [ ] Decidir sobre grafana_alert_receiver (notificação direta vs apenas estado)
- [ ] weekly_report mantém envio próprio (não silenciar)

---

## FASE 4 — Limpeza final

Executar somente após Fase 3 estável por 2+ semanas.

### Checklist Fase 4

- [ ] Remover função `send_discord()` e imports relacionados de `monitor.py`
- [ ] Remover função `send_discord()` e imports relacionados de `anomaly_detector.py`
- [ ] Remover função `send_discord()` e imports relacionados de `unbound_log_report.py`
- [ ] Remover variáveis `MESSAGE_FILE` desnecessárias dos scripts silenciados
- [ ] Remover do `.env.example`: `MONITOR_MESSAGE_FILE`, `ANOMALY_MESSAGE_FILE`, `UNBOUND_LOG_MESSAGE_FILE`
- [ ] Corrigir duplicação em `discord_unified.py`: substituir função `query()` local por `query_prometheus()` de `homelab_lib`
- [ ] Tornar `unbound_log_report.py` condicional: só executar quando `cache_hit < 60` OU `queries_exceeded > 0` (ler do Prometheus no início do script antes de chamar journalctl)
- [ ] Remover arquivos de message ID obsoletos em produção: `discord_message_id.txt`, `anomaly-message-id.txt`, `unbound-log-message-id.txt`
- [ ] Atualizar `cron/homelab-monitoring.example` removendo entradas silenciadas ou ajustando
- [ ] Atualizar `README.md` para refletir nova arquitetura
- [ ] Remover `DISCORD_SILENT` do código (não mais necessário — os sends foram removidos)

### Validação final

```bash
# Confirmar que não há envio Discord duplicado
grep -r "send_discord\|webhook_send_or_edit\|bot_send_or_edit" src/

# Deve aparecer apenas em:
# - discord_unified.py (bot_send_or_edit)
# - weekly_report.py (webhook_send_or_edit — mantido)
# - grafana_alert_receiver.py (webhook_send_or_edit — se mantido)
# - homelab_lib.py (definições)
```

---

## O que NUNCA consolidar

| Item | Motivo |
|---|---|
| `grafana_alert_receiver.py` como serviço Flask | Receptor HTTP — não substituível por polling |
| `weekly_report.py` mensagem Discord completa | 300–400 palavras é documento de leitura |
| `history.json` escrito por `monitor.py` | Base de dados crítica para anomaly + weekly |
| `speedtest-prometheus.sh` | Já na arquitetura correta (Pushgateway → Prometheus) |

---

## Riscos e mitigações

| Risco | Mitigação |
|---|---|
| State file corrompido quebra unified | `read_state()` retorna `{}` em caso de erro — unified simplesmente não exibe o campo |
| Timestamp antigo exibe dado desatualizado | unified verifica idade: não exibir se > 13h (diário) ou > 7d (semanal) |
| Grafana alerts não limpos após resolve | `process_alert()` limpa `active_alerts` ao receber `state=resolved` |
| Embed ultrapassa 6000 chars | Truncar cada campo: análise IA 900, anomalias 600, DNS logs 800, alertas Grafana 400 |
| Fase 3 silencia script com bug no state file | Rollback: remover `DISCORD_SILENT=1` do cron da entrada afetada |

---

## Contexto do projeto

- Repositório: `/home/daniel/repos/homelab-monitoring`
- Produção (legado): `/usr/local/bin/` + `/home/daniel/network-monitor/`
- Deploy alvo: `/opt/homelab-monitoring` (ver `docs/deployment-plan.md`)
- Biblioteca compartilhada: `src/homelab_monitoring/homelab_lib.py`
- Painel ao vivo: `src/homelab_monitoring/discord_unified.py` (a cada 3 min via cron)
- LLM: Ollama em `http://10.0.100.187:11434`, modelo `qwen2.5:3b`
- Este repositório é independente de `homelab-bot`, `cs2-ranking` e `steamwatch`
