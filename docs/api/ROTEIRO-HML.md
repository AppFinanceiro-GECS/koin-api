# Roteiro de teste da homologação

O que conferir à mão na hml (`https://hml.144-22-232-63.sslip.io`) antes de promover para a produção. É a matriz da auditoria de 30/09, atualizada. Use a coleção `koin/` (ver [README](README.md)) ou o app.

Marque cada linha. Se algo falhar, anote o `request_id` da resposta, que serve para achar a linha exata no log.

## Sessão

| # | Caso | Esperado |
|---|---|---|
| 1 | Login com senha certa | 200 com `access_token` e `refresh_token` |
| 2 | Login com senha errada 5 vezes | 401 nas primeiras; depois 429 com `Retry-After` |
| 3 | Requisição sem token | 401, `code: not_authenticated` |
| 4 | Refresh | Tokens novos; o refresh antigo passa a dar 401 |
| 5 | Reusar um refresh já trocado | 401, e a sessão daquele aparelho cai |
| 6 | Logout e depois refresh | 401 |
| 7 | Trocar a senha logado no celular e no computador | O aparelho que trocou continua; o outro precisa logar de novo |

## Cartão, compras e faturas

| # | Caso | Esperado |
|---|---|---|
| 8 | Criar cartão (fechamento 10, vencimento 17) | 201 |
| 9 | Compra no dia 10 | Fatura do mesmo mês (RN003) |
| 10 | Compra no dia 11 | Fatura do mês seguinte |
| 11 | Cartão que fecha dia 31, compra em 30/abril | Fatura de abril, fechando dia 30 |
| 12 | Compra parcelada 1/10 com parcelas futuras | 10 parcelas, uma por fatura (RN005) |
| 13 | Lançar de novo a parcela 2/10 | Não duplica |
| 14 | Listar transações depois de compra no cartão | 200, com `credit_card_name` (regressão do #33) |
| 15 | Valor 0,001 ou data 2999-01-01 | 422 |
| 16 | Pagar fatura com outro cartão | 400 (RN006) |
| 17 | Pagar parte da fatura e depois o resto | `partial` e depois `paid` (RN010) |
| 18 | Resumo do mês com fatura paga | O pagamento não aparece como despesa (RN008) |

## Envio de fatura (IA)

| # | Caso | Esperado |
|---|---|---|
| 19 | Enviar PDF de fatura (assíncrono) | 202; `stage` vai de `received` a `extracting` e `done` |
| 20 | Enviar foto (PNG, JPEG, HEIC) | Lê do mesmo jeito |
| 21 | Enviar o mesmo arquivo de novo | 409 com o id do original |
| 22 | PDF com senha, sem informar a senha | 422 `password_required` |
| 23 | Arquivo que não é fatura | `failed`, `error_code: unreadable_document`, mensagem em português |
| 24 | IA sem cota (ou com o disjuntor aberto) | `waiting_ai`, `error_code: ai_quota_exhausted`; o documento termina sozinho quando a cota volta (RN016) |
| 25 | `/health` com a IA lenta ou sem cota | `ai: degraded` ou `quota_exhausted` |
| 26 | Nenhuma resposta traz texto cru do Google ou nome de variável | Só mensagens do catálogo |

## Avisos

| # | Caso | Esperado |
|---|---|---|
| 27 | Registrar aparelho (`POST /users/me/devices`) | 200; token inválido dá 422 |
| 28 | Fatura que vence em 3 dias (rode o job ou espere as 9h) | Notificação e push "Fatura vence em 3 dias" |
| 29 | Fatura que vence hoje | "Fatura vence hoje" |
| 30 | Fatura vencida e não paga | "Fatura vencida!" |
| 31 | Upload assíncrono termina com o app fechado | Push "Fatura lida" |
| 32 | Horário silencioso ligado (22h às 7h) | O push segura até as 7h |

## Conta e LGPD

| # | Caso | Esperado |
|---|---|---|
| 33 | Exportar meus dados | JSON com contas, cartões, transações e documentos |
| 34 | Excluir conta com a senha certa | Acesso bloqueado e sessões derrubadas |
| 35 | Ver a fatura ou a transação de outro usuário | 404 |
| 36 | Rotas de admin com usuário comum | 403 |

## Infra

| # | Caso | Esperado |
|---|---|---|
| 37 | `GET /health` | 200 com `db: ok`, `version`, `commit` e `modules` |
| 38 | Erro 500 | JSON com `request_id`, sem a exceção |
| 39 | Header `X-Request-ID` e `X-API-Version` | Presentes em toda resposta |
| 40 | Convite criado pelo admin | Resposta com `invite_url` e `invite_token`; vale 48 h |
| 41 | `make seed-hml` | Usuário demo com 3 meses de dados |
