# 04 — Guia de sustentação

Runbook para o dia a dia de manutenção: como testar, como investigar problemas, regras de segurança e o backlog de dívidas técnicas conhecidas (ótima fonte de primeiras tarefas).

## Testes

### Backend (pytest)

```powershell
cd backend
.\venv\Scripts\Activate.ps1
pytest                      # suíte completa (~131 testes, roda em segundos)
pytest tests/test_auth.py -v
```

Como funciona: `tests/conftest.py` cria um SQLite **in-memory** por teste (`db_session`) e um client HTTP (`client`, httpx AsyncClient) com o `get_db` sobrescrito. `asyncio_mode = auto` — escreva testes `async def` sem decorators extras.

Estado real: a cobertura é **baixa e concentrada** (extração, fuzzy matching de parcelas, agente de chat). Módulos críticos como `transactions`, `credit_cards` e `budgets` não têm testes. **Regra do time: todo PR que mexe em regra de negócio adiciona ao menos um teste da regra alterada** — é assim que a cobertura sobe de forma orgânica.

### Frontend

- Type check + build (o que o CI cobra): `npx tsc --noEmit && npm run build`
- **Não há testes unitários** de componentes (decisão herdada; e2e cobre o fluxo).

### E2E (Playwright)

Pré-requisitos: backend rodando em `localhost:8000` com um usuário de teste existente.

```powershell
cd frontend
npx playwright install          # primeira vez
$env:E2E_USER_EMAIL='voce@exemplo.com'; $env:E2E_USER_PASSWORD='SuaSenha@123'
npm run test:e2e                # ou test:e2e:ui para o modo interativo
```

O projeto `setup` faz login real e salva a sessão em `e2e/.auth/user.json` (ignorado pelo git). A suíte roda em 12 combinações navegador×tema×dispositivo — para iterar, filtre: `npx playwright test tests/05-transactions --project=chromium-light`.

## Troubleshooting em produção/uso real

