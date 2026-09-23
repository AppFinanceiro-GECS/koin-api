# AUDIT_REPORT.md - Koin

**Data:** 2026-01-11
**Auditor:** Claude (AI Technical Auditor)
**Versao:** 1.1 (Atualizado com achados do Frontend)

---

## A) Resumo Executivo

### Riscos P0 (Criticos - Resolver Imediatamente)

| ID | Achado | Impacto | Motivo P0 |
|----|--------|---------|-----------|
| AUD-001 | **Erros de tipo mypy criticos em services** | Runtime errors potenciais | `financial_agent_service.py` tem 40+ erros de tipo que podem causar crashes |
| AUD-002 | **pytest nao executa - falta pytest_asyncio** | Zero cobertura de testes | Impossivel rodar testes do backend |
| AUD-003 | **Uploads nao tem cleanup automatico** | Disco cheio em producao | Arquivos acumulam em `uploads/` sem limpeza |
| AUD-004 | **datetime.utcnow() timezone-naive** | Bugs em datas/faturas | Calculos de periodo de fatura podem falhar em fusos diferentes |

### Metricas Gerais

| Categoria | Quantidade | Severidade Media |
|-----------|------------|------------------|
| Bugs (Backend) | 8 | Alta |
| Bugs (Frontend) | 3 | Media |
| Divida Tecnica | 18 | Media |
| Lacunas UX | 8 | Media |
| Seguranca | 4 | Media |
| Performance | 3 | Baixa |
| Observabilidade | 4 | Media |
| Acessibilidade | 5 | Media |

---

## B) Achados por Categoria

### B.1 BUGS

#### AUD-001: Erros de tipo mypy em financial_agent_service.py
- **Tipo:** Bug
- **Prioridade:** P0
- **Esforco:** M
- **Evidencia:** `app/services/financial_agent_service.py:120-314`
- **Descricao:** 40+ erros de tipo incluindo:
  - `Incompatible types in assignment (expression has type "dict[str, Any]", target has type "bool | list[Any] | None")`
  - `Item "bool" of "bool | list[Any] | None" has no attribute "append"`
  - `Unsupported operand types for + ("object" and "float")`
- **Impacto:** Runtime crashes quando Financial Agent e usado
- **Fix sugerido:** Adicionar type hints corretos e corrigir assignmentos

#### AUD-002: pytest nao executa
- **Tipo:** Bug
- **Prioridade:** P0
- **Esforco:** S
- **Evidencia:** `tests/conftest.py:2`
- **Descricao:** `ModuleNotFoundError: No module named 'pytest_asyncio'`
- **Impacto:** Zero cobertura de testes
- **Fix sugerido:** `pip install pytest-asyncio` e adicionar ao requirements.txt

#### AUD-005: Retorno incorreto em transaction_service._create_recurring_from_transaction
- **Tipo:** Bug
- **Prioridade:** P1
- **Esforco:** S
- **Evidencia:** `app/services/transaction_service.py:104`
- **Descricao:** Funcao retorna `None` quando ja existe recorrente, mas tipo de retorno e `RecurringTransaction`
- **Impacto:** mypy error `Incompatible return value type (got "None", expected "RecurringTransaction")`
- **Fix sugerido:** Mudar retorno para `RecurringTransaction | None`

#### AUD-006: Undefined names em models/transaction.py
- **Tipo:** Bug
- **Prioridade:** P1
- **Esforco:** S
- **Evidencia:** `app/models/transaction.py:97-98`
- **Descricao:** flake8 F821 - `undefined name 'CreditCard'` e `undefined name 'IncomeSource'`
- **Impacto:** Pode causar erros em runtime se esses relationships forem acessados
- **Fix sugerido:** Adicionar imports com TYPE_CHECKING ou usar strings

#### AUD-007: email_service.py parametro opcional incorreto
- **Tipo:** Bug
- **Prioridade:** P2
- **Esforco:** S
- **Evidencia:** `app/services/email_service.py:180`
- **Descricao:** `Incompatible default for argument "text_content" (default has type "None", argument has type "str")`
- **Impacto:** Type error, envio de email pode falhar
- **Fix sugerido:** Mudar para `text_content: str | None = None`

