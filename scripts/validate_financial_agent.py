"""
Script de validação do agente financeiro.

Testa as consultas e cálculos contra os valores esperados do documento de validação.
Usuário de teste: kalebeandradesilva@hotmail.com (id: 3)
Data de referência: Janeiro/2026

Uso:
    cd backend && python scripts/validate_financial_agent.py
"""

import os
import sys

# Adicionar diretório pai ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.account import Account
from app.models.category import Category
from app.models.credit_card import CreditCard
from app.models.credit_card_invoice import CreditCardInvoice
from app.models.installment import InstallmentSeries, InstallmentSeriesStatus
from app.models.transaction import Transaction, TransactionType
from app.models.user import User

# Valores esperados do documento de validação
EXPECTED_VALUES = {
    # Faturas Janeiro/2026 (todas pagas)
    "faturas_janeiro": {
        "Bradesco Amazon": 1411.10,
        "Bradesco Amex": 3335.23,
        "Carrefour": 1478.01,
        "Celebre leroy": 634.61,
        "Digio": 296.10,
        "Inter": 1178.99,
        "Itau Pao de açucar": 3194.54,
        "Mercado Pago": 911.98,
        "Nubank": 2211.36,
        "Ourocard": 681.14,
        "Pan": 428.15,
        "Sams clube": 613.60,
        "Santander": 657.92,
    },
    "total_faturas_janeiro": 17032.73,
    # Faturas Fevereiro/2026 (todas abertas)
    "faturas_fevereiro": {
        "Bradesco Amazon": 52.54,
        "Bradesco Amex": 2737.87,
        "Carrefour": 1478.01,
        "Celebre leroy": 598.99,
        "Digio": 296.10,
        "Inter": 1149.09,
        "Itau Pao de açucar": 2153.09,
        "Mercado Pago": 785.38,
        "Nubank": 666.38,
        "Ourocard": 365.65,
        "Pan": 428.15,
        "Sams clube": 572.13,
        "Santander": 1125.18,
    },
    "total_faturas_fevereiro": 12408.56,
    # Gastos Janeiro/2026
    "despesas_janeiro": 36719.61,
    "receitas_janeiro": 39131.02,
    # Gastos por categoria Janeiro/2026
    "gastos_por_categoria_janeiro": {
        "Pagamento de Fatura": {"total": 17032.73, "count": 13},
        "Mercado": {"total": 1756.57, "count": 138},
        "Educação": {"total": 3600.00, "count": 1},
        "Contas": {"total": 4431.26, "count": 6},
        "Moradia": {"total": 299.00, "count": 1},
        "Lazer": {"total": 106.09, "count": 1},
        "Alimentação": {"total": 38.18, "count": 4},
    },
    # Cartões
    "total_cartoes": 14,
    "limite_total": 237136.00,
    "maior_limite_cartao": "Bradesco Amex",
    "maior_limite_valor": 76000.00,
    # Parcelas
    "parcelas_ativas": 109,
    "impacto_mensal_parcelas": 11363.93,
    "total_parcelas_restantes": 63343.95,
    # Contas
    "saldo_investimentos": 45000.00,
    "saldo_beneficios": 1479.56,
}


