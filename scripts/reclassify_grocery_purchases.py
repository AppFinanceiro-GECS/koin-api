#!/usr/bin/env python3
"""
Script para reclassificar grocery_purchases baseado no nome do produto.
Execute com: python scripts/reclassify_grocery_purchases.py [--dry-run]
"""

import asyncio
import os
import re
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.grocery import GroceryCategory, GroceryPurchase, NecessityType

# Regras de classificacao baseadas em palavras-chave
# IMPORTANTE: A ordem importa! Categorias mais especificas primeiro
CLASSIFICATION_RULES = [
    # TEMPEROS E CONDIMENTOS (condiments) - primeiro para pegar maionese, geleia, molho
    (
        GroceryCategory.CONDIMENTS.value,
        {
            "keywords": [
                "sal ",
                "acucar",
                "açúcar",
                "oleo",
                "óleo",
                "azeite",
                "vinagre",
                "molho",
                "ketchup",
                "mostarda",
                "maionese",
                "mayonese",
                "shoyu",
                "tempero",
                "oregano",
                "orégano",
                "manjericao",
                "manjericão",
                "pimenta",
                "colorau",
                "cominho",
                "canela",
                "cravo",
                "noz moscada",
                "curry",
                "geleia",
                "geléia",
                "mel ",
                "extrato",
                "caldo",
                "knorr",
                "maggi",
                "baconnaise",
                "hellmanns",
                "heinz",
                "aretti",
            ],
            "necessity": NecessityType.ESSENTIAL.value,
        },
    ),
    # PADARIA (bakery) - antes de snacks para pegar coxinha, pao
    (
        GroceryCategory.BAKERY.value,
        {
            "keywords": [
                "pao",
                "pão",
                "frances",
                "francês",
                "forma",
                "integral",
                "baguete",
                "croissant",
                "bolo",
                "torta",
                "rosquinha",
                "sonho",
                "coxinha",
                "esfiha",
                "empada",
                "pastel",
                "brioche",
            ],
            "necessity": NecessityType.ESSENTIAL.value,
        },
    ),
    # FRUTAS E VERDURAS (fruits_vegetables)
    (
        GroceryCategory.FRUITS_VEGETABLES.value,
        {
            "keywords": [
                "banana",
                "maca",
                "maça",
                "laranja",
                "limao",
                "limão",
                "uva",
                "morango",
                "melancia",
                "melao",
                "melão",
                "abacaxi",
                "manga",
                "mamao",
                "mamão",
                "tomate",
                "cebola",
                "batata",
                "cenoura",
                "alface",
                "couve",
                "brocolis",
                "brócolis",
                "pepino",
                "pimentao",
                "pimentão",
                "abobrinha",
                "berinjela",
                "repolho",
                "espinafre",
                "rucula",
                "rúcula",
                "agriao",
                "hortalica",
                "hortaliça",
                "verdura",
                "legume",
                "fruta",
                "salada",
            ],
            "necessity": NecessityType.ESSENTIAL.value,
        },
    ),
    # CARNES E PEIXES (meat_fish)
    (
        GroceryCategory.MEAT_FISH.value,
        {
            "keywords": [
                "carne",
                "bovina",
                "frango",
                "galinha",
                "peru",
                "pato",
                "porco",
                "linguica",
                "linguiça",
                "salsicha",
                "bacon",
                "presunto",
                "mortadela",
                "hamburguer",
                "hambúrguer",
                "bife",
                "file",
                "filé",
                "costela",
                "picanha",
                "alcatra",
                "patinho",
                "acém",
                "acem",
                "contrafile",
                "contrafilé",
                "maminha",
                "cupim",
                "t bone",
                "t-bone",
                "angus",
                "peixe",
                "salmao",
                "salmão",
                "tilapia",
                "tilápia",
                "atum",
                "sardinha",
                "bacalhau",
                "camarao",
                "camarão",
                "lagosta",
                "merluza",
                "pescada",
            ],
            "necessity": NecessityType.ESSENTIAL.value,
        },
    ),
    # LATICINIOS (dairy)
    (
        GroceryCategory.DAIRY.value,
        {
            "keywords": [
                "leite",
                "queijo",
                "iogurte",
                "yogurt",
                "manteiga",
                "margarina",
                "requeijao",
                "requeijão",
                "creme de leite",
                "nata",
                "ricota",
                "mussarela",
                "muçarela",
                "parmesao",
                "parmesão",
                "provolone",
                "cottage",
                "cream cheese",
                "coalho",
                "minas",
            ],
            "necessity": NecessityType.ESSENTIAL.value,
        },
    ),
    # BEBIDAS (beverages) - geralmente non_essential
    (
        GroceryCategory.BEVERAGES.value,
        {
            "keywords": [
                "refrigerante",
                "refri",
                "coca",
                "pepsi",
                "fanta",
                "sprite",
                "guarana",
                "guaraná",
                "suco",
                "nectar",
                "néctar",
                "agua",
                "água",
                "mineral",
                "cerveja",
                "heineken",
                "brahma",
                "skol",
                "amstel",
                "budweiser",
                "vinho",
                "espumante",
                "champagne",
                "whisky",
                "vodka",
                "gin",
                "rum",
                "energetico",
                "energético",
                "redbull",
                "monster",
                "cha",
                "chá",
                "cafe",
                "café",
                "cappuccino",
                "achocolatado",
                "toddy",
                "nescau",
            ],
            "necessity": NecessityType.NON_ESSENTIAL.value,
            # Excecoes que sao essenciais
            "essential_keywords": ["agua", "água", "mineral", "cafe", "café", "cha", "chá"],
        },
    ),
    # LANCHES/SNACKS (snacks) - geralmente non_essential
    (
        GroceryCategory.SNACKS.value,
        {
            "keywords": [
                "chocolate",
                "bombom",
                "barra",
                "kit kat",
                "bis ",
                "snickers",
                "bala",
                "pirulito",
                "chiclete",
                "goma",
                "doce",
                "brigadeiro",
                "chips",
                "batata frita",
                "doritos",
                "ruffles",
                "cheetos",
                "fandangos",
                "amendoim",
                "castanha",
                "salgadinho",
                "pipoca",
                "cereal",
                "biscoito",
                "bolacha",
                "sorvete",
                "picole",
                "picolé",
                "gelato",
                "acai",
                "açaí",
            ],
            "necessity": NecessityType.NON_ESSENTIAL.value,
        },
    ),
    # CONGELADOS (frozen)
    (
        GroceryCategory.FROZEN.value,
        {
            "keywords": [
                "congelado",
                "pizza congelada",
                "lasanha",
                "nuggets",
                "empanado",
                "hamburguer congelado",
                "legumes congelados",
                "batata congelada",
            ],
            "necessity": NecessityType.NON_ESSENTIAL.value,
        },
    ),
    # ENLATADOS (canned)
    (
        GroceryCategory.CANNED.value,
        {
            "keywords": [
                "enlatado",
                "conserva",
                "atum lata",
                "sardinha lata",
                "milho lata",
                "ervilha",
                "palmito",
                "azeitona",
                "picles",
                "pepino conserva",
            ],
            "necessity": NecessityType.ESSENTIAL.value,
        },
    ),
    # GRAOS E MASSAS (grains_pasta)
    (
        GroceryCategory.GRAINS_PASTA.value,
        {
            "keywords": [
                "arroz",
                "feijao",
                "feijão",
                "lentilha",
                "grao de bico",
                "grão",
                "macarrao",
                "macarrão",
                "espaguete",
                "penne",
                "lasanha massa",
                "farinha",
                "trigo",
                "fuba",
                "fubá",
                "aveia",
                "granola",
                "muesli",
                "tapioca",
                "polenta",
                "cuscuz",
                "quinoa",
            ],
            "necessity": NecessityType.ESSENTIAL.value,
        },
    ),
    # LIMPEZA (cleaning)
    (
        GroceryCategory.CLEANING.value,
        {
            "keywords": [
                "detergente",
                "sabao",
                "sabão",
                "lava loucas",
                "lava louças",
                "desinfetante",
                "agua sanitaria",
                "água sanitária",
                "cloro",
                "alvejante",
                "amaciante",
                "sabao em po",
                "sabão em pó",
                "omo",
                "ariel",
                "vanish",
                "esponja",
                "pano",
                "vassoura",
                "rodo",
                "lustra moveis",
                "limpa vidro",
                "multiuso",
                "veja",
                "cif",
            ],
            "necessity": NecessityType.ESSENTIAL.value,
        },
    ),
    # HIGIENE (hygiene)
    (
        GroceryCategory.HYGIENE.value,
        {
            "keywords": [
                "shampoo",
                "condicionador",
                "sabonete",
                "desodorante",
                "creme dental",
                "pasta de dente",
                "escova dental",
                "fio dental",
                "enxaguante",
                "papel higienico",
                "papel higiênico",
                "absorvente",
                "cotonete",
                "algodao",
                "algodão",
                "gilete",
                "aparelho barbear",
                "creme barbear",
                "hidratante",
                "protetor solar",
                "repelente",
            ],
            "necessity": NecessityType.ESSENTIAL.value,
        },
    ),
    # BEBE (baby)
    (
        GroceryCategory.BABY.value,
        {
            "keywords": [
                "fralda",
                "pampers",
                "huggies",
                "lenco umedecido",
                "lenço",
                "papinha",
                "nan",
                "aptamil",
                "nestle bebe",
                "mamadeira",
                "chupeta",
            ],
            "necessity": NecessityType.ESSENTIAL.value,
        },
    ),
    # PET
    (
        GroceryCategory.PET.value,
        {
            "keywords": [
                "racao",
                "ração",
                "pedigree",
                "whiskas",
                "petisco",
                "ossinho",
                "areia gato",
                "sachê",
                "sache",
            ],
            "necessity": NecessityType.ESSENTIAL.value,
        },
    ),
    # UTILIDADES (household)
    (
        GroceryCategory.HOUSEHOLD.value,
        {
            "keywords": [
                "sacola",
                "pilha",
                "lampada",
                "lâmpada",
                "vela",
                "fosforo",
                "fósforo",
                "isqueiro",
                "fita",
                "cola",
                "tesoura",
                "caixa",
                "saco lixo",
            ],
            "necessity": NecessityType.NON_ESSENTIAL.value,
        },
    ),
]

