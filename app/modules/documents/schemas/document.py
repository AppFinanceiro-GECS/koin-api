from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, field_validator

from app.models.document import DocumentStatus, DocumentType
from app.modules.known_services.schemas.recurring_detection import RecurringDetection


class FutureInstallmentResponse(BaseModel):
    """Parcela futura calculada pelo LLM"""

    installment: int  # Numero da parcela (ex: 4)
    reference_month: int  # Mes de referencia (1-12)
    reference_year: int  # Ano de referencia


class ExtractedItemResponse(BaseModel):
    """Item individual extraido do documento"""

    description: str
    amount: float
    date: str | None  # YYYY-MM-DD
    category: str | None  # categoria sugerida pelo LLM
    confidence: float = 0.9

    # Tipo de transacao extraido pelo LLM
    # Valores: compra, estorno, credito, pagamento, anuidade, encargo, saldo_anterior
    transaction_type: str | None = None

    # Informacoes de parcelamento
    is_installment: bool = False
    installment_current: int | None = None  # Parcela atual (ex: 3)
    installment_total: int | None = None  # Total de parcelas (ex: 12)

    # Parcelas futuras calculadas pelo LLM (para Santander/Itau que mostram todas as parcelas)
    future_installments: list[FutureInstallmentResponse] | None = None

    # Flag de duplicado (ja existe transacao similar no banco)
    is_duplicate: bool = False
    existing_transaction_id: int | None = None

    # Deteccao de recorrencia (Netflix, Spotify, etc.)
    recurring_detection: RecurringDetection | None = None

    # Campos para cupom fiscal (grocery tracking)
    quantity: float | None = None  # Quantidade do produto
    unit: str | None = None  # Unidade de medida (kg, un, L, etc)
    unit_price: float | None = None  # Preco unitario
    grocery_category: str | None = None  # Categoria de mercado detalhada
    necessity_type: str | None = None  # essential ou non_essential
    discount_amount: float | None = None  # Valor do desconto aplicado neste item
    original_amount: float | None = None  # Valor original antes do desconto

    class Config:
        from_attributes = True


class InstallmentAnalysisResponse(BaseModel):
    """Resultado da analise de parcela"""

    is_installment: bool
    series_found: dict | None = None
    series_status: dict | None = None
    installment_exists: bool = False
    suggestion: str | None = (
        None  # create_single, create_series, add_to_series, mark_previous_paid, skip
    )
    suggested_series: dict | None = None
    pending_installments: list[dict] | None = None


class DocumentExtractionResponse(BaseModel):
    """Extracao salva no banco (para historico)"""

    id: int
    version: int

    amount: float | None
    amount_confidence: float | None
    amount_source: str | None

    date: datetime | None
    date_confidence: float | None
    date_source: str | None

    merchant_name: str | None
    merchant_confidence: float | None
    merchant_cnpj: str | None

    items: dict | None
    payment_method: str | None
    installments: int | None
    suggested_category_id: int | None

    created_at: datetime

    class Config:
        from_attributes = True


class CardInfoResponse(BaseModel):
    """Informacoes do cartao extraidas de uma fatura"""

    # Identificacao do cartao
    card_issuer: str | None = None  # Codigo do emissor (nubank, itau, bradesco, bradescard)
    card_bank: str | None = None  # Nome completo do banco (Bradesco, Itau Unibanco)
    card_brand: str | None = None  # Bandeira (visa, mastercard, elo, hipercard, amex)
    card_partner: str | None = None  # Parceiro co-branded (amazon, smiles, latam)
    card_last_digits: str | None = None  # Ultimos 4 digitos
    card_name: str | None = None  # Nome completo do cartao (ex: Bradesco Amazon Visa)

    # Informacoes da fatura
    invoice_month: int | None = None
    invoice_year: int | None = None
    closing_date: str | None = None  # Data de fechamento YYYY-MM-DD
    closing_day: int | None = None  # Dia do fechamento (1-31)
    due_date: str | None = None  # Data de vencimento YYYY-MM-DD
    due_day: int | None = None  # Dia do vencimento (1-31)
    total_amount: float | None = None

    # Limites do cartao (se disponivel na fatura)
    credit_limit: float | None = None  # Limite total
    credit_used: float | None = None  # Limite utilizado
    credit_available: float | None = None  # Limite disponivel


class CardSuggestionResponse(BaseModel):
    """Cartão que a fatura descreve, para cadastrar com um toque"""

    name: str
    last_four_digits: str | None = None
    bank_id: str | None = None
    card_brand: str | None = None
    closing_day: int | None = None
    due_day: int | None = None
    credit_limit: float | None = None