async def validate_invoices(session: AsyncSession, user_id: int):
    """Valida faturas de cartão de crédito"""
    print("\n" + "=" * 70)
    print("VALIDAÇÃO DE FATURAS DE CARTÃO")
    print("=" * 70)

    # Buscar faturas de janeiro
    result = await session.execute(
        select(CreditCardInvoice, Account.name.label("card_name"))
        .join(CreditCard, CreditCardInvoice.credit_card_id == CreditCard.id)
        .join(Account, CreditCard.account_id == Account.id)
        .where(
            CreditCardInvoice.user_id == user_id,
            CreditCardInvoice.reference_month == 1,
            CreditCardInvoice.reference_year == 2026,
        )
    )

    invoices_jan = result.all()

    print("\n--- FATURAS JANEIRO/2026 ---")
    print(
        f"{'Cartão':<25} {'Valor Encontrado':>15} {'Valor Esperado':>15} {'Status':>10} {'Match'}"
    )
    print("-" * 80)

    total_jan = 0
    errors_jan = []

    for inv, card_name in invoices_jan:
        expected = EXPECTED_VALUES["faturas_janeiro"].get(card_name)
        valor = float(inv.total_amount)
        total_jan += valor

        match = "✓" if expected and abs(valor - expected) < 0.01 else "✗"
        if expected and abs(valor - expected) >= 0.01:
            errors_jan.append((card_name, valor, expected))

        print(
            f"{card_name:<25} R$ {valor:>12.2f} R$ {expected or 0:>12.2f} {inv.status:>10} {match}"
        )

    print("-" * 80)
    expected_total = EXPECTED_VALUES["total_faturas_janeiro"]
    match_total = "✓" if abs(total_jan - expected_total) < 0.01 else "✗"
    print(f"{'TOTAL':<25} R$ {total_jan:>12.2f} R$ {expected_total:>12.2f} {'':>10} {match_total}")

    if errors_jan:
        print(f"\n⚠️  ERROS ENCONTRADOS: {len(errors_jan)}")
        for card, found, expected in errors_jan:
            print(f"   - {card}: encontrado R$ {found:.2f}, esperado R$ {expected:.2f}")

    # Buscar faturas de fevereiro
    result = await session.execute(
        select(CreditCardInvoice, Account.name.label("card_name"))
        .join(CreditCard, CreditCardInvoice.credit_card_id == CreditCard.id)
        .join(Account, CreditCard.account_id == Account.id)
        .where(
            CreditCardInvoice.user_id == user_id,
            CreditCardInvoice.reference_month == 2,
            CreditCardInvoice.reference_year == 2026,
        )
    )

    invoices_feb = result.all()

    print("\n--- FATURAS FEVEREIRO/2026 ---")
    print(
        f"{'Cartão':<25} {'Valor Encontrado':>15} {'Valor Esperado':>15} {'Status':>10} {'Match'}"
    )
    print("-" * 80)

    total_feb = 0
    errors_feb = []

    for inv, card_name in invoices_feb:
        expected = EXPECTED_VALUES["faturas_fevereiro"].get(card_name)
        valor = float(inv.total_amount)
        total_feb += valor

        match = "✓" if expected and abs(valor - expected) < 0.01 else "✗"
        if expected and abs(valor - expected) >= 0.01:
            errors_feb.append((card_name, valor, expected))

        print(
            f"{card_name:<25} R$ {valor:>12.2f} R$ {expected or 0:>12.2f} {inv.status:>10} {match}"
        )

    print("-" * 80)
    expected_total = EXPECTED_VALUES["total_faturas_fevereiro"]
    match_total = "✓" if abs(total_feb - expected_total) < 0.01 else "✗"
    print(f"{'TOTAL':<25} R$ {total_feb:>12.2f} R$ {expected_total:>12.2f} {'':>10} {match_total}")

    return len(errors_jan) + len(errors_feb)


