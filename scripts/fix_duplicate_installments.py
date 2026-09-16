"""
Script para corrigir séries de parcelas duplicadas.

Problema: Quando duas compras têm mesmo merchant, valor e total de parcelas,
elas foram incorretamente mescladas em uma única série.

Solução: Separar cada compra em sua própria série e criar parcelas futuras faltantes.
"""

import asyncio
from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.installment import InstallmentSeries, InstallmentSeriesStatus
from app.models.transaction import Transaction, TransactionType
from app.models.user import User


async def find_problematic_series(session: AsyncSession) -> list[dict]:
    """Encontra séries com parcelas duplicadas (mesmo installment_number)."""
    result = await session.execute(
        text("""
        SELECT
            s.id as series_id,
            s.user_id,
            s.description,
            s.merchant_name,
            s.installment_amount,
            s.installment_count,
            s.first_installment_date,
            s.account_id,
            s.category_id,
            s.credit_card_id,
            t.installment_number,
            array_agg(t.id ORDER BY t.created_at) as transaction_ids,
            array_agg(t.date ORDER BY t.created_at) as transaction_dates,
            array_agg(t.invoice_id ORDER BY t.created_at) as invoice_ids
        FROM installment_series s
        JOIN transactions t ON t.installment_series_id = s.id
        GROUP BY s.id, s.user_id, s.description, s.merchant_name, s.installment_amount,
                 s.installment_count, s.first_installment_date, s.account_id,
                 s.category_id, s.credit_card_id, t.installment_number
        HAVING COUNT(*) > 1
        ORDER BY s.user_id, s.id, t.installment_number
    """)
    )

    rows = result.fetchall()
    problems = []
    for row in rows:
        problems.append(
            {
                "series_id": row.series_id,
                "user_id": row.user_id,
                "description": row.description,
                "merchant_name": row.merchant_name,
                "installment_amount": float(row.installment_amount),
                "installment_count": row.installment_count,
                "first_installment_date": row.first_installment_date,
                "account_id": row.account_id,
                "category_id": row.category_id,
                "credit_card_id": row.credit_card_id,
                "installment_number": row.installment_number,
                "transaction_ids": row.transaction_ids,
                "transaction_dates": row.transaction_dates,
                "invoice_ids": row.invoice_ids,
            }
        )
    return problems