#### AUD-008: recurring.py acessa atributos de None
- **Tipo:** Bug
- **Prioridade:** P1
- **Esforco:** S
- **Evidencia:** `app/routers/recurring.py:28-46`
- **Descricao:** mypy: `Item "None" of "RecurringTransaction | None" has no attribute "id"`
- **Impacto:** Runtime error se recorrente nao for encontrada
- **Fix sugerido:** Adicionar verificacao de None antes de acessar atributos

---

### B.2 DIVIDA TECNICA

#### AUD-010: ESLint sem configuracao no frontend
- **Tipo:** Divida Tecnica
- **Prioridade:** P2
- **Esforco:** S
- **Evidencia:** `frontend/` - arquivo `.eslintrc` nao existe
- **Descricao:** `npm run lint` falha com "ESLint couldn't find a configuration file"
- **Impacto:** Sem linting no frontend, codigo pode ter problemas de estilo
- **Fix sugerido:** Criar `.eslintrc.cjs` com config para React+TS

#### AUD-011: Imports nao usados (F401) - 20+ ocorrencias
- **Tipo:** Divida Tecnica
- **Prioridade:** P3
- **Esforco:** S
- **Evidencia:** Multiplos arquivos em `app/`
- **Exemplos:**
  - `main.py:8` - `slowapi._rate_limit_exceeded_handler`
  - `main.py:12` - `.core.database.Base`
  - `routers/auth.py:1-16` - 6 imports nao usados
- **Impacto:** Codigo mais pesado, confuso
- **Fix sugerido:** Remover imports nao usados

#### AUD-012: Imports nao no topo do arquivo (E402) - 70+ ocorrencias
- **Tipo:** Divida Tecnica
- **Prioridade:** P3
- **Esforco:** M
- **Evidencia:** Todos os arquivos em `app/models/`
- **Descricao:** Imports no final dos arquivos para evitar circular imports
- **Impacto:** Padrao de codigo nao convencional
- **Fix sugerido:** Aceitar como padrao do projeto (circular imports) ou refatorar relationships

#### AUD-013: ocr_service.py legado
- **Tipo:** Divida Tecnica
- **Prioridade:** P2
- **Esforco:** S
- **Evidencia:** `app/services/ocr_service.py`
- **Descricao:** Servico substituido por `llm_ocr_service.py`, funcao `extract_financial_data()` nao e usada
- **Impacto:** Codigo morto, confusao
- **Fix sugerido:** Remover arquivo ou marcar como deprecated

#### AUD-014: Variavel assignada mas nao usada
- **Tipo:** Divida Tecnica
- **Prioridade:** P3
- **Esforco:** S
- **Evidencia:** `app/main.py:169` - `local variable 'conn' is assigned to but never used`
- **Fix sugerido:** Usar `_` ou remover

#### AUD-015: Comparacoes com True/False incorretas
- **Tipo:** Divida Tecnica
- **Prioridade:** P3
- **Esforco:** S
- **Evidencia:**
  - `routers/admin.py:51,54` - E712
  - `routers/categories.py:55` - E712
- **Descricao:** `comparison to True should be 'if cond is True:' or 'if cond:'`
- **Fix sugerido:** Usar `if cond:` em vez de `if cond == True:`

#### AUD-016: Falta stubs para dateutil
- **Tipo:** Divida Tecnica
- **Prioridade:** P3
- **Esforco:** S
- **Evidencia:** Multiplos services - `import-untyped` errors
- **Fix sugerido:** `pip install types-python-dateutil`

---

### B.3 SEGURANCA

#### AUD-020: Rate limit nao granular por endpoint
- **Tipo:** Seguranca
- **Prioridade:** P1
- **Esforco:** M
- **Evidencia:** `app/core/rate_limit.py` + `main.py`
- **Descricao:** Rate limit global configurado, mas endpoints sensiveis (login, OCR) nao tem limites especificos
- **Impacto:** Brute force em login, abuso de API de OCR (custosa)
- **Fix sugerido:** Adicionar `@limiter.limit("5/minute")` em endpoints criticos