class CardMatchResponse(BaseModel):
    """
    De qual cartão é este documento.

    matched: um cartão cadastrado bate (pelo final, ou pelo banco quando falta o final)
    new: é fatura de um cartão que ainda não existe; `suggestion` traz os dados para cadastrar
    ambiguous: mais de um cartão bate; `candidate_ids` lista quais
    unregistered: comprovante de compra com o final de um cartão que não está cadastrado;
        `suggestion` traz final, bandeira e banco para o app perguntar se quer cadastrar
        (o comprovante nunca cria o cartão sozinho)
    none: o documento não traz dados de cartão (cupom, comprovante de PIX etc.)
    """

    status: str
    credit_card_id: int | None = None
    credit_card_name: str | None = None
    candidate_ids: list[int] = []
    suggestion: CardSuggestionResponse | None = None


class PaymentCardResponse(BaseModel):
    """Cartão citado num comprovante: o da compra ou o da fatura paga"""

    card_issuer: str | None = None
    card_bank: str | None = None
    card_brand: str | None = None
    card_last_digits: str | None = None


class InvoicePaymentCandidateResponse(BaseModel):
    """Fatura que um comprovante de pagamento pode quitar"""

    invoice_id: int
    credit_card_id: int
    credit_card_name: str
    reference_month: int
    reference_year: int
    due_date: date
    total_amount: float
    remaining_amount: float


class InvoicePaymentMatchResponse(BaseModel):
    """
    Qual fatura o comprovante de pagamento quita (só para comprovante_fatura).

    matched: `invoice` é a fatura em aberto do cartão; `amount_matches` diz se o valor pago
        fecha com o total ou com o que falta pagar (senão é pagamento parcial)
    ambiguous: mais de uma fatura serve; `candidates` lista quais
    already_paid: a fatura com esse valor já está paga (`invoice`)
    none: nenhuma fatura em aberto bate pelo banco e pelo valor
    O app marca como paga com POST /invoices/{invoice_id}/pay e a conta de origem escolhida.
    """

    status: str
    amount_paid: float | None = None
    payment_date: date | None = None
    invoice: InvoicePaymentCandidateResponse | None = None
    amount_matches: bool = False
    candidates: list[InvoicePaymentCandidateResponse] = []


class DetectedPaymentResponse(BaseModel):
    """Pagamento detectado no cupom fiscal"""

    method: str  # voucher_va, debit_card, pix, etc.
    amount: float
    label: str  # Label original do OCR (ex: "CARTAO ALIMENTACAO")
    sequence: int


class PaymentInfoResponse(BaseModel):
    """Informacoes de pagamento extraidas do cupom"""

    total: float | None = None
    subtotal: float | None = None
    discount: float | None = None
    payments: list[DetectedPaymentResponse] = []
    store_name: str | None = None  # Nome do estabelecimento
    store_cnpj: str | None = None  # CNPJ do estabelecimento


class DocumentResponse(BaseModel):
    id: int
    file_hash: str
    original_filename: str
    mime_type: str
    status: DocumentStatus
    document_type: DocumentType | None = None
    error_message: str | None
    # RN016: o app decide pelo código; next_retry_at diz quando a leitura volta a tentar
    error_code: str | None = None
    next_retry_at: datetime | None = None
    # #37: received → extracting → validating → done (ou waiting / failed)
    stage: str | None = None
    created_at: datetime
    processed_at: datetime | None

    # Lista de itens extraidos (cada um e uma transacao potencial)
    extracted_items: list[ExtractedItemResponse] = []

    # Alerta de duplicata (nao bloqueia, apenas informa)
    is_duplicate: bool = False

    # Informacoes do cartao (apenas para fatura_cartao)
    card_info: CardInfoResponse | None = None

    # De qual cartão é o documento (reconhecido pelo final e pelo banco)
    card_match: CardMatchResponse | None = None

    # Comprovantes: cartão da compra ou da fatura paga (lido do documento)
    payment_card: PaymentCardResponse | None = None

    # Comprovante de pagamento de fatura: qual fatura em aberto ele quita
    invoice_payment: InvoicePaymentMatchResponse | None = None

    # Informacoes de pagamento (apenas para cupom_fiscal)
    payment_info: PaymentInfoResponse | None = None

    @field_validator("document_type", mode="before")
    @classmethod
    def normalize_document_type(cls, v: Any) -> DocumentType | None:
        if v is None or v == "":
            return None
        return DocumentType.from_string(v)

    class Config:
        from_attributes = True


class DocumentAsyncUploadResponse(BaseModel):
    """Resposta para upload async (retorno imediato)"""

    id: int
    status: DocumentStatus
    message: str
    stage: str = "received"
