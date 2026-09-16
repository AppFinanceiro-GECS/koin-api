"""
Script para corrigir o campo paid_count em séries de parcelas.

Problema: Quando uma parcela (ex: 6/12) é importada, o sistema
incrementa paid_count em 1, mas as parcelas anteriores (1-5) nunca
são contabilizadas se mark_previous_as_paid=False (padrão).

Fórmula correta:
    paid_count = COUNT(transações pagas) + (MIN(installment_number) - 1)

Onde:
- COUNT(transações pagas): parcelas marcadas como is_paid=true no sistema
- MIN(installment_number) - 1: parcelas anteriores à primeira importada (implicitamente pagas)

Exemplo - MOTOCHEFE BRASILIA:
- Importada: parcela 6/12
- Sistema criou: paid_count = 1 (ERRADO)
- Transações com is_paid=true: 1 (parcela 6)
- MIN(installment_number): 6
- Parcelas anteriores implícitas: 6 - 1 = 5
- paid_count correto: 1 + 5 = 6

Uso:
    python fix_paid_count.py --dry-run          # Simula sem alterar (padrão)
    python fix_paid_count.py --execute          # Aplica as correções
    python fix_paid_count.py --user-id UUID     # Testa apenas para um usuário
"""

import argparse
import asyncio
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.installment import InstallmentSeriesStatus


async def calculate_correct_paid_counts(
    session: AsyncSession, user_id: str | None = None
) -> list[dict]:
    """
    Calcula o paid_count correto para todas as séries ativas.

    Fórmula:
        paid_count = COUNT(transações pagas) + (MIN(installment_number) - 1)

    Returns:
        Lista de dicionários com séries que precisam de correção
    """
    user_filter = "AND s.user_id = :user_id" if user_id else ""
    params = {"user_id": user_id} if user_id else {}

    result = await session.execute(
        text(f"""
        WITH series_stats AS (
            SELECT
                s.id as series_id,
                s.user_id,
                s.description,
                s.installment_count,
                s.paid_count as paid_atual,
                s.status,
                a.name as cartao_nome,
                (
                    SELECT COUNT(*)
                    FROM transactions t
                    WHERE t.installment_series_id = s.id AND t.is_paid = true
                ) as transacoes_pagas,
                (
                    SELECT COALESCE(MIN(t.installment_number), 1)
                    FROM transactions t
                    WHERE t.installment_series_id = s.id
                ) as min_installment_number,
                (
                    SELECT COUNT(*)
                    FROM transactions t
                    WHERE t.installment_series_id = s.id
                ) as total_transacoes
            FROM installment_series s
            LEFT JOIN credit_cards cc ON s.credit_card_id = cc.id
            LEFT JOIN accounts a ON cc.account_id = a.id
            WHERE s.status = 'active'
            {user_filter}
        )
        SELECT
            series_id,
            user_id,
            description,
            installment_count,
            paid_atual,
            status,
            cartao_nome,
            transacoes_pagas,
            min_installment_number,
            total_transacoes,
            transacoes_pagas + (min_installment_number - 1) as paid_correto
        FROM series_stats
        WHERE total_transacoes > 0  -- Só corrige séries que têm transações
        ORDER BY cartao_nome, description
    """),
        params,
    )

    rows = result.fetchall()
    corrections = []

    for row in rows:
        paid_correto = row.paid_correto

        # Limitar ao installment_count máximo
        if paid_correto > row.installment_count:
            paid_correto = row.installment_count

        # Só inclui se precisa de correção
        if row.paid_atual != paid_correto:
            corrections.append(
                {
                    "series_id": row.series_id,
                    "user_id": row.user_id,
                    "description": row.description,
                    "cartao_nome": row.cartao_nome or "N/A",
                    "installment_count": row.installment_count,
                    "paid_atual": row.paid_atual,
                    "paid_correto": paid_correto,
                    "transacoes_pagas": row.transacoes_pagas,
                    "min_installment_number": row.min_installment_number,
                    "parcelas_anteriores": row.min_installment_number - 1,
                    "should_complete": paid_correto >= row.installment_count,
                }
            )

    return corrections