#### AUD-021: Soft delete nao implementado
- **Tipo:** Seguranca
- **Prioridade:** P2
- **Esforco:** L
- **Evidencia:** Todos os models usam delete real
- **Descricao:** Transacoes, faturas e documentos sao deletados permanentemente
- **Impacto:** Dados irrecuperaveis, sem audit trail completo
- **Fix sugerido:** Adicionar campo `deleted_at` e filtrar em queries

#### AUD-022: Validacao de tamanho de upload pode ser bypassada
- **Tipo:** Seguranca
- **Prioridade:** P2
- **Esforco:** S
- **Evidencia:** `app/services/document_service.py:32-37`
- **Descricao:** Validacao ocorre apos `await file.read()` - arquivo ja foi carregado em memoria
- **Impacto:** Memory exhaustion attack possivel
- **Fix sugerido:** Usar streaming e validar tamanho antes de carregar todo

---

### B.4 LACUNAS UX

#### AUD-030: 409 Conflict sem acao clara para usuario
- **Tipo:** Lacuna UX
- **Prioridade:** P2
- **Esforco:** M
- **Evidencia:** `frontend/src/pages/Upload.tsx` - tratamento de erro generico
- **Descricao:** Quando backend retorna 409 (duplicata), UI mostra mensagem mas nao oferece acao clara (ex: "Ver transacao existente" ou "Forcar duplicata")
- **Impacto:** Usuario confuso sobre como resolver
- **Fix sugerido:** Adicionar botao "Ver existente" ou "Adicionar mesmo assim"

#### AUD-031: 429 Rate Limit sem retry/backoff
- **Tipo:** Lacuna UX
- **Prioridade:** P2
- **Esforco:** M
- **Evidencia:** `frontend/src/services/api.ts`
- **Descricao:** Sem interceptor para tratar 429 com retry automatico
- **Impacto:** Usuario ve erro generico
- **Fix sugerido:** Adicionar interceptor axios com exponential backoff

#### AUD-032: Falta mascaras de input em valores monetarios
- **Tipo:** Lacuna UX
- **Prioridade:** P3
- **Esforco:** M
- **Evidencia:** LOGIC_MAP.md secao 6.3 - "Mascaras: Nao detectado - Ponta solta"
- **Impacto:** Usuario pode digitar formatos invalidos
- **Fix sugerido:** Usar biblioteca como react-number-format

#### AUD-033: Loading state incompleto em algumas telas
- **Tipo:** Lacuna UX
- **Prioridade:** P3
- **Esforco:** S
- **Evidencia:** Algumas telas usam apenas spinner generico
- **Fix sugerido:** Usar skeletons consistentes

---

### B.5 PERFORMANCE

#### AUD-040: N+1 queries em list_invoices
- **Tipo:** Performance
- **Prioridade:** P2
- **Esforco:** M
- **Evidencia:** `app/routers/invoices.py:88-120`
- **Descricao:** Para cada fatura, faz 3 queries adicionais (nome cartao, nome conta, contagem transacoes)
- **Impacto:** Lentidao com muitas faturas
- **Fix sugerido:** Usar JOINs ou eager loading

#### AUD-041: Falta paginacao em algumas listas
- **Tipo:** Performance
- **Prioridade:** P3
- **Esforco:** M
- **Evidencia:** Algumas queries tem limite fixo de 50-100
- **Impacto:** Performance com muitos dados
- **Fix sugerido:** Implementar cursor-based pagination

---

### B.7 PONTAS SOLTAS DE NEGOCIO (CRITICO)

#### AUD-060: Job de atualizacao de status de faturas nao implementado
- **Tipo:** Ponta Solta / Regra de Negocio Incompleta
- **Prioridade:** P1
- **Esforco:** M
- **Evidencia:** `app/services/invoice_service.py:421-468` - `update_invoice_statuses()`
- **Descricao:** Funcao que atualiza status das faturas (OPEN→CLOSED→OVERDUE) existe mas:
  - **NAO e chamada automaticamente** (sem cron/celery/scheduler)
  - Endpoint `PUT /invoices/update-statuses` existe mas precisa ser chamado manualmente
  - Faturas podem ficar com status incorreto indefinidamente
