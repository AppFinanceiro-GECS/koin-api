"""Utility functions for the application."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc  # noqa: UP017


def utc_now() -> datetime:
    """
    Return the current UTC time as a naive datetime.

    This replaces datetime.utcnow() which is deprecated in Python 3.12+.
    Returns naive datetime (no tzinfo) for compatibility with PostgreSQL
    TIMESTAMP WITHOUT TIME ZONE columns.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def today_br() -> date:
    """Retorna a data atual no fuso horário de Brasília."""
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()