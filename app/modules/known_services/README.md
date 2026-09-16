# Modulo Known Services

## Descricao
Modulo responsavel pela deteccao automatica de servicos recorrentes conhecidos (Netflix, Spotify, etc.) durante a extracao de faturas de cartao de credito. Permite identificar assinaturas, sugerir cadastro de recorrencias e detectar duplicidades suspeitas.

## Responsabilidades
- Manter catalogo de servicos recorrentes conhecidos
- Detectar servicos conhecidos em descricoes de transacoes
- Identificar recorrencias ja cadastradas pelo usuario
- Analisar duplicidades (legitimas vs suspeitas vs erros)
- Sugerir cadastro de novas recorrencias

## Estrutura
```
known_services/
├── __init__.py
├── models/
│   └── known_service.py      # KnownRecurringService (catalogo)
├── schemas/
│   └── recurring_detection.py # RecurringDetection, DuplicateAnalysis, RecurringSuggestion
└── services/
    └── recurring_detector.py  # RecurringDetectorService (deteccao)
```

## Dependencias
- **Models**: `KnownRecurringService`, `RecurringTransaction`
- **Outros Modulos**: `recurring` (para verificar recorrencias do usuario)
- **Core**: `deps` (DbSession)

## Modelo KnownRecurringService

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | int | ID do servico |
| name | string | Nome do servico (ex: "Netflix") |
| patterns | JSON | Lista de padroes para matching (ex: ["NETFLIX", "NETFLIX.COM"]) |
| default_category | string | Categoria sugerida |
| default_frequency | string | Frequencia padrao (monthly) |
| logo_url | string | URL do logo (opcional) |
| is_active | bool | Se esta ativo |

## Servicos Cadastrados (Seed Data)

### Streaming
- Netflix, Spotify, Amazon Prime, Disney+, HBO Max, YouTube Premium
- Globoplay, Paramount+, Crunchyroll, Deezer

### Software e Cloud
- Apple Services, Google One, Microsoft 365, ChatGPT Plus, Claude AI
- Canva Pro, Dropbox, Adobe Creative Cloud, GitHub, JetBrains

### Assinaturas
- iFood Club, Rappi Prime, Uber One, Mercado Livre Melius
- Wellhub/Gympass, Smiles, Livelo, Starlink

### Games
- PlayStation Plus, Xbox Game Pass

### Saude
- Strava

## Tipos de Duplicidade

| Tipo | Descricao |
|------|-----------|
| `none` | Sem duplicidade - unica ocorrencia no periodo |
| `legitimate` | Duplicidade legitima - valores diferentes ou ciclos distintos |
| `suspicious` | Suspeito - valores iguais com datas proximas (<7 dias) |
| `error` | Provavel erro - 3+ cobrancas no mesmo periodo |

## Uso

### Integrar no fluxo de extracao
```python
from app.modules.known_services.services import RecurringDetectorService

# Apos extrair itens da fatura
detector = RecurringDetectorService(db)
items_with_detection = await detector.detect_all(
    user=user,
    items=extracted_items,
    invoice_month=1,
    invoice_year=2026,
)

# Cada item tera recurring_detection preenchido
for item in items_with_detection:
    detection = item.get("recurring_detection")
    if detection and detection.get("suggested_recurring"):
        # Mostrar sugestao para criar recorrencia
        pass
```

### Resposta do recurring_detection
```json
{
  "is_known_service": true,
  "known_service_id": 1,
  "known_service_name": "Netflix",
  "is_user_recurring": false,
  "user_recurring_id": null,
  "duplicate_analysis": {
    "duplicate_type": "none",
    "reason": "Unica ocorrencia no periodo",
    "occurrences_count": 1
  },
  "suggested_recurring": {
    "name": "Netflix",
    "amount": 55.90,
    "frequency": "monthly",
    "default_category": "streaming",
    "day_of_month": 15
  },
  "confidence": 0.95
}
```

## Fluxo de Deteccao

```
┌─────────────────────────────────────────────────────────────┐
│                    FLUXO DE DETECCAO                         │
└─────────────────────────────────────────────────────────────┘

  Item extraido: "NETFLIX.COM" - R$ 55.90
         │
         ▼
  ┌──────────────────────────────────────┐
  │ 1. Match com servicos conhecidos     │
  │    Patterns: ["NETFLIX", "NETFLIX*"] │
  │    Resultado: Netflix (95% conf)     │
  └──────────────────┬───────────────────┘
                     │
                     ▼
  ┌──────────────────────────────────────┐
  │ 2. Verificar recorrencias do usuario │
  │    Usuario ja tem Netflix cadastrado?│
  │    Resultado: Nao                    │
  └──────────────────┬───────────────────┘
                     │
                     ▼
  ┌──────────────────────────────────────┐
  │ 3. Analisar duplicidades             │
  │    Outras cobrancas Netflix?         │
  │    Resultado: Nenhuma                │
  └──────────────────┬───────────────────┘
                     │
                     ▼
  ┌──────────────────────────────────────┐
  │ 4. Gerar sugestao                    │
  │    Sugerir criar recorrencia Netflix │
  │    com R$ 55.90 mensal no dia 15     │
  └──────────────────────────────────────┘
```

## Endpoint Relacionado

O endpoint `POST /recurring/from-suggestion` permite criar uma recorrencia a partir da sugestao detectada. Ver documentacao do modulo `recurring`.