- **Impacto:**
  - Faturas abertas nunca fecham automaticamente
  - Faturas vencidas nao sao marcadas como OVERDUE
  - Dashboard/Analytics podem mostrar dados incorretos
- **Fix sugerido:**
  1. Implementar job com APScheduler ou Celery Beat
  2. OU chamar no endpoint de listagem de faturas (lazy update)

#### AUD-061: Projecao de recorrentes para faturas futuras nao automatizada
- **Tipo:** Ponta Solta / Regra de Negocio Incompleta
- **Prioridade:** P1
- **Esforco:** M
- **Evidencia:** `app/services/invoice_service.py:655-775` - `project_recurring_to_invoices()`
- **Descricao:** Funcao que projeta transacoes recorrentes para faturas futuras existe mas:
  - **NAO e chamada automaticamente**
  - Nenhum endpoint expoe essa funcionalidade
  - Recorrentes nao aparecem nas faturas futuras
- **Impacto:**
  - Usuario nao consegue ver projecao de gastos futuros
  - Planejamento financeiro comprometido
- **Fix sugerido:** Adicionar endpoint + chamar ao criar recorrente ou ao visualizar fatura futura

#### AUD-062: Cleanup de uploads nao implementado
- **Tipo:** Ponta Solta / Operacional
- **Prioridade:** P0
- **Esforco:** M
- **Evidencia:** `uploads/` - diretorio com subpastas por user_id
- **Descricao:** Arquivos PDF/imagens uploadados ficam no servidor indefinidamente
  - Nao ha job de limpeza
  - Nao ha politica de retencao
  - Disco pode encher em producao
- **Impacto:** Disco cheio, custos de storage
- **Fix sugerido:**
  1. Comando `make cleanup-uploads` que remove arquivos > 30 dias
  2. OU mover para S3/storage externo com lifecycle policy

#### AUD-063: datetime.utcnow() timezone-naive em todo o codigo
- **Tipo:** Bug de Negocio / Datas
- **Prioridade:** P1
- **Esforco:** M
- **Evidencia:**
  - `invoice_service.py:313` - `invoice.paid_at = datetime.utcnow()`
  - `transaction_service.py:*` - multiplas ocorrencias
  - `auth.py:*` - token expiration
- **Descricao:** Uso de `datetime.utcnow()` cria objetos timezone-naive
- **Impacto:**
  - Calculos de periodo de fatura podem errar em fusos diferentes
  - Comparacoes de data podem falhar
  - Inconsistencia com banco PostgreSQL (timezone-aware)
- **Fix sugerido:** Usar `datetime.now(timezone.utc)` ou `pendulum`

#### AUD-064: Transacoes projetadas (is_paid=false) sem confirmacao clara
- **Tipo:** Regra de Negocio / UX
- **Prioridade:** P2
- **Esforco:** M
- **Evidencia:**
  - `transaction_service.py:313-334` - `_find_matching_projected_transaction()`
  - `Upload.tsx:103-156` - checkProjected useEffect
- **Descricao:** Fluxo de confirmacao de transacoes projetadas:
  1. Parcelas futuras sao criadas com `is_paid=false`
  2. Quando PDF real chega, tenta fazer match
  3. **Match usa tolerancia de valor (5%) e data (±45 dias)**
  4. Se match, atualiza transacao existente em vez de criar duplicata
- **Pontos de atencao:**
  - Match pode falhar se descricao mudar (ex: "NETFLIX" vs "NETFLIX.COM")
  - Usuario nao tem visibilidade clara de quais projetadas foram confirmadas
- **Sugestao:** Adicionar log/historico de confirmacoes

