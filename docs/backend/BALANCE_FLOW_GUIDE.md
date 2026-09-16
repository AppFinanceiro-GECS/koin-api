# 💰 Guia Completo: Fluxo de Saldo de Benefícios

## 🎯 Filosofia do Sistema

**IMPORTANTE:** O sistema **NÃO bloqueia** débitos quando o saldo fica negativo.

### Por quê?

O **saldo real está no cartão físico** (Alelo, Sodexo, VR, etc.), não no sistema.

**Cenário comum:**
```
Sistema mostra: R$ 0,00 (erro de lançamento)
Cartão físico tem: R$ 400,00
Usuário faz compra: R$ 150,00 ✅ DEVE PERMITIR!

Motivo: O cartão físico aprovou a transação
```

**Solução implementada:**
1. ✅ Permite débitos mesmo com saldo negativo
2. ✅ Registra ALERTAS quando isso acontece
3. ✅ Fornece endpoint para AJUSTAR saldo manualmente

---

## 📊 Fluxo Completo de Saldo

### 1. Criação de Cartão Benefício

```
POST /api/v1/benefit-cards
{
  "name": "Vale Alimentação Alelo",
  "card_type": "va",
  "initial_balance": 500.00  ← Saldo inicial
}

Resultado:
┌─────────────────────────────┐
│ Account                     │
│ balance = 500.00            │ ← Base para cálculo
└─────────────────────────────┘
```

### 2. Confirmação de Recibo (Compra)

```
POST /api/v1/receipts/confirm
{
  "payments": [
    {
      "account_id": 10,  ← Conta do VA
      "amount": 150.00,
      "is_installment": false
    }
  ]
}

Fluxo Interno:
┌─────────────────────────────────────────┐
│ 1. Verificar saldo                      │
│    check_negative_balance()             │
│    ├─ current: 500                      │
│    ├─ debit: 150                        │
│    └─ result: 350 ✓ OK                  │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 2. Realizar débito (SEMPRE)             │
│    account.balance = 500 - 150 = 350    │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 3. Criar ReceiptPayment                 │
│    amount = 150 (registro histórico)    │
└─────────────────────────────────────────┘

Saldo exibido = account.balance + tx_balance - receipt_total
              = 350 + 0 - 150
              = 200 ✓ Correto
```

### 3. Compra com Saldo Insuficiente no Sistema

```
Situação:
- Sistema: balance = 50
- Cartão físico: R$ 400 (usuário sabe que tem)
- Compra: R$ 150

POST /api/v1/receipts/confirm
{
  "payments": [{"account_id": 10, "amount": 150.00}]
}

Fluxo:
┌─────────────────────────────────────────┐
│ 1. Verificar saldo                      │
│    ├─ current: 50                       │
│    ├─ debit: 150                        │
│    └─ result: -100 ⚠️ NEGATIVO          │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 2. ALERTAR (não bloqueia!)              │
│    ⚠️ "Saldo ficará negativo..."        │
│    📝 Log de auditoria registrado       │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 3. Realizar débito (PERMITE)            │
│    account.balance = 50 - 150 = -100    │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 4. Criar ReceiptPayment                 │
│    ✅ Transação registrada              │
└─────────────────────────────────────────┘

Log gerado:
⚠️ Saldo ficará negativo na conta 'VA Alelo':
   R$ 50,00 - R$ 150,00 = R$ -100,00.
   Verifique se o saldo do cartão físico está correto.
```

### 4. Ajuste Manual de Saldo

```
Quando o saldo do sistema diverge do cartão físico:

POST /api/v1/benefit-cards/{card_id}/adjust-balance
{
  "adjustment_amount": 450.00,  ← +450 para corrigir
  "reason": "Saldo real no cartão Alelo é R$ 400"
}

Fluxo:
┌─────────────────────────────────────────┐
│ 1. Saldo atual no sistema: -100        │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 2. Aplicar ajuste                       │
│    -100 + 450 = 350                     │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 3. Criar Transaction de auditoria       │
│    type: INCOME                         │
│    amount: 450                          │
│    description: "Ajuste de saldo: ..."  │
│    tags: ["ajuste_saldo"]               │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 4. Atualizar account.balance            │
│    balance = 350                        │
└─────────────────────────────────────────┘

Response:
{
  "old_balance": -100.00,
  "adjustment": 450.00,
  "new_balance": 350.00,
  "transaction_id": 123,
  "reason": "Saldo real no cartão Alelo é R$ 400",
  "timestamp": "2026-02-03T12:30:00"
}
```

