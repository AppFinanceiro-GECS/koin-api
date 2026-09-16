#!/usr/bin/env python3
"""
Script para migrar transacoes antigas de mercado para a tabela grocery_purchases.
Execute com: python scripts/backfill_grocery_purchases.py [--dry-run]
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import and_, func, select
from sqlalchemy.orm import selectinload

from app.core.database import async_session_maker
from app.models.category import Category
from app.models.grocery import GroceryCategory, GroceryPurchase, NecessityType
from app.models.transaction import Transaction

# Categorias que indicam compras de mercado
MARKET_CATEGORY_NAMES = [
    "supermercado",
    "alimentação",
    "alimentacao",
    "mercado",
    "grocery",
]


async def backfill_grocery_purchases(dry_run: bool = True):
    """
    Migra transacoes de categorias de mercado para grocery_purchases.

    Args:
        dry_run: Se True, apenas mostra o que seria feito sem criar registros
    """
    async with async_session_maker() as db:
        # 1. Buscar IDs das categorias de mercado
        category_query = select(Category).where(
            func.lower(Category.name).in_(MARKET_CATEGORY_NAMES)
        )
        category_result = await db.execute(category_query)
        categories = category_result.scalars().all()

        if not categories:
            print("Nenhuma categoria de mercado encontrada!")
            print(f"Categorias procuradas: {MARKET_CATEGORY_NAMES}")
            return

        category_ids = [c.id for c in categories]
        print(f"Categorias encontradas: {[(c.id, c.name) for c in categories]}")

        # 2. Buscar transacoes que ja tem grocery_purchase
        existing_query = select(GroceryPurchase.transaction_id).where(
            GroceryPurchase.transaction_id.isnot(None)
        )
        existing_result = await db.execute(existing_query)
        existing_transaction_ids = set(row[0] for row in existing_result.all())

        print(f"Transacoes que ja tem grocery_purchase: {len(existing_transaction_ids)}")

        # 3. Buscar transacoes de mercado sem grocery_purchase
        transactions_query = (
            select(Transaction)
            .options(selectinload(Transaction.merchant))
            .where(
                and_(
                    Transaction.category_id.in_(category_ids),
                    Transaction.type == "expense",
                    ~Transaction.id.in_(existing_transaction_ids)
                    if existing_transaction_ids
                    else True,
                )
            )
            .order_by(Transaction.date.desc())
        )
        transactions_result = await db.execute(transactions_query)
        transactions = transactions_result.scalars().all()

        print(f"\nTransacoes para migrar: {len(transactions)}")

        if not transactions:
            print("Nenhuma transacao para migrar!")
            return

        # 4. Criar grocery_purchases
        created_count = 0
        for tx in transactions:
            # Determinar nome do produto
            product_name = tx.description or tx.merchant_name or "Compra de mercado"

            # Determinar merchant_id
            merchant_id = tx.merchant_id

            print(f"\n{'[DRY-RUN] ' if dry_run else ''}Transacao #{tx.id}:")
            print(f"  Data: {tx.date}")
            print(f"  Valor: R$ {float(tx.amount):.2f}")
            print(f"  Descricao: {product_name}")
            print(f"  Merchant: {tx.merchant_name or 'N/A'}")

            if not dry_run:
                # Criar GroceryPurchase
                grocery_purchase = GroceryPurchase(
                    user_id=tx.user_id,
                    transaction_id=tx.id,
                    document_id=None,
                    product_id=None,
                    merchant_id=merchant_id,
                    product_name=product_name,
                    quantity=1,
                    unit="un",
                    unit_price=float(tx.amount),
                    total_price=float(tx.amount),
                    category=GroceryCategory.OTHER.value,
                    necessity_type=NecessityType.ESSENTIAL.value,
                    purchase_date=tx.date,
                    ownership_type=tx.ownership_type or "personal",
                )
                db.add(grocery_purchase)
                created_count += 1

        if not dry_run:
            await db.commit()
            print(f"\n{'=' * 50}")
            print(f"Criados {created_count} registros de grocery_purchase!")
        else:
            print(f"\n{'=' * 50}")
            print(f"[DRY-RUN] Seriam criados {len(transactions)} registros.")
            print("Execute sem --dry-run para criar os registros.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv or "-n" in sys.argv

    if dry_run:
        print("Modo DRY-RUN: nenhum registro sera criado\n")
    else:
        print("Modo EXECUCAO: registros serao criados\n")

    asyncio.run(backfill_grocery_purchases(dry_run=dry_run))
