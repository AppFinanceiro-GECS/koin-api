"""
Core Services - Serviços compartilhados entre módulos.
"""

from .business_day_service import (
    calculate_easter,
    get_brazilian_holidays,
    get_next_payment_date,
    get_nth_business_day,
    get_payment_date_for_income,
    is_business_day,
)
from .email_service import EmailService, email_service

__all__ = [
    "EmailService",
    "email_service",
    "get_brazilian_holidays",
    "calculate_easter",
    "is_business_day",
    "get_nth_business_day",
    "get_payment_date_for_income",
    "get_next_payment_date",
]
