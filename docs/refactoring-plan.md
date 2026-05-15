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

**Concluída em 2026-05-15** (todos os scripts rodados manualmente).

### Checklist Fase 2

- [x] Confirmar campo "🤖 Análise IA" aparece → validado manualmente (monitor.py)
- [x] Forçar anomalia → detector encontrou anomalia real (DNS Response 2.1σ), campo apareceu no unified
- [x] Confirmar campo "📋 DNS Logs" → `has_issues: false`, campo corretamente ausente
- [x] Confirmar linha semanal na description → weekly_report.py rodado manualmente, `weekly: True` no unified
- [x] Simular alerta Grafana via `curl` → alerting criou entrada, resolved limpou, campo apareceu no unified

**Nota:** `summary_line` do weekly ficou com o título markdown (`### Relatório...`) em vez de linha
resumo curta. Ajustar o prompt do `weekly_report.py` na Fase 4 (limpeza final).

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

- [x] Implementar DISCORD_SILENT em todos os scripts
- [ ] Silenciar unbound_log_report → observar 2 dias
- [ ] Silenciar anomaly_detector → observar 2 dias
- [ ] Silenciar monitor → observar 3 dias
- [ ] Decidir sobre grafana_alert_receiver (notificação direta vs apenas estado)
- [ ] weekly_report mantém envio próprio (não silenciar)

---

## FASE 4 — Limpeza final

**Concluída em 2026-05-15.**

### Checklist Fase 4

- [x] Remover função `send_discord()` e imports relacionados de `monitor.py`
- [x] Remover função `send_discord()` e imports relacionados de `anomaly_detector.py`
- [x] Remover função `send_discord()` e imports relacionados de `unbound_log_report.py`
- [x] Remover função `send_discord()` e imports relacionados de `grafana_alert_receiver.py`
- [x] Remover variáveis `MESSAGE_FILE` desnecessárias dos scripts silenciados
- [x] Remover do `.env.example`: `MONITOR_MESSAGE_FILE`, `ANOMALY_MESSAGE_FILE`, `UNBOUND_LOG_MESSAGE_FILE`, `ALERT_WEBHOOK`, `ALERT_MSG_FILE`, `PROMETHEUS_URL`, `DISCORD_SILENT`
- [x] Corrigir duplicação em `discord_unified.py`: substituir função `query()` local por `query_prometheus()` de `homelab_lib`; remover `import requests` e `PROMETHEUS_URL` locais
- [x] Tornar `unbound_log_report.py` condicional: só executa journalctl + Ollama quando `cache_hit < 60%` OU `queries_exceeded > 0`
- [x] Atualizar `cron/homelab-monitoring.example`
- [x] Atualizar `README.md` para refletir nova arquitetura
- [x] Remover `DISCORD_SILENT` do código (sends foram removidos)

**Pendente (produção):** remover arquivos de message ID obsoletos após deploy:
`discord_message_id.txt`, `anomaly-message-id.txt`, `unbound-log-message-id.txt`

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

---

## Estado final do código (2026-05-15)

O refatoramento foi concluído integralmente. O sistema funciona assim:

**Um único painel Discord** — `discord_unified.py` é o único script que posta no Discord
(exceto `weekly_report.py`, que mantém sua própria mensagem por ser um relatório de leitura longa).

**Workers de fundo** — os outros scripts rodam nos seus crons, fazem seu trabalho
(Prometheus, Ollama, journalctl) e escrevem arquivos JSON em `data/state/`.
O unified lê esses arquivos a cada 3 minutos e exibe os campos relevantes.

### Mapa de responsabilidades atual

| Script | Faz | Escreve | Possui Discord? |
|---|---|---|---|
| `discord_unified.py` | Lê Prometheus + Kuma + state files | — | ✅ único painel |
| `monitor.py` | Coleta 12 métricas + chama Ollama + salva history.json | `daily_analysis.json` | ❌ |
| `anomaly_detector.py` | Lê history.json + cálculo σ + Ollama se anomalia | `anomaly_state.json` | ❌ |
| `unbound_log_report.py` | journalctl + Ollama (só se DNS degradado) | `unbound_report.json` | ❌ |
| `weekly_report.py` | Agrega 7 dias + Ollama | `weekly_summary.json` | ✅ própria mensagem |
| `grafana_alert_receiver.py` | Flask :9999, recebe webhooks do Grafana + Ollama | `grafana_alerts.json` | ❌ |
| `speedtest-prometheus.sh` | speedtest-ookla → Pushgateway | — | ❌ |
| `homelab_lib.py` | Biblioteca compartilhada | — | — |

