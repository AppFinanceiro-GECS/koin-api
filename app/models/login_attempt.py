from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.utils import utc_now

from ..core.database import Base


class LoginAttempt(Base):
    """
    Rastreia tentativas de login malsucedidas por e-mail, para bloqueio
    progressivo. Guardado no Postgres (não em memória) para sobreviver a
    deploys/restarts.
    """

    __tablename__ = "login_attempts"

    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    lock_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