async def apply_corrections(
    session: AsyncSession, corrections: list[dict], dry_run: bool = True
) -> dict:
    """
    Aplica as correções de paid_count.

    Args:
        session: Sessão do banco de dados
        corrections: Lista de correções a aplicar
        dry_run: Se True, apenas simula sem alterar

    Returns:
        Dicionário com estatísticas das correções
    """
    stats = {
        "total": len(corrections),
        "updated": 0,
        "completed": 0,
        "errors": 0,
    }

    for correction in corrections:
        try:
            if not dry_run:
                # Atualiza paid_count
                await session.execute(
                    text("""
                    UPDATE installment_series
                    SET paid_count = :paid_count
                    WHERE id = :series_id
                """),
                    {
                        "paid_count": correction["paid_correto"],
                        "series_id": correction["series_id"],
                    },
                )

                # Se deve completar, atualiza status
                if correction["should_complete"]:
                    await session.execute(
                        text("""
                        UPDATE installment_series
                        SET status = :status
                        WHERE id = :series_id
                    """),
                        {
                            "status": InstallmentSeriesStatus.COMPLETED.value,
                            "series_id": correction["series_id"],
                        },
                    )
                    stats["completed"] += 1

            stats["updated"] += 1

        except Exception as e:
            print(f"    ERRO na série {correction['series_id']}: {e}")
            stats["errors"] += 1

    return stats


async def run_fix(dry_run: bool = True, user_id: str | None = None):
    """Executa a correção de paid_count."""
    print(f"\n{'=' * 70}")
    print("CORREÇÃO DE PAID_COUNT EM SÉRIES DE PARCELAS")
    print(f"{'=' * 70}")
    print(f"Modo: {'DRY RUN (simulação)' if dry_run else 'EXECUÇÃO REAL'}")
    if user_id:
        print(f"Filtro: user_id = {user_id}")
    print(f"Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 70}\n")

    print("Fórmula utilizada:")
    print("  paid_count = COUNT(transações pagas) + (MIN(installment_number) - 1)")
    print()

    async with async_session_maker() as session:
        # Calcular correções necessárias
        corrections = await calculate_correct_paid_counts(session, user_id)

        if not corrections:
            print("Nenhuma série precisa de correção!")
            return

        print(f"Encontradas {len(corrections)} séries que precisam de correção:\n")
        print(f"{'Cartão':<20} {'Descrição':<30} {'Atual':>6} {'Correto':>7} {'Fórmula'}")
        print("-" * 90)

        for c in corrections:
            formula = f"{c['transacoes_pagas']} + ({c['min_installment_number']} - 1) = {c['paid_correto']}"
            desc = c["description"][:28] + ".." if len(c["description"]) > 30 else c["description"]
            cartao = (
                c["cartao_nome"][:18] + ".." if len(c["cartao_nome"]) > 20 else c["cartao_nome"]
            )

            completar = " [COMPLETAR]" if c["should_complete"] else ""
            print(
                f"{cartao:<20} {desc:<30} {c['paid_atual']:>6} {c['paid_correto']:>7} {formula}{completar}"
            )

        print()

        # Aplicar correções
        stats = await apply_corrections(session, corrections, dry_run)

        if not dry_run:
            await session.commit()
            print(f"\n{'=' * 70}")
            print("COMMIT REALIZADO - Alterações salvas no banco!")
            print(f"{'=' * 70}")
        else:
            print(f"\n{'=' * 70}")
            print("DRY RUN - Nenhuma alteração foi salva.")
            print("Execute com --execute para aplicar as correções.")
            print(f"{'=' * 70}")

        # Resumo
        print("\n--- RESUMO ---")
        print(f"Séries analisadas: {stats['total']}")
        print(f"Séries {'a corrigir' if dry_run else 'corrigidas'}: {stats['updated']}")
        print(f"Séries {'a completar' if dry_run else 'completadas'}: {stats['completed']}")
        if stats["errors"] > 0:
            print(f"Erros: {stats['errors']}")

        return corrections


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Corrige o campo paid_count em séries de parcelas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
    python fix_paid_count.py --dry-run          # Simula sem alterar (padrão)
    python fix_paid_count.py --execute          # Aplica as correções
    python fix_paid_count.py --user-id UUID     # Testa apenas para um usuário
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Simula as correções sem alterar o banco (padrão)",
    )
    parser.add_argument("--execute", action="store_true", help="Executa as correções de verdade")
    parser.add_argument("--user-id", type=str, default=None, help="Filtra por user_id específico")

    args = parser.parse_args()

    # Se --execute foi passado, dry_run = False
    dry_run = not args.execute

    asyncio.run(run_fix(dry_run=dry_run, user_id=args.user_id))
