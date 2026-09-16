# Instruções Específicas para Faturas Itaú

## LAYOUT CARACTERÍSTICO DO ITAÚ

### Página 1: Boleto e Resumo
- Contém informações gerais e boleto
- **NÃO extrair transações da página 1**

### Página 2: DUAS COLUNAS DE TRANSAÇÕES (CRÍTICO!)

O Itaú usa um layout de **DUAS COLUNAS** lado a lado na página 2.
**AMBAS AS COLUNAS DEVEM SER EXTRAÍDAS!**

#### Estrutura da Página 2:

```
┌───────────────────────────────────┬───────────────────────────────────┐
│ ✅ Lançamentos: compras e saques  │ ✅ Lançamentos: compras e saques  │
│ KALEBE A SILVA (final 8849)       │                                   │
│ DATA  ESTABELECIMENTO      VALOR  │ DATA  ESTABELECIMENTO      VALOR  │
├───────────────────────────────────┼───────────────────────────────────┤
│ COLUNA ESQUERDA (EXTRAIR!)        │ COLUNA DIREITA (EXTRAIR!)         │
│ (Parcelas de meses anteriores     │ (Compras do mês atual +           │
│  que continuam sendo cobradas)    │  produtos e serviços)             │
│                                   │                                   │
│ 09/07 MOTOCHEFE 08/12     574,13  │ 23/02 Wellhub          199,99     │
│ 20/07 PRIME GLOBAL 08/10  148,00  │                                   │
│ 13/09 FASTSHO 06/12       107,33  │ Lançamentos: produtos e serviços  │
│ 26/09 GpPneus 06/08       241,00  │ 09/02 ANUIDADE          56,50     │
│ 08/10 PAYGO 05/06         144,90  │                                   │
│ 15/10 EC *PICHAU 05/06    166,64  │ Total dos lançamentos: 2.371,56   │
│ 15/10 EC *PICHAU 05/06     85,61  │                                   │
│ 16/10 PAG*Steam 05/12     107,51  │ ──────────────────────────────    │
│ 17/10 PG *MARCELO 05/06    83,35  │ ❌ Compras parceladas -           │
│ 18/10 PAG*Steam 05/12     161,52  │    próximas faturas               │
│ 21/10 PAG*Steam 05/12     106,09  │ (NÃO EXTRAIR! São as mesmas       │
│ 01/01 nuuvem 03/06         44,65  │  parcelas mas com número +1)      │
│ 01/01 nuuvem 03/06         18,35  │                                   │
│ 13/02 Karacas              21,00  │ 09/07 MOTOCHEFE 09/12    574,13   │
│ 13/02 CASAS PERNAM 01/02  104,99  │ 15/10 EC *PICHAU 06/06   166,64  │
│                                   │ etc...                            │
└───────────────────────────────────┴───────────────────────────────────┘
```

**⚠️ ATENÇÃO:** A seção "Compras parceladas - próximas faturas" aparece na MESMA página 2 (coluna direita).
Ela contém os MESMOS estabelecimentos com a parcela incrementada (08/12→09/12).
**NÃO EXTRAIA itens da seção "próximas faturas"!**

## 🚨 INSTRUÇÕES CRÍTICAS PARA EXTRAÇÃO DO ITAÚ

### 1. IDENTIFIQUE AS DUAS COLUNAS

Antes de extrair, identifique visualmente:
- ✅ Há duas colunas lado a lado?
- ✅ Ambas têm o título "Lançamentos: compras e saques"?
- ✅ As datas da esquerda são antigas (07, 09, 10) e da direita são recentes (01, 23, 26)?

**Se SIM para todas:** Você DEVE extrair AMBAS AS COLUNAS!

### 2. PROCESSE COLUNA POR COLUNA

**PASSO 1:** Extraia TODA a coluna ESQUERDA
- Comece em "09/07 MOTOCHEFE..."
- Vá até a última linha antes da seção "Lançamentos produtos e serviços"
- Geralmente tem ~10-15 transações

**PASSO 2:** Extraia TODA a coluna DIREITA
- Comece em "23/01 Wellhub..." (ou primeira transação visível)
- Vá até a última linha
- Geralmente tem ~3-5 transações

### 3. CARACTERÍSTICAS DAS COLUNAS

**Coluna ESQUERDA:**
- Datas: Meses anteriores (07, 08, 09, 10, etc.)
- Descrições: Sempre têm código de parcela (07/12, 05/08, 04/06)
- Valores: Geralmente R$ 100-600
- Total esperado: ~R$ 1.500-1.800
- **São parcelas de compras antigas que CONTINUAM sendo cobradas**

**Coluna DIREITA:**
- Datas: Mês atual da fatura (01, 23, 26, etc.)
- Descrições: Podem ou não ter parcelas
- Valores: Variam
- Total esperado: ~R$ 300-500
- **São compras NOVAS do mês**

### 4. NÃO CONFUNDA COM PRÓXIMA FATURA (CRÍTICO!)

A seção **"Compras parceladas - próximas faturas"** aparece na **mesma página 2** (coluna direita, parte inferior) OU na página 3.
Esta seção mostra parcelas que VÃO VENCER no futuro — são os MESMOS estabelecimentos mas com o número da parcela INCREMENTADO.

