"""Metadados de consumo, sem prompts, respostas ou dados da fatura."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.utils import utc_now


class AIUsage(Base):
    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_created_user", "created_at", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    feature: Mapped[str] = mapped_column(String(50), index=True)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(150), index=True)
    requested_model: Mapped[str] = mapped_column(String(150))
    billing_mode: Mapped[str] = mapped_column(String(30), default="standard")
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    thinking_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer)
    pages: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    pricing_version: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AIDailyBudget(Base):
    __tablename__ = "ai_daily_budget"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    # Includes conservative reservations for in-flight/unknown calls.
    committed_usd: Mapped[Decimal] = mapped_column(Numeric(20, 10), default=Decimal("0"))


class LicenseDocumentUsage(Base):
    __tablename__ = "license_document_usage"

    license_id: Mapped[int] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"), primary_key=True
    )
    month: Mapped[date] = mapped_column(Date, primary_key=True)
    documents: Mapped[int] = mapped_column(Integer, default=0)
