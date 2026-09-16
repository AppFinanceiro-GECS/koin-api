"""Monitor de saldo para alertas e auditoria

Este módulo NÃO bloqueia transações, apenas:
1. Registra quando saldo fica negativo
2. Envia alertas ao usuário
3. Permite ajustes manuais
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import utc_now
from app.models.account import Account

logger = logging.getLogger(__name__)


class BalanceMonitor:
    """Monitor de saldo - não bloqueia, apenas alerta"""

    @staticmethod
    def check_negative_balance(account: Account, amount: float, operation: str = "débito") -> dict:
        """Verifica se débito resultará em saldo negativo

        NÃO BLOQUEIA a operação, apenas retorna informações

        Returns:
            dict com:
            - will_be_negative: bool
            - current_balance: float
            - debit_amount: float
            - resulting_balance: float
            - alert_message: str (se aplicável)
        """
        current = float(account.balance)
        debit = float(amount)
        resulting = current - debit

        result = {
            "will_be_negative": resulting < 0,
            "current_balance": current,
            "debit_amount": debit,
            "resulting_balance": resulting,
            "alert_message": None,
        }

        if resulting < 0:
            result["alert_message"] = (
                f"⚠️ Saldo ficará negativo na conta '{account.name}': "
                f"R$ {current:.2f} - R$ {debit:.2f} = R$ {resulting:.2f}. "
                f"Verifique se o saldo do cartão físico está correto."
            )

            # Log para auditoria
            logger.warning(
                f"Saldo negativo detectado - Conta: {account.name} (ID: {account.id}), "
                f"Operação: {operation}, "
                f"Saldo atual: {current:.2f}, "
                f"Débito: {debit:.2f}, "
                f"Saldo resultante: {resulting:.2f}"
            )

        return result

    @staticmethod
    def log_negative_balance_event(
        account: Account, amount: float, operation: str, user_id: int
    ) -> None:
        """Registra evento de saldo negativo para auditoria

        Útil para identificar padrões e possíveis erros de lançamento
        """
        current = float(account.balance)
        resulting = current - float(amount)

        logger.info(
            f"[NEGATIVE_BALANCE_EVENT] "
            f"user_id={user_id}, "
            f"account_id={account.id}, "
            f"account_name={account.name}, "
            f"operation={operation}, "
            f"current_balance={current:.2f}, "
            f"debit_amount={amount:.2f}, "
            f"resulting_balance={resulting:.2f}, "
            f"timestamp={utc_now().isoformat()}"
        )


async def create_balance_adjustment(
    db: AsyncSession, account: Account, adjustment_amount: float, reason: str, user_id: int
) -> dict:
    """Cria ajuste de saldo (correção manual)

    Use quando o saldo do sistema estiver divergente do cartão físico

    Args:
        db: Sessão do banco
        account: Conta a ajustar
        adjustment_amount: Valor do ajuste (positivo ou negativo)
        reason: Motivo do ajuste
        user_id: ID do usuário que solicitou

    Returns:
        dict com detalhes do ajuste

    Example:
        # Saldo no sistema: R$ -50
        # Saldo real no cartão: R$ 400
        # Ajuste necessário: +450

        await create_balance_adjustment(
            db, account, 450.00,
            "Correção: saldo real do cartão é R$ 400",
            user.id
        )
    """
    from app.models.transaction import Transaction, TransactionType

    old_balance = float(account.balance)
    new_balance = old_balance + float(adjustment_amount)

    # Criar transação de ajuste para auditoria
    adjustment = Transaction(
        user_id=user_id,
        account_id=account.id,
        type=TransactionType.INCOME if adjustment_amount > 0 else TransactionType.EXPENSE,
        amount=abs(adjustment_amount),
        date=utc_now().date(),
        description=f"Ajuste de saldo: {reason}",
        category_id=None,  # Sem categoria (é ajuste manual)
        is_recurring=False,
        tags=["ajuste_saldo", "correcao_manual"],
    )

    db.add(adjustment)

    # Atualizar saldo
    account.balance = new_balance

    await db.flush()

    logger.info(
        f"[BALANCE_ADJUSTMENT] "
        f"user_id={user_id}, "
        f"account_id={account.id}, "
        f"account_name={account.name}, "
        f"old_balance={old_balance:.2f}, "
        f"adjustment={adjustment_amount:.2f}, "
        f"new_balance={new_balance:.2f}, "
        f"reason={reason}, "
        f"transaction_id={adjustment.id}"
    )

    return {
        "old_balance": old_balance,
        "adjustment": adjustment_amount,
        "new_balance": new_balance,
        "transaction_id": adjustment.id,
        "reason": reason,
    }
