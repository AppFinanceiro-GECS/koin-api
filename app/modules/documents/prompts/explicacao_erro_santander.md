Você tem razão — **na fatura do Santander o valor correto da fatura atual é R$ 657,90**, e **não** R$ 2.199,09.

O próprio PDF mostra **“Total a Pagar R$ 657,90”**  e no detalhamento confirma **“Saldo Desta Fatura 657,90”** .

A diferença acontece porque **houve créditos/estornos (descontos) grandes** que reduziram bastante o total.

---

## Santander — Tabela da fatura atual (somente o que compõe o saldo de R$ 657,90)

> Observação: a fatura tem lançamentos em **mais de um cartão (final 5201 e final 5581)**, mas **o “Saldo desta fatura” é único**.

### Lançamentos (por tipo)

| Cartão (final) | Seção           |  Data | Descrição                    | Parcela | Valor (R$) | É parcelado? |
| -------------- | --------------- | ----: | ---------------------------- | ------- | ---------: | ------------ |
| 5201           | Pagamento       | 08/12 | PAGAMENTO DE FATURA-INTERNET | —       |    -827,60 | Não          |
| 5201           | Parcelamentos   | 27/09 | PRIME GLOBAL PAGAMENTO       | 04/10   |     315,00 | Sim          |
| 5201           | Despesas        | 05/01 | ANUIDADE DIFERENCIADA        | —       |      37,00 | Não          |
| 5201           | Parcelamentos   | 01/12 | MERCADOLIVRE*4PRODUTOS       | 01/12   |      16,91 | Sim          |
| 5201           | Parcelamentos   | 01/12 | MERCADOLIVRE*4PRODUTOS       | 01/12   |      20,87 | Sim          |
| 5201           | Parcelamentos   | 01/12 | MERCADO*GOBLINFACTORY        | 10/12   |     107,49 | Sim          |
| 5201           | Parcelamentos   | 01/12 | MERCADO*GOBLINFACTORY        | 11/12   |     107,49 | Sim          |
| 5201           | Parcelamentos   | 01/12 | MERCADO*GOBLINFACTORY        | 12/12   |     107,49 | Sim          |
| 5201           | Estorno/Crédito | 03/12 | MERCADO*GOBLINFACTORY        | —       |  -1.289,94 | Não          |
| 5581           | Créditos        | 18/11 | (crédito)                    | —       |      -0,02 | Não          |
| 5581           | Créditos        | 19/11 | (crédito)                    | —       |      -0,02 | Não          |
| 5581           | Créditos        | 25/11 | (crédito)                    | —       |      -0,02 | Não          |
| 5581           | Créditos        | 04/12 | (crédito)                    | —       |     -97,44 | Não          |
| 5581           | Parcelamentos   | 16/11 | MERCADOLIVRE*LGELECTR        | 14/21   |     172,88 | Sim          |
| 5581           | Parcelamentos   | 17/11 | MERCADOLIVRE*HABBITSH        | 02/06   |      56,15 | Sim          |
| 5581           | Parcelamentos   | 17/11 | MERCADOLIVRE*MERCADOL        | 02/09   |      53,35 | Sim          |
| 5581           | Parcelamentos   | 17/11 | MERCADO*MERCADOLIVRE         | 02/06   |      43,39 | Sim          |
| 5581           | Parcelamentos   | 17/11 | MERCADO*MERCADOLIVRE         | 02/06   |      39,85 | Sim          |
| 5581           | Parcelamentos   | 19/11 | MERCADO*GOBLINFACTORY        | 01/12   |     107,55 | Sim          |
| 5581           | Parcelamentos   | 19/11 | MERCADO*GOBLINFACTORY        | 02/12   |     107,49 | Sim          |
| 5581           | Parcelamentos   | 19/11 | MERCADO*GOBLINFACTORY        | 03/12   |     107,49 | Sim          |
| 5581           | Parcelamentos   | 19/11 | MERCADO*GOBLINFACTORY        | 04/12   |     107,49 | Sim          |
| 5581           | Parcelamentos   | 19/11 | MERCADO*GOBLINFACTORY        | 05/12   |     107,49 | Sim          |
| 5581           | Parcelamentos   | 19/11 | MERCADO*GOBLINFACTORY        | 06/12   |     107,49 | Sim          |
| 5581           | Parcelamentos   | 19/11 | MERCADO*GOBLINFACTORY        | 07/12   |     107,49 | Sim          |
| 5581           | Parcelamentos   | 19/11 | MERCADO*GOBLINFACTORY        | 08/12   |     107,49 | Sim          |
| 5581           | Parcelamentos   | 19/11 | MERCADO*GOBLINFACTORY        | 09/12   |     107,49 | Sim          |

**De onde eu peguei esses lançamentos no PDF**

