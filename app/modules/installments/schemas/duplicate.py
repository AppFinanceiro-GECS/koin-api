"""Schemas para detecção e resolução de duplicatas"""

from datetime import date

from pydantic import BaseModel, Field

from app.modules.installments.schemas.installment import InstallmentSeriesResponse


class ConflictDetail(BaseModel):
    """Detalhes de um conflito entre duas séries"""

    installment_number: int
    series_a_transaction_id: int | None = None
    series_a_date: date | None = None
    series_b_transaction_id: int | None = None
    series_b_date: date | None = None
    description: str


class DuplicateGroup(BaseModel):
    """Grupo de séries potencialmente duplicadas"""

    series: list[InstallmentSeriesResponse]
    similarity_score: float
    conflicts: list[ConflictDetail]
    suggested_primary_id: int
    estimated_excess: float = 0.0  # Valor a mais devido a duplicatas


class DuplicateGroupsResponse(BaseModel):
    """Response com grupos de duplicatas detectadas"""

    duplicate_groups: list[DuplicateGroup]
    total_groups: int


class MergeSeriesRequest(BaseModel):
    """Request para mesclar duas séries"""

    source_series_id: int = Field(description="Série que será mesclada (removida)")
    target_series_id: int = Field(description="Série que receberá as transações")
    conflict_resolution: str = Field(
        default="keep_oldest",
        description="Como resolver conflitos: keep_oldest, keep_newest, keep_both",
    )
    new_merchant_name: str | None = Field(
        default=None, description="Novo nome do merchant (opcional)"
    )


class UpdateSeriesRequest(BaseModel):
    """Request para atualizar série"""

    description: str | None = None
    merchant_name: str | None = None
    not_duplicate_with: list[int] | None = Field(
        default=None, description="IDs de séries para não sugerir como duplicata"
    )


class TransactionDuplicatePair(BaseModel):
    """Par de transações potencialmente duplicadas"""

    transaction_a_id: int
    transaction_a_description: str
    transaction_a_date: date
    transaction_a_amount: float
    transaction_a_is_installment: bool

    transaction_b_id: int
    transaction_b_description: str
    transaction_b_date: date
    transaction_b_amount: float
    transaction_b_is_installment: bool

    similarity_score: float
    amount_difference: float
    days_apart: int
    suggested_action: str = Field(description="Ação sugerida: delete_a, delete_b, review")


class TransactionDuplicatesResponse(BaseModel):
    """Response com pares de transações duplicadas"""

    duplicate_pairs: list[TransactionDuplicatePair]
    total_pairs: int
    estimated_excess: float = Field(description="Valor estimado em excesso devido a duplicatas")