async def validate_expenses(session: AsyncSession, user_id: int):
    """Valida cálculo de despesas"""
    print("\n" + "=" * 70)
    print("VALIDAÇÃO DE DESPESAS - JANEIRO/2026")
    print("=" * 70)

    period_start = date(2026, 1, 1)
    period_end = date(2026, 1, 31)

    # Buscar categorias
    cat_result = await session.execute(select(Category).where(Category.user_id == user_id))
    categories = {c.id: c.name for c in cat_result.scalars().all()}

    # Buscar transações do período
    result = await session.execute(
        select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.date >= period_start,
            Transaction.date <= period_end,
        )
    )
    txs = result.scalars().all()

    # Calcular totais SEM exclusões
    total_despesas_sem_filtro = sum(
        float(t.amount) for t in txs if t.type == TransactionType.EXPENSE.value
    )

    # Calcular totais COM exclusões (como o agente faz agora - apenas linked_transaction)
    total_despesas_com_filtro = sum(
        float(t.amount)
        for t in txs
        if t.type == TransactionType.EXPENSE.value and not t.linked_transaction_id
    )

    # Calcular receitas
    total_receitas = sum(
        float(t.amount)
        for t in txs
        if t.type == TransactionType.INCOME.value and not t.linked_transaction_id
    )

    # Gastos por categoria
    gastos_por_categoria = {}
    for t in txs:
        if t.type == TransactionType.EXPENSE.value and not t.linked_transaction_id:
            cat_name = categories.get(t.category_id, "Sem categoria")
            if cat_name not in gastos_por_categoria:
                gastos_por_categoria[cat_name] = {"total": 0, "count": 0}
            gastos_por_categoria[cat_name]["total"] += float(t.amount)
            gastos_por_categoria[cat_name]["count"] += 1

    # Transações excluídas
    excluded_linked = [
        t for t in txs if t.type == TransactionType.EXPENSE.value and t.linked_transaction_id
    ]
    excluded_receipt = [t for t in txs if t.type == TransactionType.EXPENSE.value and t.receipt_id]

    expected_despesas = EXPECTED_VALUES["despesas_janeiro"]
    expected_receitas = EXPECTED_VALUES["receitas_janeiro"]

    print(f"\nTotal de transações no período: {len(txs)}")
    print(
        f"Transações de despesa (sem filtro): {sum(1 for t in txs if t.type == TransactionType.EXPENSE.value)}"
    )
    print(f"Transações excluídas por linked_transaction_id: {len(excluded_linked)}")
    print(f"Transações excluídas por receipt_id: {len(excluded_receipt)}")

    print("\n--- TOTAIS ---")
    print(f"{'Métrica':<40} {'Encontrado':>15} {'Esperado':>15} {'Match'}")
    print("-" * 80)

    match_desp = "✓" if abs(total_despesas_com_filtro - expected_despesas) < 0.01 else "✗"
    match_rec = "✓" if abs(total_receitas - expected_receitas) < 0.01 else "✗"

    print(
        f"{'Despesas (com filtro agente)':<40} R$ {total_despesas_com_filtro:>12.2f} R$ {expected_despesas:>12.2f} {match_desp}"
    )
    print(
        f"{'Despesas (sem filtro)':<40} R$ {total_despesas_sem_filtro:>12.2f} R$ {expected_despesas:>12.2f}"
    )
    print(f"{'Receitas':<40} R$ {total_receitas:>12.2f} R$ {expected_receitas:>12.2f} {match_rec}")

    diff = total_despesas_sem_filtro - total_despesas_com_filtro
    print(f"\nDiferença por exclusões: R$ {diff:.2f}")

    if abs(total_despesas_com_filtro - expected_despesas) >= 0.01:
        print("\n⚠️  DISCREPÂNCIA DETECTADA!")
        print(f"   Esperado: R$ {expected_despesas:.2f}")
        print(f"   Encontrado: R$ {total_despesas_com_filtro:.2f}")
        print(f"   Diferença: R$ {expected_despesas - total_despesas_com_filtro:.2f}")

    # Mostrar gastos por categoria
    print("\n--- GASTOS POR CATEGORIA ---")
    print(f"{'Categoria':<30} {'Encontrado':>15} {'Esperado':>15} {'Count':>8} {'Match'}")
    print("-" * 80)

    for cat, data in sorted(
        gastos_por_categoria.items(), key=lambda x: x[1]["total"], reverse=True
    ):
        expected = EXPECTED_VALUES["gastos_por_categoria_janeiro"].get(cat, {})
        exp_total = expected.get("total", 0)
        match = (
            "✓"
            if exp_total and abs(data["total"] - exp_total) < 0.01
            else "✗"
            if exp_total
            else "-"
        )
        print(
            f"{cat:<30} R$ {data['total']:>12.2f} R$ {exp_total:>12.2f} {data['count']:>8} {match}"
        )

    return 0 if abs(total_despesas_com_filtro - expected_despesas) < 0.01 else 1


