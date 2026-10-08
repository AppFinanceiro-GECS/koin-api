# Consumo de IA e limites da licença (#38 / N02)

## Instalação

Aplicar `alembic upgrade head` antes de iniciar a versão nova. A revisão
`add_ai_usage_and_limits` cria `ai_usage`, `ai_daily_budget` e
`license_document_usage`. Nenhuma migração foi aplicada a hml nesta implementação.

`AI_PRICES_FILE` aponta para um JSON versionado. `config/ai_prices.json` contém
tarifas **standard paid** consultadas em 07/10/2026, com URLs das fontes. Os aliases
Mistral `latest` devem ser conferidos contra o modelo/tarifa efetivamente contratado
antes do deploy; atualizar a versão ao alterar preços. Para tier grátis, descontos
ou outros modelos, fornecer outra configuração. Não inferir gratuidade da ausência
de metadados nem aplicar o preço de outro modelo desconhecido.

Valores monetários são calculados com Decimal e persistidos como NUMERIC(20,10).
Gemini: entrada sem cache + entrada com cache + saída + pensamento. Pensamento
é separado da saída, evitando dupla cobrança. OCR Mistral é cobrado por página;
document annotation usa sua tarifa específica. Custo é derivado de uso medido e
tarifa configurada, não substitui a conciliação com a fatura do provider.

## Registros e atribuição

Uma linha por chamada efetiva de extração, OCR, classificação, chat ou lista
inteligente, incluindo retries/fallback e chamadas que falham. Registra usuário,
documento quando aplicável, funcionalidade, provider, modelo pedido/resolvido,
modo de cobrança, tokens, páginas, USD, latência, versão de preço e status.
Não armazena prompts, respostas, senha ou conteúdo financeiro nesta tabela.

O registro de consumo é gravado antes do parsing em uma transação separada. O
documento é persistido antes da chamada paga, preservando sua referência mesmo
se o processamento falhar. Chamadas sem metadados têm custo NULL e status
`unknown_usage`; chamadas interrompidas podem permanecer `pending`.

Ferramentas offline que chamam providers diretamente, sem contexto de usuário,
não entram no relatório. As entradas de aplicação vinculam explicitamente o
usuário, inclusive na tarefa de background; o contexto é isolado por tarefa.

## Limite mensal

A licença compartilha `max_documents_per_month` entre seus membros, por mês UTC.
`None` significa ilimitado; `0` impede envio. Licença inativa também retorna 402.
Usuários legados sem licença mantêm o comportamento anterior, sem cota mensal.

Uploads síncronos, assíncronos, batch, force e retry passam pela mesma reserva.
Batch conta como um documento. Duplicata rejeitada com 409 não consome cota;
reprocessamento aceito consome. Exclusão não devolve cota. A inicialização do
contador considera os documentos já existentes no mês. A reserva e o documento
são transacionais; rejeições anteriores ao aceite não consomem cota.

Resposta: HTTP 402, `detail.error=plan_limit`, mensagem contendo `limite do plano`.
`max_transactions_per_month` não é aplicado nesta mudança: a atividade da #38
solicita especificamente o limite de documentos no upload.

## Disjuntor diário

`AI_DAILY_BUDGET_USD` define o teto global em USD por dia UTC. Vazio desabilita
o teto; `0` bloqueia todas as chamadas. `AI_CALL_RESERVATION_USD` (padrão 0.10)
reserva uma quantia antes de cada tentativa. A atualização condicional é atômica
no banco, compartilhada entre processos; não depende de contador em memória.

Ao concluir, a reserva é substituída pelo custo medido. Consumo desconhecido,
timeout ou crash mantém a reserva conservadora. Reconciliar reservas pendentes
com o provider antes de qualquer liberação operacional; a aplicação não as libera
automaticamente. A virada do dia abre outro contador.

Rejeição: HTTP 429, `detail.error=ai_daily_limit`. Preço ausente/inválido bloqueia
a chamada com 503, `ai_pricing_unavailable`. Esses erros não provocam fallback
ou retry que contorne o disjuntor. A tarefa assíncrona conserva o arquivo e registra
a falha de processamento para consulta.

O disjuntor bloqueia **novas** chamadas. Não cancela chamadas em andamento nem
garante um teto exato na fatura do provider: se uma chamada custar mais que sua
reserva, pode ultrapassar o saldo previsto. Dimensionar a reserva pelo maior
consumo permitido e manter também os limites do projeto no provider (#21).

## Relatório administrativo

`GET /api/v1/admin/ai-usage?from=2026-10-01T00:00:00Z&to=2026-11-01T00:00:00Z&group_by=user`

Somente administradores. `group_by`: `user`, `feature`, `model` (provider e modelo).
Intervalo UTC `[from,to)`; padrão últimos 30 dias. Filtro `document_id` permite
medir uma fatura individual. Paginação por `limit` (até 1000) e `offset`.

Cada grupo informa chamadas, documentos distintos, tokens, páginas, latência
total, custo medido e chamadas sem medição. `cost_usd` e média por documento
ficam NULL quando há consumo desconhecido, evitando apresentar total incompleto
como custo real. Grupos por usuário/modelo podem incluir chat; use `document_id`
para o custo de uma fatura.

## Aceite em hml (pendente)

Após deploy/migração, verificar preço/tier, definir teto diário e assegurar uma
licença de teste com pelo menos 30 envios disponíveis. Usar conta sintética e
credenciais de hml; nunca dados financeiros reais. Fornecer por ambiente
`KOIN_BENCHMARK_USER_TOKEN` e `KOIN_BENCHMARK_ADMIN_TOKEN`.

```powershell
python scripts/benchmark_ai_usage.py --base-url https://HOST-DE-HML --run-live --count 30 --output ai-usage-hml.json
```

O script gera 30 PDFs únicos de 1–3 páginas, envia sequencialmente, aguarda o
resultado e consulta o custo por documento. Salva apenas IDs, status, consumo,
tarifas calculadas e médias. `acceptance_met=true` exige pelo menos 30 documentos
concluídos e todas as chamadas com custo medido. Arquivar o relatório e comparar
com o painel de cobrança. Os testes com respostas simuladas não satisfazem esse
aceite. Esta etapa local não executa o script contra hml.
