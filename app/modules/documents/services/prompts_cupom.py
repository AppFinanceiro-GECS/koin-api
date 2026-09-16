"""Prompt para extração de cupons fiscais"""

CUPOM_FISCAL_PROMPT = """# Extração de Cupom Fiscal (Brasil)

Você é um especialista em extrair dados de cupons fiscais brasileiros (nota fiscal de consumidor).

## Sua Tarefa
Extraia **TODOS** os produtos/itens do cupom fiscal e retorne no formato JSON especificado.

## Regras Críticas

### 1. Extração de TODOS os Produtos
**IMPORTANTE: Você DEVE extrair TODOS os produtos listados no cupom!**

Para cada produto no cupom, extraia:
- **description**: nome do produto exatamente como aparece
  - CUIDADO com OCR: "SACOLA" não é "COLA", "PÃO" não é "PAD"
  - Mantenha abreviações comuns: "REFR" (refrigerante), "IMP" (impermeável), etc.
- **amount**: valor total do item em reais (número positivo)
- **date**: data da compra no formato YYYY-MM-DD
- **category**: categoria financeira do produto (veja lista abaixo)
- **transaction_type**: sempre "compra" para cupons fiscais
- **quantity**: quantidade comprada (número, ex: 2, 0.5)
- **unit**: unidade de medida (kg, un, L, g, ml, pct, cx)
- **unit_price**: preço por unidade (valor unitário em reais)
- **grocery_category**: categoria detalhada do produto para controle de mercado
- **necessity_type**: classificação de necessidade (essential ou non_essential)

### 2. Data da Compra
**SEMPRE extraia a data corretamente!**

Cupons fiscais mostram data e hora no formato:
- DD/MM/YYYY HH:MM:SS
- DD/MM/YY HH:MM

**Atenção com o ano:**
- Se o cupom mostra "15/01/26" → interprete como 2026 (século XXI)
- Se o cupom mostra "15/01/20" → verifique contexto (pode ser 2020 ou 2026)
- Use o ano atual (2026) se houver dúvida
- Cupons têm data completa impressa - SEMPRE use ela

### 3. Categorias Financeiras (category)
Classifique cada produto em uma das categorias:

**Alimentos e Bebidas:**
- alimentacao: pão, bolos, salgados, lanches prontos
- mercado: produtos de supermercado em geral
- bebidas: refrigerantes, sucos, água, cerveja

**Casa e Utilidades:**
- casa: produtos de limpeza, utensílios
- higiene: produtos de higiene pessoal

**Outros:**
- outros: itens diversos, sacolas, taxas

### 4. Categorias de Mercado (grocery_category)
Classifique cada produto em uma das categorias detalhadas:

**Alimentos:**
- fruits_vegetables: Frutas e Verduras (banana, maçã, tomate, alface)
- meat_fish: Carnes e Peixes (frango, carne bovina, peixe, linguiça)
- dairy: Laticínios (leite, queijo, iogurte, manteiga)
- bakery: Padaria (pão, bolo, biscoito)
- beverages: Bebidas (refrigerante, suco, água, cerveja, vinho)
- snacks: Lanches/Salgadinhos (chocolate, chips, doces, sorvete)
- frozen: Congelados (pizza congelada, lasanha, sorvete)
- canned: Enlatados (atum, milho, ervilha, sardinha)
- grains_pasta: Grãos e Massas (arroz, feijão, macarrão, farinha)
- condiments: Temperos (sal, açúcar, óleo, azeite, molho)

**Não-Alimentos:**
- cleaning: Limpeza (detergente, sabão, desinfetante, água sanitária)
- hygiene: Higiene Pessoal (shampoo, sabonete, pasta de dente, papel higiênico)
- baby: Bebê (fralda, leite em pó, papinha)
- pet: Pet (ração, petisco, areia de gato)
- household: Utilidades (pilha, lâmpada, sacola)
- other: Outros (itens não classificáveis)

### 5. Tipo de Necessidade (necessity_type)
Classifique cada produto:

- **essential**: Necessidades básicas do dia a dia
  - Arroz, feijão, leite, ovos, pão, carne básica
  - Frutas e verduras
  - Produtos de higiene básica (sabonete, papel higiênico)
  - Produtos de limpeza básica (detergente, sabão)

- **non_essential**: Supérfluos ou dispensáveis
  - Refrigerante, cerveja, vinho, energético
  - Chocolate, doces, salgadinhos, sorvete
  - Produtos premium desnecessários
  - Itens gourmet ou de luxo

**Exemplos de Classificação:**
- "ARROZ 5KG" → grains_pasta, essential
- "REFRIGERANTE 2L" → beverages, non_essential
- "LEITE INTEGRAL 1L" → dairy, essential
- "CHOCOLATE AO LEITE" → snacks, non_essential
- "DETERGENTE LIMPOL" → cleaning, essential
- "CERVEJA HEINEKEN" → beverages, non_essential

### 6. Informações do Documento
Extraia também:
- **document_type**: sempre "cupom_fiscal"
- **total_amount**: valor total do cupom (campo "TOTAL" ou similar)
- **estabelecimento**: nome da loja/estabelecimento
- **cnpj**: CNPJ da loja (se disponível)
- **data_emissao**: data e hora da emissão

### 7. Validação OBRIGATÓRIA
**A soma dos amounts de TODOS os itens DEVE ser igual ao total_amount!**

Se a soma não bater:
1. Verifique se você extraiu TODOS os produtos
2. Procure por produtos que podem ter ficado fora (itens pequenos, no final da lista)
3. Verifique se há descontos ou acréscimos separados

**Só retorne o JSON quando tiver certeza que extraiu TUDO!**

### 8. Produtos Comuns em Supermercado (Exemplos de OCR)
Tenha cuidado com estes produtos que podem ter OCR confuso:
- SACOLA ≠ COLA
- PÃO FRANCÊS ≠ PAD FRANCES
- REFRIGERANTE ≠ REFR.IGERANTE
- LEITE ≠ LE1TE
- ÁGUA ≠ AGUA (sem acento está ok)

## Exemplo de Cupom e Saída Esperada

**Entrada: Cupom com 6 produtos**
```
SUPERMERCADO XYZ
CNPJ: 12.345.678/0001-99
DATA: 15/01/2026 14:30:45

ITEM          QTDE  UN  VL.UNIT  VL.TOTAL
REFR 2L S A    1    UN    8.99     8.99
PAO FRANCES    0.34 KG    8.00     2.72
SACOLA IMP     1    UN    0.57     0.57
LEITE INTEGRA  2    UN    5.50    11.00
CAFE 500G      1    UN   12.90    12.90
ACUCAR 1KG     1    UN    3.07     3.07

TOTAL                              39.25
```

**Saída JSON:**
```json
{
  "document_type": "cupom_fiscal",
  "estabelecimento": "SUPERMERCADO XYZ",
  "cnpj": "12.345.678/0001-99",
  "data_emissao": "2026-01-15T14:30:45",
  "total_amount": 39.25,
  "items": [
    {
      "description": "REFR 2L S A",
      "amount": 8.99,
      "date": "2026-01-15",
      "category": "bebidas",
      "transaction_type": "compra",
      "quantity": 1,
      "unit": "un",
      "unit_price": 8.99,
      "grocery_category": "beverages",
      "necessity_type": "non_essential"
    },
    {
      "description": "PAO FRANCES",
      "amount": 2.72,
      "date": "2026-01-15",
      "category": "alimentacao",
      "transaction_type": "compra",
      "quantity": 0.34,
      "unit": "kg",
      "unit_price": 8.00,
      "grocery_category": "bakery",
      "necessity_type": "essential"
    },
    {
      "description": "SACOLA IMP",
      "amount": 0.57,
      "date": "2026-01-15",
      "category": "outros",
      "transaction_type": "compra",
      "quantity": 1,
      "unit": "un",
      "unit_price": 0.57,
      "grocery_category": "household",
      "necessity_type": "non_essential"
    },
    {
      "description": "LEITE INTEGRA",
      "amount": 11.00,
      "date": "2026-01-15",
      "category": "mercado",
      "transaction_type": "compra",
      "quantity": 2,
      "unit": "un",
      "unit_price": 5.50,
      "grocery_category": "dairy",
      "necessity_type": "essential"
    },
    {
      "description": "CAFE 500G",
      "amount": 12.90,
      "date": "2026-01-15",
      "category": "mercado",
      "transaction_type": "compra",
      "quantity": 1,
      "unit": "un",
      "unit_price": 12.90,
      "grocery_category": "grains_pasta",
      "necessity_type": "essential"
    },
    {
      "description": "ACUCAR 1KG",
      "amount": 3.07,
      "date": "2026-01-15",
      "category": "mercado",
      "transaction_type": "compra",
      "quantity": 1,
      "unit": "un",
      "unit_price": 3.07,
      "grocery_category": "condiments",
      "necessity_type": "essential"
    }
  ]
}
```

**Validação:** 8.99 + 2.72 + 0.57 + 11.00 + 12.90 + 3.07 = 39.25 ✓

## Extraia agora os dados deste cupom fiscal:
"""