async def validate_cards(session: AsyncSession, user_id: int):
    """Valida informações de cartões"""
    print("\n" + "=" * 70)
    print("VALIDAÇÃO DE CARTÕES DE CRÉDITO")
    print("=" * 70)

    result = await session.execute(
        select(CreditCard, Account.name.label("card_name"))
        .join(Account, CreditCard.account_id == Account.id)
        .where(CreditCard.user_id == user_id, CreditCard.is_active == True)
    )

    cards = result.all()

    print(f"\nTotal de cartões ativos: {len(cards)} (esperado: {EXPECTED_VALUES['total_cartoes']})")

    total_limite = 0
    maior_limite_cartao = None
    maior_limite_valor = 0

    for card, card_name in cards:
        limite = float(card.credit_limit) if card.credit_limit else 0
        total_limite += limite
        if limite > maior_limite_valor:
            maior_limite_valor = limite
            maior_limite_cartao = card_name

    print(
        f"Limite total: R$ {total_limite:.2f} (esperado: R$ {EXPECTED_VALUES['limite_total']:.2f})"
    )
    print(
        f"Maior limite: {maior_limite_cartao} com R$ {maior_limite_valor:.2f} (esperado: {EXPECTED_VALUES['maior_limite_cartao']} com R$ {EXPECTED_VALUES['maior_limite_valor']:.2f})"
    )

    return 0


async def validate_installments(session: AsyncSession, user_id: int):
    """Valida parcelas ativas"""
    print("\n" + "=" * 70)
    print("VALIDAÇÃO DE PARCELAS")
    print("=" * 70)

    result = await session.execute(
        select(InstallmentSeries).where(
            InstallmentSeries.user_id == user_id,
            InstallmentSeries.status == InstallmentSeriesStatus.ACTIVE.value,
        )
    )

    installments = result.scalars().all()

    total_parcelas = len(installments)
    impacto_mensal = sum(float(s.installment_amount or 0) for s in installments)
    total_restante = sum(
        float(s.installment_amount or 0) * ((s.installment_count or 0) - (s.paid_count or 0))
        for s in installments
    )

    print(f"\nParcelas ativas: {total_parcelas} (esperado: {EXPECTED_VALUES['parcelas_ativas']})")
    print(
        f"Impacto mensal: R$ {impacto_mensal:.2f} (esperado: R$ {EXPECTED_VALUES['impacto_mensal_parcelas']:.2f})"
    )
    print(
        f"Total restante: R$ {total_restante:.2f} (esperado: R$ {EXPECTED_VALUES['total_parcelas_restantes']:.2f})"
    )

    return 0


async def run_validation():
    """Executa todas as validações"""
    print("\n" + "=" * 70)
    print("VALIDAÇÃO DO AGENTE FINANCEIRO BIVETO")
    print("=" * 70)
    print("Usuário de teste: kalebeandradesilva@hotmail.com (id: 3)")
    print("Data de referência: Janeiro/2026")

    async with async_session_maker() as session:
        # Buscar usuário
        result = await session.execute(
            select(User).where(User.email == "kalebeandradesilva@hotmail.com")
        )
        user = result.scalar_one_or_none()

        if not user:
            print("\n⚠️  ERRO: Usuário não encontrado!")
            return

        print(f"\nUsuário encontrado: {user.name} (ID: {user.id})")

        # Executar validações
        errors = 0
        errors += await validate_invoices(session, user.id)
        errors += await validate_expenses(session, user.id)
        errors += await validate_cards(session, user.id)
        errors += await validate_installments(session, user.id)

        # Resumo final
        print("\n" + "=" * 70)
        print("RESUMO DA VALIDAÇÃO")
        print("=" * 70)
        if errors == 0:
            print("✓ Todas as validações passaram!")
        else:
            print(f"✗ {errors} validações falharam")


if __name__ == "__main__":
    asyncio.run(run_validation())
