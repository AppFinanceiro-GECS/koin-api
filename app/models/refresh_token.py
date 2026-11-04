from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.utils import utc_now

from ..core.database import Base


class RefreshToken(Base):
    """
    Um refresh token emitido (#45). Cada login abre uma família (= um aparelho);
    cada refresh revoga o token usado e emite o próximo da mesma família.
    Reusar um token já trocado revoga a família inteira (roubo provável).
    O JWT carrega só o jti; o token em si não é guardado.
    """

    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    device_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # jti do token que substituiu este na rotação; revogado sem replaced_by = logout/revogação
    replaced_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
