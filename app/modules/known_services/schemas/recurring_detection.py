"""Schemas para detecção de transações recorrentes"""

from enum import Enum

from pydantic import BaseModel


class DuplicateType(str, Enum):
    """Tipo de duplicidade detectada"""

    NONE = "none"  # Sem duplicidade
    LEGITIMATE = "legitimate"  # Duplicidade legítima (2 assinaturas)
    SUSPICIOUS = "suspicious"  # Suspeito (valores/datas muito próximos)
    ERROR = "error"  # Provável erro (3+ cobranças)


class DuplicateAnalysis(BaseModel):
    """Análise de duplicidade no mesmo período"""

    duplicate_type: DuplicateType = DuplicateType.NONE
    reason: str = ""
    occurrences_count: int = 1  # Quantas vezes aparece no período
    other_amounts: list[float] = []  # Valores das outras ocorrências


class RecurringSuggestion(BaseModel):
    """Sugestão para criar recorrência"""

    name: str
    amount: float
    frequency: str = "monthly"
    default_category: str | None = None
    day_of_month: int | None = None  # Inferido da data da transação


class KnownServiceResponse(BaseModel):
    """Serviço conhecido do catálogo"""

    id: int
    name: str
    default_category: str | None
    default_frequency: str
    logo_url: str | None

    model_config = {"from_attributes": True}


class RecurringDetection(BaseModel):
    """Resultado da detecção de recorrência para um item extraído"""

    # Detecção de serviço conhecido (catálogo global)
    is_known_service: bool = False
    known_service_id: int | None = None
    known_service_name: str | None = None

    # Vinculação com recorrência do usuário
    is_user_recurring: bool = False
    user_recurring_id: int | None = None
    user_recurring_name: str | None = None

    # Análise de duplicidade
    duplicate_analysis: DuplicateAnalysis | None = None

    # Sugestão de cadastro (se não existe para o usuário)
    suggested_recurring: RecurringSuggestion | None = None

    # Confiança da detecção (0.0 a 1.0)
    confidence: float = 0.0

    # Tags para o frontend
    @property
    def display_tag(self) -> str | None:
        """Retorna a tag para exibição no frontend"""
        if (
            self.duplicate_analysis
            and self.duplicate_analysis.duplicate_type == DuplicateType.SUSPICIOUS
        ):
            return "duplicate_warning"
        if (
            self.duplicate_analysis
            and self.duplicate_analysis.duplicate_type == DuplicateType.ERROR
        ):
            return "duplicate_error"
        if self.is_user_recurring:
            return "recurring"
        if self.is_known_service and self.suggested_recurring:
            return "suggest_recurring"
        return None
