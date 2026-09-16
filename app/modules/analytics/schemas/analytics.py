from datetime import date as date_type

from pydantic import BaseModel


class CategorySummary(BaseModel):
    category_id: int | None
    category_name: str
    total: float
    count: int
    percentage: float
    average: float
    trend: float | None = None  # variacao vs periodo anterior


class MerchantSummary(BaseModel):
    merchant_id: int | None
    merchant_name: str
    total: float
    count: int


class AnalyticsSummary(BaseModel):
    period_start: date_type
    period_end: date_type

    total_income: float
    total_expense: float
    balance: float
    margin: float  # receita - despesa

    fixed_expenses: float
    variable_expenses: float

    # Breakdown de despesas por tipo de pagamento
    credit_card_expenses: float = 0  # Despesas no cartao de credito
    debit_cash_expenses: float = 0  # Despesas no debito/dinheiro

    # Valores pendentes (faturas nao pagas)
    pending_invoices: float = 0  # Faturas de cartao a pagar
    pending_total: float = 0  # Total a pagar (faturas + recorrentes pendentes)
    available_balance: float = 0  # Receita - Despesas - Pendentes

    categories: list[CategorySummary]
    top_merchants: list[MerchantSummary]

    # Comparativo
    previous_period_expense: float | None = None
    expense_variation: float | None = None


class PaymentMethodSummary(BaseModel):
    """Resumo de gastos por metodo de pagamento"""

    payment_method: str | None
    payment_method_display: str
    total: float
    count: int
    percentage: float
    average: float


class PaymentMethodReport(BaseModel):
    """Relatorio completo de gastos por metodo de pagamento"""

    period_start: date_type
    period_end: date_type
    total_expenses: float
    by_payment_method: list[PaymentMethodSummary]


class InsightType(str):
    LEAK = "leak"  # vazamentos (pequenos gastos recorrentes)
    DRIVER = "driver"  # principal driver de aumento
    OPPORTUNITY = "opportunity"  # oportunidade de corte
    ANOMALY = "anomaly"  # gasto fora do padrao
    CREDIT_ALERT = "credit_alert"  # alertas de limite de credito
    INTEREST_WARNING = "interest_warning"  # avisos de juros altos
    CONSOLIDATION = "consolidation"  # oportunidade de consolidacao


class InsightResponse(BaseModel):
    type: str
    title: str
    description: str
    impact_value: float  # impacto mensal estimado
    calculation: str  # explicacao do calculo
    action: str  # acao sugerida
    category_id: int | None = None
    merchant_id: int | None = None
    credit_card_id: int | None = None