#### AUD-065: Regra de deduplicacao RN004 pode gerar falsos positivos
- **Tipo:** Regra de Negocio
- **Prioridade:** P2
- **Esforco:** S
- **Evidencia:** `transaction_service.py:168-197` - verificacao de duplicata
- **Descricao:** Deduplicacao usa: `description + amount + date + user_id`
- **Problema:** Duas compras legitimas no mesmo dia, mesmo valor, mesmo estabelecimento serao bloqueadas
- **Exemplo:** Duas compras de R$50 no iFood no mesmo dia
- **Mitigacao existente:** `force_duplicate=true` no payload
- **Sugestao:** Adicionar window de tempo (ex: 5 minutos) ou usar document_id como parte da chave

#### AUD-066: Pagamento parcial de fatura nao atualiza corretamente
- **Tipo:** Regra de Negocio
- **Prioridade:** P2
- **Esforco:** S
- **Evidencia:** `invoice_service.py:311-321` - pay_invoice
- **Descricao:** Quando faz pagamento parcial:
  ```python
  invoice.paid_amount = (invoice.paid_amount or 0) + amount
  invoice.payment_transaction_id = payment_transaction.id  # Sobrescreve!
  ```
- **Problema:** Apenas a ULTIMA transacao de pagamento e referenciada
- **Impacto:** Se fizer 2 pagamentos parciais, so o ultimo fica vinculado
- **Fix sugerido:** Usar lista de payment_transaction_ids ou tabela N:N

#### AUD-067: Exclusao de fatura pode deixar transacoes orfas
- **Tipo:** Regra de Negocio / Integridade
- **Prioridade:** P2
- **Esforco:** S
- **Evidencia:** `invoice_service.py:554-600` - delete_invoice
- **Descricao:** Opcao `delete_transactions=false` desvincula transacoes:
  ```python
  transaction.invoice_id = None
  ```
- **Problema:** Transacoes de cartao de credito sem invoice ficam "perdidas" - nao aparecem em nenhuma fatura
- **Impacto:** Analytics podem contar errado (transacoes sem invoice nao sao consideradas como cartao)
- **Fix sugerido:** Ao desvincular, recalcular invoice baseado na data da transacao

---

### B.8 INCONSISTENCIAS FRONT x BACK

#### AUD-070: Campo invoice_id pode ser alterado diretamente
- **Tipo:** Inconsistencia / Seguranca
- **Prioridade:** P2
- **Esforco:** S
- **Evidencia:**
  - Frontend: `Invoices.tsx:138-148` - moveTransactionMutation chama `transactionsApi.update(id, {invoice_id})`
  - Backend: `routers/transactions.py` - aceita invoice_id no update
- **Problema:** Usuario pode mover transacao para fatura de outro mes sem recalculo de periodo
- **Impacto:** Fatura com transacoes de periodos incorretos
- **Fix sugerido:** Validar se invoice pertence ao periodo correto no backend

#### AUD-071: create_future_installments nao tem limite maximo
- **Tipo:** Regra de Negocio / Performance
- **Prioridade:** P2
- **Esforco:** S
- **Evidencia:** `installment_service.py:317-402` - create_future_installments
- **Descricao:** Se usuario criar parcela 1/99, vai criar 98 transacoes futuras
- **Impacto:** Pode sobrecarregar banco e UI
- **Fix sugerido:** Limitar a 48 parcelas (4 anos) ou validar no frontend

#### AUD-072: Tolerancia de match de parcelas pode conflitar
- **Tipo:** Regra de Negocio
- **Prioridade:** P3
- **Esforco:** M
- **Evidencia:**
  - `installment_service.py:19-89` - find_matching_series (tolerancia 5% valor, ±45 dias)
  - `transaction_service.py:383-405` - _find_matching_projected_transaction
- **Descricao:** Duas series de parcelas similares (mesmo valor, mesmo merchant) podem fazer match errado
- **Exemplo:**
  - Compra A: MAGAZINELUIZA 10x R$100 (01/jan)
  - Compra B: MAGAZINELUIZA 10x R$100 (15/jan)
  - Parcela 2 da compra B pode fazer match com serie da compra A
