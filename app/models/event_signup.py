"""Cadastro feito com o código de um evento (ex.: o stand de 28/11/2026).

A linha marca a conta como vinda do evento e guarda o que só existe nesse fluxo:
o aceite de novidades (com data e versão do texto), a confirmação do e-mail por
código e o brinde entregue no stand. Apagar a conta apaga a linha (LGPD).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class EventSignup(Base):
    __tablename__ = "event_signups"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    # Identifica o evento (EVENT_SIGNUP_SOURCE), não o código digitado
    source: Mapped[str] = mapped_column(String(50), index=True)

    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    marketing_opt_in_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consent_version: Mapped[str] = mapped_column(String(30))

    # Código de 6 dígitos mandado por e-mail; só o hash fica no banco
    verification_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verification_attempts: Mapped[int] = mapped_column(Integer, default=0)
    verification_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    verification_sends: Mapped[int] = mapped_column(Integer, default=0)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    gift_delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    user: Mapped["User"] = relationship(lazy="noload")


from .user import User