| Sintoma | Onde olhar |
|---|---|
| Extração de fatura errando valores/datas | 1) Qual banco? Veja o prompt em `modules/documents/prompts/banks/`; 2) `extraction_validator.py` pode estar rejeitando/ajustando; 3) teste o mesmo PDF pelo Swagger (`POST /api/v1/documents`) e compare o JSON cru |
| Upload retorna erro de provider | Cota/limite da `GOOGLE_API_KEY` (429) — o retry cobre picos; cota zerada exige trocar a chave |
| Fatura com total divergente | O total é recalculado na criação de transações; confira `credit_cards/routers/invoices.py` e as transações da fatura no banco |
| Recorrentes não geraram | O APScheduler roda no processo da API — a API ficou no ar no horário do job? Só há **uma** réplica? (ver ADR-003) |
| Notificação não chegou | A entrega por email/push tem TODOs — as notificações são geradas mas **não são enviadas** (dívida #7 abaixo) |
| Usuário não consegue se registrar | É por convite (ADR-005) — verifique licenças/convites no módulo `admin` |
| Comportamento diferente entre dev e prod | Suspeite da diferença SQLite × PostgreSQL (ADR-002) — reproduza contra o Postgres do compose |

Limitação atual: o backend loga com `print()` (sem logging estruturado) — em produção, o rastro é o stdout do container. Melhorar isso é a dívida #5.

## Segurança — regras não negociáveis

Este repositório **já teve um incidente**: segredos e dados financeiros reais foram commitados e o histórico inteiro precisou ser reescrito (ver ADR-010). Para não repetir:

1. **Nunca commite:** `.env`, chaves de API, certificados/chaves (`.pem`, `.key`), dumps de banco (`.dump`, `.sql`), extratos/faturas reais (PDF/CSV), prints com dados reais. O `.gitignore` bloqueia os padrões — **não o contorne com `git add -f`**.
2. **Dados de teste são sintéticos.** Precisa de uma fatura para testar extração? Gere uma fictícia — jamais use a sua real.
3. Suspeita que commitou um segredo? **Avise o mantenedor imediatamente** — não tente apagar sozinho com mais commits (o segredo continua no histórico); a chave exposta deve ser rotacionada na hora.
4. **O scan de segredos é automático em duas camadas**: o gitleaks roda como hook de pre-commit na sua máquina (configure com `pre-commit install` — ver CONTRIBUTING.md) e de novo no CI, onde bloqueia o merge. A allowlist de placeholders de documentação fica em `.gitleaks.toml` — só adicione entradas ali se tiver certeza absoluta de que não é um segredo real.
5. `SECRET_KEY` forte em produção é vital: além de assinar os JWTs, deriva a chave que criptografa senhas de PDF dos usuários (`app/core/crypto.py`). Rotacioná-la invalida esses dados cifrados — não é uma env var qualquer.

## Backlog de dívidas técnicas conhecidas

Levantado em auditoria (ago/2026). Bom ponto de partida para tarefas do time — do mais valioso ao mais cosmético:

| # | Dívida | Onde | Por que importa |
|---|---|---|---|
| 1 | ~~Lint não roda no CI / ESLint sem config~~ **RESOLVIDO (ago/2026)**: `.eslintrc.cjs` criado, `ruff check` e `npm run lint` agora rodam no CI e bloqueiam o merge. Restam **31 warnings** de eslint (`any`, deps de hooks) que não bloqueiam — zerá-los é a continuação natural | `frontend/.eslintrc.cjs`, `backend/pyproject.toml` | Warnings visíveis em todo lint; não introduza novos |
| 2 | **Cobertura de testes baixa** nos módulos centrais (transactions, credit_cards/invoices, budgets) | `tests/` | É onde os bugs doem. Começar por testes de característica dos fluxos de fatura |
| 3 | **God files**: `financial_agent_service.py` (3.540 linhas), `transaction_service.py` (1.995), `invoices.py` (1.243 linhas de lógica dentro de um *router*), `Upload.tsx` (2.368) | backend + frontend | Difíceis de revisar e testar. O agente de chat já tem 53 testes escritos esperando o refactor |
| 4 | **Migração de dados inline no `main.py`** (~130 linhas de SQL rodando 30s após o boot) | `app/main.py` | Pertence a uma migração Alembic/script; hoje roda em todo start e falha silenciosamente |
| 5 | **`print()` como logging** em todo o backend | geral | Migrar para `logging` estruturado; hoje até prefixo de senha de PDF vai para stdout |
| 6 | ~~Código morto~~ **RESOLVIDO (ago/2026)**: camada Celery removida (config + tasks — a lógica útil, `should_run_scheduled`, migrou para `automations/services/schedule_utils.py`), `backend/mcp_server.py` legado removido, backups `*.backup_*` e `magic.mgc` removidos. Restam os providers OpenAI/Anthropic sem SDK (mantidos de propósito — ver ADR-004) | — | Feito; dois bugs reais saíram de brinde (ver nota abaixo da tabela) |
| 7 | **Entrega de notificações não implementada** (email/push) e conclusão da revisão semanal não persiste | `modules/notifications/`, `modules/review/` | Features que parecem prontas mas não funcionam de ponta a ponta. Implementar a entrega como jobs do APScheduler (`app/core/scheduler.py`) |
| 8 | Duas camadas de fetch no frontend (react-query em 32 páginas, `useEffect`+axios em 12) e tipagem fraca nos services (`data: unknown`) | `frontend/src/` | Padronizar em react-query + tipar as respostas ao tocar em cada página |
| 9 | Suítes E2E duplicadas (`e2e/*.spec.ts` antigos × `e2e/tests/*.spec.ts` novos rodam ambas × 12 projetos) e zero `data-testid` (seletores por texto PT-BR, frágeis). O diretório `e2e/` está fora do escopo do eslint até essa consolidação | `frontend/e2e/` | E2E lento e quebradiço; consolidar nas specs numeradas, introduzir `data-testid` e reincluir no lint |
| 10 | Makefile é POSIX-only (Linux/Mac/Git Bash) — ~~alvos quebrados~~ os alvos quebrados foram corrigidos/removidos em ago/2026, mas ainda não roda em PowerShell puro | `Makefile` | Prover script PowerShell equivalente ou tasks do VS Code para o time Windows |
| 11 | Rate limit em memória (`memory://`) e uploads em disco local | `app/main.py`, `documents/` | Limitações aceitáveis com 1 réplica (ADR-003/007), mas precisam de aviso em qualquer plano de escala |
| 12 | ~~URL de túnel Cloudflare hardcoded~~ **RESOLVIDO (ago/2026)**: fallback removido; use `VITE_CLOUDFLARE_BACKEND` (ver `frontend/.env.example`, criado na mesma leva) | — | Feito |

**Bugs reais corrigidos na limpeza de ago/2026** (para contexto histórico): (a) o job de automações agendadas do scheduler quebrava em todo disparo — importava um módulo que dependia do Celery (não instalado); (b) `_project_installments` do calendário referenciava um modelo `Installment` que **nunca existiu** (parcelas são `Transaction`s futuras, já contadas pela query principal — o método foi removido); (c) `alert_engine.check_missing_invoices_start_of_month` usava `utc_now()` sem import e quebraria todo dia 1º do mês. Moral: rode o lint — dois desses três eram achados `F821` do ruff.

Antes de atacar qualquer item grande (#2, #3), alinhe com o mantenedor — os relatórios detalhados por especialidade estão em `docs/team-analysis/`.
