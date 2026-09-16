"""Validadores reutilizaveis para o sistema"""

from fastapi import HTTPException

from app.models.account import Account


class InsufficientBalanceError(HTTPException):
    """Erro quando saldo e insuficiente para operacao"""

    def __init__(self, account_name: str, available: float, required: float):
        detail = (
            f"Saldo insuficiente na conta '{account_name}'. "
            f"Disponível: R$ {available:.2f}, "
            f"Necessário: R$ {required:.2f}"
        )
        super().__init__(status_code=422, detail=detail)


def validate_sufficient_balance(account: Account, amount: float, operation: str = "débito") -> None:
    """Valida se a conta tem saldo suficiente para a operacao

    Args:
        account: Conta a ser debitada
        amount: Valor a ser debitado
        operation: Nome da operacao (para mensagem de erro)

    Raises:
        InsufficientBalanceError: Se saldo insuficiente

    Examples:
        >>> validate_sufficient_balance(account, 100.00, "pagamento")
        # OK se account.balance >= 100
        # Raises InsufficientBalanceError se account.balance < 100
    """
    current_balance = float(account.balance)
    debit_amount = float(amount)

    if current_balance < debit_amount:
        raise InsufficientBalanceError(
            account_name=account.name, available=current_balance, required=debit_amount
        )


def validate_and_debit(account: Account, amount: float, operation: str = "débito") -> float:
    """Valida saldo e realiza debito atomicamente

    Args:
        account: Conta a ser debitada
        amount: Valor a ser debitado
        operation: Nome da operacao (para mensagem de erro)

    Returns:
        float: Novo saldo apos debito

    Raises:
        InsufficientBalanceError: Se saldo insuficiente

    Examples:
        >>> new_balance = validate_and_debit(account, 50.00, "compra")
        >>> print(new_balance)
        450.0  # Se tinha 500, agora tem 450
    """
    validate_sufficient_balance(account, amount, operation)

    current_balance = float(account.balance)
    debit_amount = float(amount)
    new_balance = current_balance - debit_amount

    account.balance = new_balance
    return new_balance