# Padroes para restaurantes/fast food
RESTAURANT_PATTERNS = [
    r"mcdonalds?",
    r"burger king",
    r"bk ",
    r"subway",
    r"habib",
    r"giraffas",
    r"outback",
    r"madero",
    r"coco bambu",
    r"almoco",
    r"almoço",
    r"jantar",
    r"restaurante",
    r"pizzaria",
    r"ifood",
    r"rappi",
]


def normalize_text(text: str) -> str:
    """Remove acentos e converte para minusculo."""
    return (
        text.lower()
        .replace("ã", "a")
        .replace("á", "a")
        .replace("â", "a")
        .replace("à", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )


def classify_product(product_name: str) -> tuple[str, str]:
    """
    Classifica um produto baseado no nome.

    Returns:
        tuple: (grocery_category, necessity_type)
    """
    name_normalized = normalize_text(product_name)

    # Verificar restaurantes (categoria especial - alimentacao, nao mercado)
    for pattern in RESTAURANT_PATTERNS:
        if re.search(pattern, name_normalized):
            # Restaurante vai para OTHER, mas essencial
            return GroceryCategory.OTHER.value, NecessityType.ESSENTIAL.value

    # Verificar cada categoria na ordem definida
    for category, rules in CLASSIFICATION_RULES:
        keywords = rules["keywords"]
        default_necessity = rules["necessity"]

        for keyword in keywords:
            keyword_normalized = normalize_text(keyword)

            if keyword_normalized in name_normalized:
                # Verificar se eh uma excecao de necessidade
                necessity = default_necessity
                if "essential_keywords" in rules:
                    for ess_kw in rules["essential_keywords"]:
                        ess_normalized = normalize_text(ess_kw)
                        if ess_normalized in name_normalized:
                            necessity = NecessityType.ESSENTIAL.value
                            break

                return category, necessity

    # Se nao encontrou, retorna other/essential
    return GroceryCategory.OTHER.value, NecessityType.ESSENTIAL.value


async def reclassify_purchases(dry_run: bool = True):
    """
    Reclassifica grocery_purchases baseado no nome do produto.
    """
    async with async_session_maker() as db:
        # Buscar todos os purchases
        result = await db.execute(select(GroceryPurchase))
        purchases = result.scalars().all()

        print(f"Total de compras: {len(purchases)}")
        print("=" * 100)

        updated_count = 0
        unchanged_count = 0

        for p in purchases:
            new_category, new_necessity = classify_product(p.product_name)

            # Verificar se mudou
            changed = p.category != new_category or p.necessity_type != new_necessity

            if changed:
                prefix = "[DRY-RUN] " if dry_run else ""
                print(f"{prefix}#{p.id:4} | {p.product_name[:40]:40}")
                print(f"       Categoria: {p.category:20} -> {new_category:20}")
                print(f"       Necessidade: {p.necessity_type:15} -> {new_necessity:15}")
                print()

                if not dry_run:
                    p.category = new_category
                    p.necessity_type = new_necessity

                updated_count += 1
            else:
                unchanged_count += 1

        if not dry_run:
            await db.commit()

        print("=" * 100)
        print(f"Atualizados: {updated_count}")
        print(f"Sem mudanca: {unchanged_count}")

        if dry_run:
            print("\n[DRY-RUN] Execute sem --dry-run para aplicar as mudancas.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv

    if dry_run:
        print("Modo DRY-RUN: nenhuma mudanca sera feita\n")
    else:
        print("Modo EXECUCAO: mudancas serao aplicadas\n")

    asyncio.run(reclassify_purchases(dry_run=dry_run))
