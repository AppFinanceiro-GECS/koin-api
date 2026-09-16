# Instruções Específicas para Faturas Nubank

## LAYOUT CARACTERÍSTICO DO NUBANK

### Cabeçalho
- Logo Nubank (roxo)
- "FATURA DD MMM AAAA" (ex: "FATURA 12 MAR 2026")
- Nome do titular e últimos dígitos do cartão
- Período de referência: "DD MMM a DD MMM" (ex: "05 FEV a 05 MAR")

### Seções da Fatura

1. **Resumo** (NÃO EXTRAIR):
   - Valor total da fatura
   - Limite disponível
   - Vencimento

2. **Transações da fatura** (EXTRAIR!):
   - Lista de compras, parcelas e encargos
   - Formato: `DD MMM  Descrição  R$ XX,XX`

3. **"Pagamentos e Financiamentos"** (ATENÇÃO!):
   - ❌ "Pagamento em DD MMM" → NÃO extrair (é crédito de pagamento)
   - ✅ Parcelas de compras (ex: "Amazon.com.br - Parcela 11/12") → EXTRAIR!

## 🚨 INSTRUÇÕES CRÍTICAS

### 1. FORMATO DE DATAS: "DD MMM" (SEM ANO!)

O Nubank mostra datas no formato **"DD MMM"** (ex: "11 FEV", "28 JAN", "01 MAR").

**⚠️ CRÍTICO - COMO DETERMINAR O ANO:**

Use o **invoice_year** e **invoice_month** (derivados do vencimento):

- Se mês da transação <= invoice_month → use **invoice_year**
- Se mês da transação > invoice_month → use **invoice_year - 1**

**EXEMPLO (fatura com vencimento 12/MAR/2026, invoice_month=3, invoice_year=2026):**
```
11 FEV  Loja ABC       R$ 50,00  → FEV (2) <= MAR (3) → 2026-02-11 ✅
28 JAN  Restaurante    R$ 30,00  → JAN (1) <= MAR (3) → 2026-01-28 ✅
01 MAR  Farmácia       R$ 20,00  → MAR (3) <= MAR (3) → 2026-03-01 ✅
15 DEZ  Assinatura     R$ 10,00  → DEZ (12) > MAR (3) → 2025-12-15 ✅
```

**❌ ERRO COMUM:** Usar 2025 para transações de JAN/FEV quando a fatura é de MAR/2026.
- "11 FEV" na fatura MAR/2026 → **2026**-02-11 (CORRETO!)
- "11 FEV" na fatura MAR/2026 → **2025**-02-11 (ERRADO!)

**REGRA DE OURO:** Transações recentes (últimos 1-2 meses) são do MESMO ANO da fatura!

### 2. IOF É ENCARGO POSITIVO (NUNCA NEGATIVO!)

O Nubank mostra IOF em linhas separadas:
```
18 FEV  IOF de 'No-Ip'           R$ 7,61
01 MAR  IOF de 'Www.Artlist.Io'  R$ 4,41
```

**⚠️ REGRAS DO IOF:**
- **transaction_type**: "encargo" (NÃO "credito", NÃO "compra")
- **amount**: SEMPRE **POSITIVO** (IOF é uma TAXA cobrada, não um crédito!)
- **is_installment**: false
- **description**: manter como aparece (ex: "IOF de 'No-Ip'")

**❌ ERRADO:** `{"description": "IOF de 'No-Ip'", "amount": -7.61, "transaction_type": "credito"}`
**✅ CORRETO:** `{"description": "IOF de 'No-Ip'", "amount": 7.61, "transaction_type": "encargo"}`

### 3. PARCELAS NO NUBANK

Parcelas aparecem com formato "Descrição - Parcela X/Y" ou "Descrição X/Y":
```
06 FEV  Mercado Livre - Parcela 2/3    R$ 100,00
06 FEV  Amazon.com.br 11/12            R$ 50,00
```

**Extrair:**
- description: "Mercado Livre" (SEM "- Parcela 2/3")
- installment_current: 2
- installment_total: 3
- is_installment: true

### 4. PAGAMENTOS (NÃO EXTRAIR!)

```
01 MAR  Pagamento em 28 fev          R$ 2.500,00
```

**NÃO extrair!** Isso é o pagamento da fatura anterior.

### 5. MÚLTIPLOS CARTÕES NA MESMA CONTA (NUBANK EMPRESARIAL)

Faturas Nubank empresariais podem ter múltiplos cartões (diferentes finais).
**Extraia TODOS os cartões** que fazem parte da mesma fatura/total.

### 6. MAPEAMENTO DE MESES

Para converter "DD MMM" em data:
- JAN = 01, FEV = 02, MAR = 03, ABR = 04, MAI = 05, JUN = 06
- JUL = 07, AGO = 08, SET = 09, OUT = 10, NOV = 11, DEZ = 12

### 7. CRÉDITOS E ESTORNOS

Estornos no Nubank aparecem com indicação visual (cor diferente) ou texto como:
- "Estorno de..."
- "Crédito..."
- Valores que reduzem o total

**Extrair como:** amount NEGATIVO, transaction_type "estorno" ou "credito"

## RESUMO DA ESTRATÉGIA

Para faturas do Nubank:
1. ✅ Identifique o período e vencimento para determinar invoice_month/invoice_year
2. ✅ Use invoice_year para datas com mês <= invoice_month
3. ✅ Use invoice_year - 1 para datas com mês > invoice_month
4. ✅ IOF = encargo POSITIVO (NUNCA negativo!)
5. ✅ Remova "Parcela X/Y" da descrição, use installment_current/total
6. ✅ NÃO extraia "Pagamento em DD MMM"
7. ✅ Valide: soma deve ser igual ao total_amount
