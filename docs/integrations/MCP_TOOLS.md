# MCP Tools - Koin

O MCP (Model Context Protocol) permite que assistentes de IA como o Claude acessem dados do Koin diretamente, consultando suas financas pessoais de forma segura via API Key.

## Configuracao

1. Copie o arquivo de exemplo:
   ```bash
   cp .mcp.json.example .mcp.json
   ```

2. Gere uma API Key no Koin: **Configuracoes > API Keys**

3. Edite `.mcp.json` e substitua `your-api-key-here` pela sua API Key

4. Certifique-se de que o servidor backend esta rodando em `http://localhost:8000`

## Ferramentas Disponiveis

### `check_connection`
Verifica se a conexao com a API esta funcionando e mostra informacoes do usuario autenticado.

### `list_tables`
Lista todas as tabelas disponiveis para consulta com descricao de cada uma. Util para descobrir quais dados existem no sistema.

### `describe_table`
Mostra a estrutura de uma tabela especifica: colunas e suas descricoes. Use para entender os campos antes de fazer uma consulta.

- **table_name** (obrigatorio): nome da tabela (ex: `transactions`, `accounts`)

### `query`
Consulta dados de uma tabela com filtros, ordenacao e paginacao. Os dados sao automaticamente filtrados pelo usuario autenticado.

- **table** (obrigatorio): nome da tabela
- **filters** (opcional): filtros no formato `{coluna: valor}` (ex: `{"type": "expense", "is_paid": true}`)
- **order_by** (opcional): coluna para ordenacao
- **order_desc** (opcional): se `true`, ordena de forma descendente
- **limit** (opcional): limite de resultados, maximo 1000 (padrao: 100)
- **offset** (opcional): offset para paginacao

### `get_summary`
Retorna um resumo geral dos dados financeiros: contas e saldos, transacoes do mes (despesas/receitas), cartoes de credito, faturas em aberto, metas ativas e dividas.

### `get_table_stats`
Retorna estatisticas de uma tabela: contagem de registros e informacoes das colunas.

- **table_name** (obrigatorio): nome da tabela

## Tabelas Disponiveis

| Tabela | Descricao |
|--------|-----------|
| accounts | Contas financeiras (carteira, banco, cartao, investimento) |
| transactions | Transacoes financeiras (despesas, receitas, transferencias) |
| categories | Categorias para classificar transacoes |
| credit_cards | Cartoes de credito |
| credit_card_invoices | Faturas de cartao de credito |
| installment_series | Series de compras parceladas |
| budgets | Orcamentos mensais |
| budget_items | Itens do orcamento por categoria |
| goals | Metas financeiras |
| goal_contributions | Contribuicoes para metas |
| debts | Dividas |
| debt_payments | Pagamentos de dividas |
| recurring_transactions | Transacoes recorrentes programadas |
| income_sources | Fontes de renda |
| documents | Documentos/comprovantes |
| merchants | Comerciantes identificados |
| receipts | Cupons fiscais/recibos de compras |
| receipt_payments | Pagamentos de recibos (split payment) |
| benefit_cards | Cartoes de beneficio (VA/VR/Flex) |
| grocery_products | Catalogo de produtos de mercado |
| grocery_purchases | Compras de supermercado (itens) |
| grocery_price_history | Historico de precos de produtos |
| shopping_lists | Listas de compras |
| shopping_list_items | Itens da lista de compras |
| spending_envelopes | Envelopes de gastos (estilo YNAB) |
| envelope_history | Historico de envelopes |
| chat_conversations | Conversas do chat com assistente financeiro |
| chat_messages | Mensagens do chat |

## Exemplo de Uso com Claude

Ao usar o Claude com MCP configurado, voce pode fazer perguntas como:

> "Qual foi meu total de gastos este mes?"

O Claude ira automaticamente usar as ferramentas MCP para:
1. Chamar `get_summary` para obter o resumo financeiro
2. Ou chamar `query` na tabela `transactions` com filtros de data e tipo

Outros exemplos:

> "Liste minhas contas e saldos"
> "Quais sao minhas maiores despesas do mes passado?"
> "Quanto ja paguei das minhas dividas?"
> "Qual o status das minhas metas financeiras?"
> "Quanto gastei no cartao de credito este mes?"
