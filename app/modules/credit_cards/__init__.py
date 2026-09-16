"""Credit Cards Module

This module handles credit card management, invoices, and related operations.
"""

from app.modules.credit_cards.routers.credit_cards import router as credit_cards_router
from app.modules.credit_cards.routers.invoices import router as invoices_router
from app.modules.credit_cards.schemas.credit_card import (
    CreditCardBase,
    CreditCardCreate,
    CreditCardListResponse,
    CreditCardResponse,
    CreditCardUpdate,
)
from app.modules.credit_cards.schemas.invoice import (
    CardDetectionResult,
    DetectedCardInfo,
    InvoiceBase,
    InvoiceCreate,
    InvoiceDetailResponse,
    InvoiceFromDocument,
    InvoicePayment,
    InvoiceResponse,
    InvoiceSummary,
    InvoiceTransactionResponse,
    InvoiceUpdate,
)
from app.modules.credit_cards.services.invoice_service import InvoiceService

__all__ = [
    # Routers
    "credit_cards_router",
    "invoices_router",
    # Services
    "InvoiceService",
    # Credit Card Schemas
    "CreditCardBase",
    "CreditCardCreate",
    "CreditCardUpdate",
    "CreditCardResponse",
    "CreditCardListResponse",
    # Invoice Schemas
    "InvoiceBase",
    "InvoiceCreate",
    "InvoiceFromDocument",
    "InvoiceUpdate",
    "InvoicePayment",
    "InvoiceResponse",
    "InvoiceDetailResponse",
    "InvoiceTransactionResponse",
    "InvoiceSummary",
    "CardDetectionResult",
    "DetectedCardInfo",
]
