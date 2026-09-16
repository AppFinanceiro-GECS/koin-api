from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.installment import InstallmentSeriesStatus


class InstallmentSeriesBase(BaseModel):
    """Base para série de parcelas"""

    description: str = Field(max_length=500)
    merchant_name: str = Field(max_length=200)
    installment_amount: float = Field(gt=0)
    installment_count: int = Field(ge=2, le=72)  # 2 a 72 parcelas
    first_installment_date: date_type
    account_id: int
    category_id: int | None = None
    purchase_date: date_type | None = None
    notes: str | None = None


class InstallmentSeriesCreate(InstallmentSeriesBase):
    """Criação de série de parcelas"""

    # Opcionalmente marcar parcelas anteriores como pagas
    mark_paid_until: int | None = None  # Marcar parcelas 1 até N como pagas
    create_future: bool = False  # Criar transações para parcelas futuras


class InstallmentSeriesResponse(BaseModel):
    """Resposta de série de parcelas"""

    id: int
    description: str
    merchant_name: str
    total_amount: float
    installment_amount: float
    installment_count: int
    paid_count: int
    remaining_count: int
    remaining_amount: float
    first_installment_date: date_type
    purchase_date: date_type | None
    account_id: int
    category_id: int | None
    first_transaction_id: int | None  # ID da transação que originou a série
    status: InstallmentSeriesStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InstallmentStatusResponse(BaseModel):
    """Status detalhado de uma parcela individual"""

    number: int
    status: str  # paid, registered, pending
    date: str | None = None
    expected_date: str | None = None
    transaction_id: int | None = None


class InstallmentSeriesDetailResponse(BaseModel):
    """Detalhes completos de uma série com status de cada parcela"""

    series_id: int
    description: str
    merchant_name: str
    total_amount: float
    installment_amount: float
    installment_count: int
    paid_count: int
    remaining_count: int
    remaining_amount: float
    status: str
    installments: list[InstallmentStatusResponse]


class ConfirmInstallmentRequest(BaseModel):
    """Confirmar transação de parcela"""

    # Identificação
    document_id: int | None = None
    account_id: int

    # Dados do item extraído
    description: str
    amount: float = Field(gt=0)
    date: date_type
    category_id: int | None = None

    # Dados de parcelamento
    installment_current: int = Field(ge=1)
    installment_total: int = Field(ge=2)

    # Opções
    series_id: int | None = None  # Se já existe série, vincular
    mark_previous_as_paid: bool = False  # Marcar anteriores como pagas
    create_future_installments: bool = False  # Criar parcelas futuras


class MarkInstallmentsPaidRequest(BaseModel):
    """Marcar parcelas anteriores como pagas"""

    series_id: int
    up_to_installment: int = Field(ge=1)


class CreateFutureInstallmentsRequest(BaseModel):
    """Criar transações para parcelas futuras"""

    series_id: int
    from_installment: int = Field(ge=1)


class PotentialDuplicateSeriesResponse(BaseModel):
    """Informações sobre uma série potencialmente duplicada"""

    series_id: int
    description: str
    merchant_name: str
    installment_count: int
    installment_amount: float
    paid_count: int
    similarity_score: float
    first_installment_date: date_type