- **Fix sugerido:** Adicionar mais criterios de match (ex: card_id, primeiro valor da serie)

---

### B.9 ENDPOINTS SEM CONSUMIDOR / CODIGO MORTO

#### AUD-080: ocr_service.py - servico legado
- **Tipo:** Codigo Morto
- **Prioridade:** P3
- **Esforco:** S
- **Evidencia:** `app/services/ocr_service.py`
- **Descricao:** Servico de OCR tradicional (Tesseract) substituido por `llm_ocr_service.py`
- **Funcao nao usada:** `extract_financial_data()` linha 187
- **Fix sugerido:** Remover arquivo ou manter como fallback documentado

#### AUD-081: Endpoint project_recurring nao exposto
- **Tipo:** Funcionalidade Incompleta
- **Prioridade:** P2
- **Esforco:** S
- **Evidencia:** `invoice_service.py:655` - `project_recurring_to_invoices()` existe mas nao tem endpoint
- **Fix sugerido:** Criar `POST /invoices/project-recurring` ou chamar automaticamente

#### AUD-082: financial_agent_service com erros de tipo
- **Tipo:** Codigo Problematico
- **Prioridade:** P1
- **Esforco:** M
- **Evidencia:** `app/services/financial_agent_service.py` - 40+ erros mypy
- **Descricao:** Agente de IA financeiro tem muitos erros de tipo que podem causar crashes
- **Fix sugerido:** Corrigir tipos ou desabilitar funcionalidade ate correcao

---

### B.6 OBSERVABILIDADE

#### AUD-050: Logs insuficientes em fluxo de OCR
- **Tipo:** Observabilidade
- **Prioridade:** P2
- **Esforco:** M
- **Evidencia:** `app/services/llm_ocr_service.py`
- **Descricao:** Logging basico, mas falta:
  - Tempo de resposta da API externa
  - Quantidade de tokens usados
  - Taxa de sucesso/falha
- **Impacto:** Dificil diagnosticar problemas e otimizar custos
- **Fix sugerido:** Adicionar structured logging com metricas

#### AUD-051: Sem rastreabilidade document -> transactions
- **Tipo:** Observabilidade
- **Prioridade:** P3
- **Esforco:** S
- **Evidencia:** `transaction.document_id` existe mas nao ha endpoint para ver "transacoes de um documento"
- **Fix sugerido:** Adicionar endpoint `/documents/{id}/transactions`

---

## C) Backlog Priorizado

### P0 - Criticos (Sprint 1) - ESTABILIDADE

| ID | Achado | Esforco | Dependencias | Risco |
|----|--------|---------|--------------|-------|
| AUD-002 | pytest nao executa (falta pytest_asyncio) | S | - | Zero testes |
| AUD-062 | Cleanup de uploads nao implementado | M | - | Disco cheio |
| AUD-001 | Erros tipo financial_agent_service | M | - | Crashes |
| AUD-063 | datetime.utcnow() timezone-naive | M | - | Bugs de data |

### P1 - Alta Prioridade (Sprint 2) - REGRAS DE NEGOCIO

| ID | Achado | Esforco | Dependencias | Risco |
|----|--------|---------|--------------|-------|
| AUD-060 | Job de status de faturas nao existe | M | - | Dados incorretos |
| AUD-061 | Projecao de recorrentes nao automatizada | M | - | Feature incompleta |
| AUD-082 | financial_agent_service erros mypy | M | AUD-001 | Crashes |
| AUD-066 | Pagamento parcial sobrescreve referencia | S | - | Dados perdidos |
| AUD-020 | Rate limit nao granular | M | - | Seguranca |
| AUD-005 | Retorno None em create_recurring | S | - | Bug |
| AUD-006 | Undefined names transaction.py | S | - | Bug |

### P2 - Media Prioridade (Sprint 3) - CONSISTENCIA

