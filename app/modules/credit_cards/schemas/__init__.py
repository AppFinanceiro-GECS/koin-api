"""Credit Cards Schemas"""

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

__all__ = [
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