---

## 🔍 Cálculo de Saldo (Dinâmico)

### Fórmula Atual

```sql
Saldo Exibido = account.balance
              + transaction_balance
              - receipt_total

Onde:
  account.balance = Base (pode ser negativo)
  transaction_balance = SUM(incomes) - SUM(expenses) ± SUM(transfers)
  receipt_total = SUM(receipt_payments confirmados)
```

### Exemplo Completo

```
Cartão: VA Alelo (account_id = 10)

Histórico:
1. Criação: balance = 500
2. Recarga: +600 (transaction income)
3. Compra supermercado: -150 (receipt payment)
4. Compra farmácia: -200 (receipt payment)
5. Ajuste manual: +50 (transaction income - ajuste)

Cálculo:
┌──────────────────────────────────────┐
│ account.balance = 500 (inicial)      │
│                 + 600 (recarga)      │
│                 + 50 (ajuste)        │
│                 = 1150               │
├──────────────────────────────────────┤
│ transaction_balance = +650           │
│   (600 recarga + 50 ajuste)          │
├──────────────────────────────────────┤
│ receipt_total = 350                  │
│   (150 + 200)                        │
├──────────────────────────────────────┤
│ SALDO FINAL = 1150 + 650 - 350       │
│             = 1450 ❌ ERRADO         │
└──────────────────────────────────────┘

PROBLEMA: Dupla contagem!
```

### ⚠️ Problema Identificado: Dupla Dedução

O sistema tem um **bug de design**:

1. **Linha 217** (receipt_service.py): `account.balance -= amount`
2. **Cálculo dinâmico**: `- receipt_total`

**Resultado:** Débito é contado DUAS VEZES!

---

## 💡 Soluções Propostas

### Opção A: Não Modificar account.balance em Receipts (RECOMENDADO)

```python
# receipt_service.py:217
# REMOVER esta linha:
account.balance = float(account.balance) - float(payment_data.amount)

# Manter apenas:
# - Criação do ReceiptPayment
# - Cálculo dinâmico já subtrai receipt_total
```

**Vantagens:**
- Elimina dupla dedução
- Um único ponto de verdade (receipt_total)
- Saldo sempre correto

**Desvantagens:**
- account.balance para de refletir saldo atual
- Precisa confiar 100% no cálculo dinâmico

### Opção B: Não Subtrair receipt_total no Cálculo

```python
# benefit_cards router (linha 168)
# MUDAR de:
current_balance = account.balance + tx_balance - receipt_total

# PARA:
current_balance = account.balance + tx_balance
```

**Vantagens:**
- account.balance sempre reflete saldo atual
- Mais simples de entender

**Desvantagens:**
- Perde rastreabilidade de receipts vs transações normais

### Opção C: Usar account.balance APENAS como Base Inicial

```python
# Fórmula atual ESTÁ CORRETA se:
# account.balance = saldo inicial (nunca modificado depois)

# NÃO modificar em receipt_service.py:217
# APENAS modificar em ajustes manuais

# Cálculo final:
Saldo = saldo_inicial + (todas transações) - (todos receipts)
```

**Vantagens:**
- Matematicamente correto
- Fácil de auditar
- account.balance = "ponto zero" do cartão

**Desvantagens:**
- Precisa garantir que NADA modifica account.balance além de ajustes

---

## 🎯 Recomendação Final

### Implementar Opção C + Sistema de Ajuste

1. **Remover linha 217** do receipt_service.py
2. **Manter cálculo dinâmico** como está
3. **Adicionar endpoint de ajuste** (já implementado!)
4. **Adicionar monitoring** (já implementado!)

### Como Corrigir Seu Saldo Negativo Agora

```bash
# Opção 1: Via API
POST /api/v1/benefit-cards/{card_id}/adjust-balance
{
  "adjustment_amount": 500.00,  ← Quanto adicionar para corrigir
  "reason": "Saldo real no cartão é R$ 400, havia erro de lançamento"
}

# Opção 2: Via SQL (direto no banco)
UPDATE accounts
SET balance = 400.00
WHERE id = (SELECT account_id FROM benefit_cards WHERE id = {seu_card_id});
```

---

## 📝 Próximo Passo

Qual opção você prefere implementar?

**A)** Remover linha 217 e confiar no cálculo dinâmico
**B)** Remover receipt_total do cálculo
**C)** Deixar como está e usar apenas ajustes manuais
**D)** Mostrar código exato para ajustar seu saldo agora

Qual você escolhe?