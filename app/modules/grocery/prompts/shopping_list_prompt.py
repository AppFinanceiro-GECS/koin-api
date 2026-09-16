"""
Prompt for LLM-powered smart shopping list generation
"""

SMART_LIST_PROMPT = """Gere lista de compras a partir do historico.

DATA: {current_date} | PERIODO: {period_days} dias

REGRAS CRITICAS:
1. AGRUPE produtos similares (ignore marca): "Leite Italac" + "Leite Piracanjuba" = "Leite Integral"
2. SOME quantidades do mesmo tipo para calcular media mensal
3. EXCLUA fast-food (McDonald's, Burger King, etc)

CALCULO DE QUANTIDADE:
- Some qty de todos itens do mesmo tipo
- Divida por ({period_days}/30) para media mensal
- Arredonde para cima
- Exemplo: 3 compras de leite (2L+1L+2L) = 5L / 3 meses = 2L/mes

URGENCIA:
- high: passou do ciclo de recompra
- medium: proximo de acabar
- low: comprado recentemente

CATEGORIAS: fruits_vegetables, meat_fish, dairy, bakery, beverages, snacks, frozen, canned, grains_pasta, grains, condiments, cleaning, hygiene, personal_care, baby, pet, household, other

HISTORICO:
{purchases_json}

RESPONDA APENAS JSON:
{{"shopping_list":[{{"product_type":"Leite Integral","display_name":"Leite","category":"dairy","necessity_type":"essential","suggested_quantity":3,"unit":"L","estimated_price":5.99,"urgency":"medium","purchase_count":4,"days_since_last_purchase":10}}],"excluded":[],"insights":["insight1"]}}
"""

# Schema for structured JSON response from Gemini (simplified)
SMART_LIST_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "shopping_list": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "product_type": {"type": "string"},
                    "display_name": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "fruits_vegetables",
                            "meat_fish",
                            "dairy",
                            "bakery",
                            "beverages",
                            "snacks",
                            "frozen",
                            "canned",
                            "grains_pasta",
                            "grains",
                            "condiments",
                            "cleaning",
                            "hygiene",
                            "personal_care",
                            "baby",
                            "pet",
                            "household",
                            "other",
                        ],
                    },
                    "necessity_type": {"type": "string", "enum": ["essential", "non_essential"]},
                    "suggested_quantity": {"type": "number"},
                    "unit": {"type": "string"},
                    "estimated_price": {"type": "number", "nullable": True},
                    "urgency": {"type": "string", "enum": ["high", "medium", "low"]},
                    "purchase_count": {"type": "integer"},
                    "days_since_last_purchase": {"type": "integer"},
                },
                "required": [
                    "product_type",
                    "display_name",
                    "category",
                    "necessity_type",
                    "suggested_quantity",
                    "unit",
                    "urgency",
                    "purchase_count",
                    "days_since_last_purchase",
                ],
            },
        },
        "excluded": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "reason": {"type": "string"}},
            },
        },
        "insights": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["shopping_list", "excluded", "insights"],
}