* Pagamento/Prime Global/Anuidade (cartão 5201): 
* Créditos de -0,02 e -97,44 (cartão 5581): 
* Estorno -1.289,94 e parcelas (parte do 5201): 
* Parcelamentos do cartão 5581 (LGELECTR e demais): 

---

## Santander — Por que o total fecha em R$ 657,90 (explicação “contábil”)

O PDF traz um **resumo matemático** (isso é ótimo para treinar agentes, porque dá um “checksum”):

* **Saldo anterior:** 827,60
* **Total despesas/débitos no Brasil:** 2.045,34
* **Total de pagamentos:** 827,60
* **Total de créditos:** 1.387,44
* **Saldo desta fatura:** **657,90** 

A conta é:

**827,60 + 2.045,34 − 827,60 − 1.387,44 = 657,90**

### O que são esses “descontos/créditos” que derrubam o valor?

Os **créditos totais (R$ 1.387,44)** batem exatamente com:

* Estorno grande: **-1.289,94** (MERCADO*GOBLINFACTORY) 
* Outro crédito: **-97,44** 
* Três microcréditos: **-0,02 / -0,02 / -0,02** 

Somando: 1.289,94 + 97,44 + 0,06 = **1.387,44** → exatamente o “Total de créditos” do resumo .

### Onde aparece informação de “fatura futura” (e por que ignorar)

Nesta fatura existe bloco de **histórico/fatura aberta** (ex.: “Fatura Aberta 513,92”) — isso não é o valor da fatura fechada, é **saldo do próximo ciclo**. 
Para o dataset, o valor correto do ciclo fechado é o **“Total a Pagar”**  e/ou o **“Saldo desta fatura”** .

---

## Totais corretos (fatura atual) — para seu dataset (sem “próxima fatura”)

| Emissor       | Total da fatura atual (R$) | Evidência no PDF |
| ------------- | -------------------------: | ---------------- |
| Santander     |                 **657,90** |                  |
| Nubank        |                   2.211,36 |                  |
| Inter         |                   1.178,99 |                  |
| Digio         |                     296,10 |                  |
| Ourocard (BB) |                     681,14 |                  |
| Bradesco AMEX |                   3.334,89 |                  |
| Carrefour     |                   1.478,01 |                  |
| Sam’s Club    |                     613,60 |                  |
| Itaú          |                   3.193,12 |                  |

---

## “Como eu peguei” (regras práticas para treinar seus agentes por banco)

### Santander

1. **Valor oficial**: procurar **“Total a Pagar”**  e validar com **“Saldo Desta Fatura”** .
2. **Lançamentos**: pegar do “Detalhamento da Fatura” (Pagamentos/Créditos/Parcelamentos/Despesas) .
3. **Parcelado**: existe coluna **“x/y”** (ex.: 14/21, 02/06, 09/12) .
4. **Ignorar futuro**: “Histórico de faturas / Fatura Aberta” .

### Nubank

1. **Valor oficial**: “RESUMO DA FATURA ATUAL” → **“Total a pagar”** .
2. **Ignorar futuro**: bloco “PRÓXIMAS FATURAS” .
3. **Parcelado**: na linha da compra aparece “**Parcela x/y**” .

### Inter

1. **Valor oficial**: no cabeçalho do ciclo aparece “(cartão) (vencimento) **R$ 1.178,99**” .
2. **Parcelado**: “(Parcela N de M)” na linha .
3. **Ignorar futuro**: existe trecho explícito “**Próxima fatura…** (compras parceladas…)” .

### Digio

1. **Valor oficial**: “**Valor da fatura R$ 296,10**” .
2. **Parcelado**: “8/10”, “8/12” etc ao lado do lançamento .
3. **Ignorar futuro**: “**Próximas faturas**” .

### Ourocard (BB)

1. **Valor oficial**: “Resumo da fatura … **Total R$ 681,14**” .
2. **Parcelado**: aparece como “PARC xx/yy” na descrição .
3. **Ignorar futuro**: bloco “Parcelamentos Próxima Fatura” .

### Bradesco AMEX

1. **Valor oficial**: “Total da fatura R$ 3.334,89”  e confirmação no resumo “(=)Total … 3.334,89” .
2. **Lançamentos**: linhas com data/descrição e às vezes parcela “01/03”, “01/06” etc .

### Carrefour

1. **Valor oficial**: “TOTAL DA FATURA ATUAL: R$ 1.478,01” .
2. **Ignorar futuro**: “SALDOS FUTUROS / Total de parcelas a pagar / … próxima fatura …” .
3. **Parcelado**: padrão “- 9/15”, “- 8/10” na própria linha .

### Sam’s Club

1. **Valor oficial**: “TOTAL DA SUA FATURA … R$ 613,60” .

### Itaú

1. **Valor oficial**: “Lançamentos atuais … Total desta fatura 3.193,12”  e também no boleto “Valor do Documento R$ 3.193,12” .
2. **Parcelado**: aparece como “04/12”, “02/06” etc ao lado do lançamento .