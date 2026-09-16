from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class TransactionPayment(Base):
    """
    Representa um pagamento parcial de uma transacao.
    Permite dividir uma compra em multiplas formas de pagamento.
    Ex: R$300 no VA + R$200 no debito = R$500 total
    """

    __tablename__ = "transaction_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )

    # Detalhes do pagamento
    payment_method: Mapped[str] = mapped_column(String(30))  # PaymentMethod enum value
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )

    # Links opcionais para detalhes especificos do cartao
    benefit_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("benefit_cards.id", ondelete="SET NULL"), index=True
    )
    credit_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("credit_cards.id", ondelete="SET NULL")
    )

    # Ordem de exibicao
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    transaction: Mapped["Transaction"] = relationship(back_populates="payments")
    account: Mapped["Account"] = relationship(lazy="noload")
    benefit_card: Mapped["BenefitCard | None"] = relationship(lazy="noload")
    credit_card: Mapped["CreditCard | None"] = relationship(lazy="noload")


from .account import Account
from .benefit_card import BenefitCard
from .credit_card import CreditCard
from .transaction import Transaction