### Onde cada coisa aparece no embed do unified

```
Título            → score composto + emoji de status
Description       → timestamp + link dashboard + linha semanal (se weekly < 7 dias)
Campo 📊 Geral    → score, uptime 24h, diagnóstico, resumo humano
Campo 📡 Internet → latência, jitter
Campo 🎮 Jogos    → TCP Discord, TCP Steam
Campo 🔍 DNS      → resposta DNS, cache hit %
Campo 🖥️ Serviços → Uptime Kuma (online/total, offline names, ping médio)
Campo 🚀 Speedtest→ agora + média 7d + mínimos 7d
Campo 🕐 Eventos  → picos HTTP/TCP/DNS últimos 30min (condicional)
Campo ⚠️ Alertas  → alertas baseados em thresholds Prometheus (condicional)
Campo 🤖 Análise IA → texto Ollama do monitor.py, atualizado 2×/dia (condicional, < 13h)
Campo ⚠️ Anomalias → detector σ, só quando has_anomalies: true (condicional)
Campo 📋 DNS Logs → logs Unbound, só quando has_issues: true (condicional)
Campo 🔔 Alertas Grafana → alertas ativos do Grafana (condicional)
Footer            → lista de fontes de dados
```

### Regras para modificar o código

**Para mudar a estética do painel (textos, emojis, formatação, campos):**
Editar apenas `discord_unified.py`. As funções relevantes são:
- `build_embed()` — monta o embed completo; campos ficam na lista `fields`
- `build_services_text()` — texto do campo Kuma
- `build_speedtest_text()` — texto do campo Speedtest
- `resumo_humano()` — lógica do texto de resumo na seção Geral
- `ctx_*()` — funções de contexto inline por métrica (ex: `ctx_latencia`, `ctx_cache`)
- `score_emoji()` — emoji do título baseado no score
- `embed_color()` — cor da barra lateral do embed

**Para mudar os campos dos workers (análise IA, anomalias, DNS logs, alertas Grafana):**
Os campos condicionais são lidos de state files e montados dentro de `build_embed()`,
nas linhas após os campos fixos. Procurar por `daily`, `anomaly`, `unbound`, `grafana`
dentro de `build_embed()`.

**Para mudar o que o monitor.py coleta ou como classifica:**
Editar a lista `METRICS` no topo de `monitor.py` (query PromQL, thresholds warn/crit, invert).
A classificação é feita por `classify()` no mesmo arquivo.

**Para mudar os limiares do detector de anomalias:**
`THRESHOLD_SIGMA = 2.0` no topo de `anomaly_detector.py`. Métricas invertidas (onde menor é pior)
estão em `INVERTED_METRICS`.

**Para mudar quando o unbound roda:**
Os limiares da guarda condicional estão no início de `unbound_log_report.py`:
`cache_hit < 60` e `queries_exceeded > 0`.

**Para mudar o modelo LLM:**
`OLLAMA_MODEL` em `homelab_lib.py` (padrão) ou via env `OLLAMA_MODEL`.
O detector de anomalias tem override próprio: env `ANOMALY_OLLAMA_MODEL`.

**Nunca fazer:**
- Adicionar `webhook_send_or_edit` ou `bot_send_or_edit` em `monitor.py`,
  `anomaly_detector.py`, `unbound_log_report.py` ou `grafana_alert_receiver.py`
  (esses scripts são workers — sem Discord próprio)
- Remover a escrita de `history.json` do `monitor.py`
  (dela dependem `anomaly_detector` e `weekly_report`)
- Adicionar `import requests` diretamente em `discord_unified.py`
  (usa `query_prometheus` da lib)
