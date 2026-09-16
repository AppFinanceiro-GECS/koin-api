"""Modelo para serviços recorrentes conhecidos (Netflix, Spotify, etc)"""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.utils import utc_now


class KnownRecurringService(Base):
    """Catálogo global de serviços recorrentes conhecidos"""

    __tablename__ = "known_recurring_services"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Identificação
    name: Mapped[str] = mapped_column(String(100), index=True)  # "Netflix", "Spotify"
    patterns: Mapped[list] = mapped_column(JSON)  # ["NETFLIX", "NETFLIX.COM", "NETFLIX*"]

    # Configuração padrão sugerida
    default_category: Mapped[str | None] = mapped_column(String(50))  # "streaming", "assinaturas"
    default_frequency: Mapped[str] = mapped_column(String(20), default="monthly")  # monthly, yearly

    # Metadata
    logo_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