async def fix_series(session: AsyncSession, problem: dict, dry_run: bool = True) -> dict:
    """
    Corrige uma série problemática separando a segunda transação em nova série.

    Returns:
        dict com informações sobre as correções realizadas
    """
    result = {
        "series_id": problem["series_id"],
        "description": problem["description"],
        "actions": [],
        "new_series_id": None,
        "transactions_created": 0,
    }

    # A primeira transação fica na série original, a segunda precisa de nova série
    first_tx_id = problem["transaction_ids"][0]
    second_tx_id = problem["transaction_ids"][1]

    # Buscar a transação que será movida
    tx_result = await session.execute(select(Transaction).where(Transaction.id == second_tx_id))
    second_tx = tx_result.scalar_one()

    # Buscar série original
    series_result = await session.execute(
        select(InstallmentSeries).where(InstallmentSeries.id == problem["series_id"])
    )
    original_series = series_result.scalar_one()

    # Buscar usuário
    user_result = await session.execute(select(User).where(User.id == problem["user_id"]))
    user_result.scalar_one()  # valida que o usuario existe

    result["actions"].append(f"Transação {second_tx_id} será movida para nova série")

    if dry_run:
        result["actions"].append("[DRY RUN] Nenhuma alteração realizada")
        return result

    # PASSO 1: Atualizar first_transaction_id da série original (se ainda não definido)
    if not original_series.first_transaction_id:
        original_series.first_transaction_id = first_tx_id
        result["actions"].append(
            f"Série original {problem['series_id']}: first_transaction_id = {first_tx_id}"
        )

    # PASSO 2: Criar nova série para a segunda transação
    # Calcular first_installment_date baseado na data da transação e número da parcela
    tx_date = second_tx.date
    installment_num = problem["installment_number"]
    new_first_installment_date = tx_date - relativedelta(months=installment_num - 1)

    new_series = InstallmentSeries(
        user_id=problem["user_id"],
        description=problem["description"],
        merchant_name=problem["merchant_name"],
        merchant_id=original_series.merchant_id,
        total_amount=problem["installment_amount"] * problem["installment_count"],
        installment_amount=problem["installment_amount"],
        installment_count=problem["installment_count"],
        first_installment_date=new_first_installment_date,
        account_id=problem["account_id"],
        category_id=problem["category_id"],
        credit_card_id=problem["credit_card_id"],
        first_transaction_id=second_tx_id,
        status=InstallmentSeriesStatus.ACTIVE,
        paid_count=1,  # A transação movida conta como paga
    )
    session.add(new_series)
    await session.flush()

    result["new_series_id"] = new_series.id
    result["actions"].append(f"Nova série criada: ID {new_series.id}")

    # PASSO 3: Mover a transação para a nova série
    second_tx.installment_series_id = new_series.id
    result["actions"].append(f"Transação {second_tx_id} movida para série {new_series.id}")

    # PASSO 4: Atualizar paid_count da série original
    # Contar quantas transações pagas restam na série original
    count_result = await session.execute(
        text("""
        SELECT COUNT(*) FROM transactions
        WHERE installment_series_id = :series_id AND is_paid = true
    """),
        {"series_id": problem["series_id"]},
    )
    original_paid_count = count_result.scalar()
    original_series.paid_count = original_paid_count
    result["actions"].append(f"Série original: paid_count atualizado para {original_paid_count}")

    # PASSO 5: Criar parcelas futuras para a nova série
    current_installment = problem["installment_number"]
    total_installments = problem["installment_count"]

    if current_installment < total_installments:
        # Buscar faturas futuras para vincular
        invoices_by_month = {}
        if problem["credit_card_id"]:
            inv_result = await session.execute(
                text("""
                SELECT id, reference_month, reference_year
                FROM credit_card_invoices
                WHERE credit_card_id = :card_id AND user_id = :user_id
                ORDER BY reference_year, reference_month
            """),
                {"card_id": problem["credit_card_id"], "user_id": problem["user_id"]},
            )
            for inv in inv_result.fetchall():
                key = (inv.reference_year, inv.reference_month)
                invoices_by_month[key] = inv.id

        # Determinar mês/ano base da fatura atual
        if problem["invoice_ids"] and problem["invoice_ids"][1]:
            base_invoice_id = problem["invoice_ids"][1]
            base_inv_result = await session.execute(
                text("""
                SELECT reference_month, reference_year FROM credit_card_invoices WHERE id = :id
            """),
                {"id": base_invoice_id},
            )
            base_inv = base_inv_result.fetchone()
            base_month = base_inv.reference_month
            base_year = base_inv.reference_year
        else:
            # Fallback: usar a data da transação
            base_month = tx_date.month
            base_year = tx_date.year

        # Criar parcelas futuras
        for i in range(current_installment + 1, total_installments + 1):
            months_offset = i - current_installment
            future_date = date(base_year, base_month, 1) + relativedelta(months=months_offset)
            estimated_tx_date = tx_date + relativedelta(months=months_offset)

            # Buscar invoice_id para este mês
            invoice_id = invoices_by_month.get((future_date.year, future_date.month))

            # Verificar se já existe esta parcela
            existing = await session.execute(
                text("""
                SELECT id FROM transactions
                WHERE installment_series_id = :series_id AND installment_number = :num
            """),
                {"series_id": new_series.id, "num": i},
            )
            if existing.fetchone():
                continue

            new_tx = Transaction(
                user_id=problem["user_id"],
                account_id=problem["account_id"],
                category_id=problem["category_id"],
                merchant_id=original_series.merchant_id,
                credit_card_id=problem["credit_card_id"],
                invoice_id=invoice_id,
                installment_series_id=new_series.id,
                type=TransactionType.EXPENSE,
                amount=problem["installment_amount"],
                date=estimated_tx_date,
                description=f"{problem['description']} - Parcela {i}/{total_installments}",
                installment_number=i,
                installment_total=total_installments,
                is_paid=False,
                is_fixed=True,
            )
            session.add(new_tx)
            result["transactions_created"] += 1

            # Atualizar total da fatura se existir
            if invoice_id:
                await session.execute(
                    text("""
                    UPDATE credit_card_invoices
                    SET total_amount = total_amount + :amount
                    WHERE id = :id
                """),
                    {"amount": problem["installment_amount"], "id": invoice_id},
                )

        result["actions"].append(
            f"Criadas {result['transactions_created']} parcelas futuras (parcelas {current_installment + 1} a {total_installments})"
        )

    await session.flush()
    return result


async def run_fix(dry_run: bool = True):
    """Executa a correção de todas as séries problemáticas."""
    print(f"\n{'=' * 60}")
    print("CORREÇÃO DE PARCELAS DUPLICADAS")
    print(f"{'=' * 60}")
    print(f"Modo: {'DRY RUN (simulação)' if dry_run else 'EXECUÇÃO REAL'}")
    print(f"{'=' * 60}\n")

    async with async_session_maker() as session:
        # Encontrar séries problemáticas
        problems = await find_problematic_series(session)

        if not problems:
            print("Nenhuma série problemática encontrada!")
            return

        print(f"Encontradas {len(problems)} séries problemáticas:\n")

        # Agrupar por série (pode haver múltiplas parcelas duplicadas na mesma série)
        series_problems = {}
        for p in problems:
            if p["series_id"] not in series_problems:
                series_problems[p["series_id"]] = []
            series_problems[p["series_id"]].append(p)

        results = []
        for series_id, probs in series_problems.items():
            # Usar apenas o primeiro problema de cada série (normalmente só há um)
            problem = probs[0]
            print(f"\n--- Série {series_id}: {problem['description']} ---")
            print(f"    Parcela {problem['installment_number']} duplicada")
            print(f"    Transações: {problem['transaction_ids']}")

            result = await fix_series(session, problem, dry_run=dry_run)
            results.append(result)

            for action in result["actions"]:
                print(f"    -> {action}")

        if not dry_run:
            await session.commit()
            print(f"\n{'=' * 60}")
            print("COMMIT REALIZADO - Alterações salvas no banco!")
            print(f"{'=' * 60}")
        else:
            print(f"\n{'=' * 60}")
            print("DRY RUN - Nenhuma alteração foi salva.")
            print("Execute com dry_run=False para aplicar as correções.")
            print(f"{'=' * 60}")

        # Resumo
        print("\n--- RESUMO ---")
        print(f"Séries corrigidas: {len(results)}")
        total_tx = sum(r["transactions_created"] for r in results)
        print(f"Parcelas futuras criadas: {total_tx}")

        return results


if __name__ == "__main__":
    import sys

    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1] == "--execute":
        dry_run = False

    asyncio.run(run_fix(dry_run=dry_run))