| ID | Achado | Esforco | Dependencias | Risco |
|----|--------|---------|--------------|-------|
| AUD-064 | Transacoes projetadas sem visibilidade | M | - | UX confusa |
| AUD-065 | Deduplicacao falsos positivos | S | - | UX frustrante |
| AUD-067 | Exclusao fatura deixa orfas | S | - | Dados inconsistentes |
| AUD-070 | invoice_id alteravel sem validacao | S | - | Integridade |
| AUD-071 | Parcelas sem limite maximo | S | - | Performance |
| AUD-040 | N+1 queries invoices | M | - | Performance |
| AUD-081 | Endpoint project_recurring faltando | S | AUD-061 | Feature incompleta |
| AUD-080 | ocr_service.py codigo morto | S | - | Confusao |

### P3 - Baixa Prioridade (Backlog) - POLISH

| ID | Achado | Esforco | Dependencias | Risco |
|----|--------|---------|--------------|-------|
| AUD-072 | Match de parcelas pode conflitar | M | - | Edge case |
| AUD-050 | Logs OCR insuficientes | M | - | Debug dificil |
| AUD-011 | Imports nao usados (F401) | S | - | Limpeza |
| AUD-015 | Comparacoes True/False | S | - | Estilo |
| AUD-041 | Paginacao cursor-based | M | - | Escalabilidade |

---

## D) Milestones

### Sprint 1 (Estabilidade - 1 semana)
**Objetivo:** Sistema funcionando sem crashes, testes rodando, riscos operacionais mitigados

**Tarefas:**
1. **AUD-002:** Instalar pytest-asyncio + rodar testes existentes
2. **AUD-062:** Implementar cleanup de uploads:
   - Comando `make cleanup-uploads` que remove arquivos > 30 dias
   - Adicionar ao cron de deploy ou documentar procedimento
3. **AUD-001:** Corrigir erros de tipo em `financial_agent_service.py`:
   - Adicionar type hints corretos
   - Corrigir assignments incompativeis
4. **AUD-063:** Substituir `datetime.utcnow()` por `datetime.now(timezone.utc)`:
   - Criar helper `utc_now()` em `core/utils.py`
   - Substituir todas as ocorrencias

**Entregaveis:**
- `make test` passa
- mypy tem < 20 erros
- Script de cleanup funcional

---

### Sprint 2 (Regras de Negocio - 1 semana)
**Objetivo:** Completar funcionalidades criticas de negocio, corrigir bugs

**Tarefas:**
1. **AUD-060:** Implementar atualizacao automatica de status de faturas:
   - Opcao A: Job com APScheduler (executar diariamente)
   - Opcao B: Lazy update no endpoint de listagem
   - Adicionar teste unitario para transicoes de status

2. **AUD-061:** Expor projecao de recorrentes:
   - Criar endpoint `POST /api/v1/credit-cards/{id}/project-recurring`
   - Chamar quando usuario visualiza fatura futura
   - Adicionar botao "Projetar recorrentes" no frontend (opcional)

3. **AUD-066:** Corrigir pagamento parcial de fatura:
   - Mudar `payment_transaction_id` para `payment_transaction_ids: list` (JSON)
   - OU criar tabela `invoice_payments` (melhor para auditoria)

4. **AUD-005/006:** Corrigir bugs de tipo:
   - `_create_recurring_from_transaction` retornar `Optional[RecurringTransaction]`
   - Adicionar imports corretos em `transaction.py`

5. **AUD-020:** Rate limit granular:
   - `/auth/login`: 5/minuto
   - `/documents`: 10/minuto (OCR e caro)

**Entregaveis:**
- Faturas atualizam status automaticamente
- Recorrentes aparecem em faturas futuras
- Pagamentos parciais funcionam corretamente

---

### Sprint 3 (Consistencia e Integridade - 1 semana)
**Objetivo:** Garantir integridade de dados, melhorar UX de fluxos criticos

**Tarefas:**
1. **AUD-067:** Corrigir exclusao de fatura:
   - Ao desvincular transacoes, recalcular invoice baseado na data
   - Adicionar confirmacao no frontend antes de excluir

2. **AUD-070:** Validar invoice_id no update de transacao:
   - Backend deve verificar se invoice pertence ao periodo correto
   - Retornar erro 400 se periodo nao bate