**🚫 NÃO EXTRAIA ESSA SEÇÃO!**

Como diferenciar:
- ✅ **"Lançamentos: compras e saques"** → EXTRAIR (são os lançamentos ATUAIS)
- ✅ **"Lançamentos: produtos e serviços"** → EXTRAIR (anuidades, etc.)
- ❌ **"Compras parceladas - próximas faturas"** → NÃO EXTRAIR

**Exemplo de como distinguir (mesma página 2):**
```
LANÇAMENTOS ATUAIS (EXTRAIR):          PRÓXIMAS FATURAS (NÃO EXTRAIR):
09/07 MOTOCHEFE 08/12  574,13          09/07 MOTOCHEFE 09/12  574,13
15/10 EC *PICHAU 05/06  166,64         15/10 EC *PICHAU 06/06  166,64
```
Note que as parcelas na seção "próximas faturas" têm o número da parcela +1 (08/12→09/12, 05/06→06/06).
**Extraia APENAS os lançamentos atuais, que aparecem ANTES da linha "Total dos lançamentos atuais".**

### 5. VALIDAÇÃO ESPECÍFICA DO ITAÚ

Após extrair, valide:
```
A soma dos itens extraídos DEVE ser próxima ao total_amount da fatura.

Se diferença > R$ 50:
- Você provavelmente esqueceu itens da COLUNA ESQUERDA!
- Verifique se TODOS os itens ANTES de "Total dos lançamentos atuais" foram extraídos
- Confira especialmente: itens com valores altos (R$ 500+) são fáceis de pular
- Itens com mesma descrição mas valores diferentes são compras DISTINTAS (ex: 2x EC *PICHAU com valores diferentes)
```

### 6. ITENS COM MESMA DESCRIÇÃO MAS VALORES DIFERENTES

É comum ter MÚLTIPLAS transações com o mesmo estabelecimento mas valores diferentes.
**TODAS devem ser extraídas como itens separados!**

Exemplo real:
```
15/10 EC *PICHAUINFO05/06  166,64   ← Item 1 (EXTRAIR!)
15/10 EC *PICHAUINFO05/06   85,61   ← Item 2 (EXTRAIR! Valor diferente = compra diferente!)
```

**NÃO agrupe esses itens!** São compras distintas no mesmo estabelecimento.

### 7. FORMATO DAS DESCRIÇÕES DO ITAÚ

O Itaú frequentemente trunca descrições:
- "MOTOCHEFE BRASILIA07/12" (sem espaço antes do código)
- "FASTSHO*CD66D2X*Fa05/12" (sem espaço antes do código)
- "nuuvem *Nuuvem" (pode aparecer como "nuuem *Nuuve m")

**Extraia exatamente como está**, não tente corrigir ou completar.

### 8. CRÉDITOS E ESTORNOS

O Itaú mostra créditos com valor negativo:
- "01/01 nuuvem *Nuuvem - 0,10" → amount: -0.10
- "01/01 nuuvem *Nuuvem - 0,20" → amount: -0.20

**⚠️ NÃO IGNORE valores pequenos!** Mesmo R$ 0,10 deve ser extraído.

### 9. FORMATO DE DATAS DO ITAÚ (CRÍTICO!)

A coluna DATA no Itaú mostra o formato **DD/MM** (dia/mês) da data ORIGINAL da compra.

**⚠️ REGRA OBRIGATÓRIA:**
- O formato é DD/MM onde MM é o MÊS REAL da compra original
- NÃO use o mês da fatura para todas as transações!
- Para parcelas de compras antigas, o mês será ANTERIOR ao mês da fatura

**EXEMPLOS (fatura de fevereiro/2026):**
- "09/07 MOTOCHEFE" → date: "2025-07-09" (julho 2025, NÃO fevereiro 2026!)
- "13/09 FASTSHO" → date: "2025-09-13" (setembro 2025)
- "08/10 PAYGO" → date: "2025-10-08" (outubro 2025)
- "01/01 nuuvem" → date: "2026-01-01" (janeiro 2026)
- "13/02 Karacas" → date: "2026-02-13" (fevereiro 2026)

**REGRA PARA DETERMINAR O ANO:**
- Se o mês da transação > mês da fatura → use invoice_year - 1
- Se o mês da transação <= mês da fatura → use invoice_year

**❌ ERRO COMUM:** Ignorar o mês (MM) e usar o mês da fatura para todas as transações.
Exemplo errado: "09/07 MOTOCHEFE" na fatura de fev/2026 → "2026-02-09" ← ERRADO!
Exemplo correto: "09/07 MOTOCHEFE" na fatura de fev/2026 → "2025-07-09" ← CORRETO!

## RESUMO DA ESTRATÉGIA

Para faturas do Itaú:
1. ✅ Identifique as DUAS colunas na página 2
2. ✅ Processe coluna ESQUERDA (parcelas antigas)
3. ✅ Processe coluna DIREITA (compras novas)
4. ✅ Use a data DD/MM REAL de cada transação (NÃO substitua o mês!)
5. ✅ Valide: soma deve estar próxima do total_amount
6. ✅ Se diferença > R$ 50: procure transações que você esqueceu