3. **AUD-071:** Limitar parcelas:
   - Maximo 48 parcelas (4 anos)
   - Validar no frontend e backend

4. **AUD-064:** Melhorar visibilidade de transacoes projetadas:
   - Adicionar badge "Confirmado em DD/MM" quando match acontece
   - Log de historico de confirmacoes

5. **AUD-040:** Otimizar N+1 queries em invoices:
   - Usar JOINs ou eager loading
   - Medir tempo antes/depois

**Entregaveis:**
- Integridade de dados garantida
- Performance de listagem de faturas melhorada
- Usuario tem visibilidade de confirmacoes

---

### Testes Sugeridos por Sprint

**Sprint 1:**
```python
# test_infrastructure.py
def test_pytest_runs():
    assert True

def test_utc_now_is_timezone_aware():
    from app.core.utils import utc_now
    from datetime import timezone
    assert utc_now().tzinfo == timezone.utc
```

**Sprint 2:**
```python
# test_invoice_service.py
async def test_update_invoice_statuses_transitions():
    # OPEN -> CLOSED apos closing_date
    # CLOSED -> OVERDUE apos due_date
    pass

async def test_pay_invoice_partial_multiple_times():
    # Pagar 50%, pagar mais 30%, verificar status PARTIAL
    # Pagar restante, verificar status PAID
    pass

async def test_project_recurring_creates_future_transactions():
    # Criar recorrente, projetar 6 meses, verificar transacoes
    pass
```

**Sprint 3:**
```python
# test_transactions.py
async def test_update_transaction_validates_invoice_period():
    # Transacao de Jan nao pode ir para fatura de Mar
    pass

async def test_create_installments_max_limit():
    # Parcela 1/100 deve falhar (limite 48)
    pass
```

**E2E (Playwright):**
```typescript
// upload-confirm.spec.ts
test('upload PDF and confirm transactions', async ({ page }) => {
  // Upload PDF
  // Selecionar cartao
  // Confirmar itens
  // Verificar transacoes criadas
  // Verificar fatura atualizada
})

// pay-invoice.spec.ts
test('pay invoice creates expense transaction', async ({ page }) => {
  // Abrir fatura
  // Clicar pagar
  // Selecionar conta
  // Confirmar
  // Verificar status PAID
  // Verificar saldo da conta
})
```

---

## Apendice: Comandos de Verificacao

```bash
# Backend linting
cd backend
source venv/bin/activate
flake8 app --max-line-length=120 --ignore=E501,W503
mypy app --ignore-missing-imports

# Backend tests (apos instalar pytest-asyncio)
pytest

# Frontend type check
cd frontend
npx tsc --noEmit

# Frontend lint (apos criar .eslintrc)
npm run lint
```

---

## Apendice: Arquivos Criticos por Fluxo

### Fluxo Upload + OCR + Confirm
```
frontend/src/pages/Upload.tsx
  -> frontend/src/services/api.ts (documentsApi.upload)
  -> app/routers/documents.py (POST /)
  -> app/services/document_service.py (upload)
  -> app/services/llm_ocr_service.py (extract_from_image)
  -> app/services/transaction_service.py (confirm_from_document)
  -> app/services/installment_service.py (create_series, create_future)
  -> app/services/invoice_service.py (get_or_create_invoice)
```

### Fluxo Pagamento de Fatura
```
frontend/src/pages/Invoices.tsx
  -> frontend/src/services/api.ts (invoicesApi.pay)
  -> app/routers/invoices.py (POST /{id}/pay)
  -> app/services/invoice_service.py (pay_invoice)
  -> RN006: Valida account.type != credit_card
  -> RN008: Analytics exclui payment_transaction_id
```

### Fluxo Recorrentes + Projecoes
```
app/services/transaction_service.py (_create_recurring_from_transaction)
app/services/invoice_service.py (project_recurring_to_invoices)
app/services/transaction_service.py (_find_matching_projected_transaction)
```

---

*Relatorio gerado automaticamente. Revisao humana recomendada antes de executar fixes.*
