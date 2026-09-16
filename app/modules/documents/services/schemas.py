"""Schemas Pydantic para extracao de faturas"""

from pydantic import BaseModel, Field


class FutureInstallment(BaseModel):
    """Parcela futura de um parcelamento."""

    installment: int = Field(description="Numero da parcela futura")
    reference_month: int = Field(description="Mes de referencia (1-12)")
    reference_year: int = Field(description="Ano de referencia")


class FaturaItem(BaseModel):
    """Item/transacao de uma fatura."""

    description: str = Field(description="Nome do estabelecimento ou descricao da transacao")
    amount: float = Field(
        description="Valor em reais. NEGATIVO para pagamentos, creditos e estornos"
    )
    date: str | None = Field(default=None, description="Data da transacao no formato YYYY-MM-DD")
    category: str = Field(
        description="Categoria: alimentacao, transporte, mercado, lazer, saude, moradia, "
        "roupas, eletronicos, assinaturas, taxas, pagamento, credito, estorno, "
        "saldo_anterior, outros"
    )
    transaction_type: str = Field(
        description="Tipo: compra (default), estorno, anuidade, pagamento, credito, encargo, saldo_anterior"
    )
    is_installment: bool = Field(default=False, description="Se e parcelado")
    installment_current: int | None = Field(
        default=None, description="Parcela atual (ex: 3 de 3/12)"
    )
    installment_total: int | None = Field(
        default=None, description="Total de parcelas (ex: 12 de 3/12)"
    )
    future_installments: list[FutureInstallment] | None = Field(
        default=None, description="Parcelas futuras restantes. Apenas se is_installment=true"
    )
    # Campos para cupom fiscal (grocery tracking)
    quantity: float | None = Field(default=None, description="Quantidade do produto")
    unit: str | None = Field(default=None, description="Unidade de medida (kg, un, L, etc)")
    unit_price: float | None = Field(default=None, description="Preco unitario")
    grocery_category: str | None = Field(
        default=None,
        description="Categoria de mercado: fruits_vegetables, meat_fish, dairy, bakery, "
        "beverages, snacks, frozen, canned, grains_pasta, condiments, "
        "cleaning, hygiene, baby, pet, household, other",
    )
    necessity_type: str | None = Field(
        default=None,
        description="Tipo de necessidade: essential (basico) ou non_essential (superfluo)",
    )
    discount_amount: float | None = Field(
        default=None, description="Valor do desconto aplicado neste item"
    )
    original_amount: float | None = Field(
        default=None, description="Valor original antes do desconto"
    )
    # Identificação do cartão (para faturas com múltiplos cartões)
    card_last_digits: str | None = Field(
        default=None, description="Ultimos 4 digitos do cartao ao qual esta transacao pertence"
    )


class CardInfo(BaseModel):
    """Informacoes do cartao de credito."""

    card_issuer: str = Field(
        description="Emissor/banco: nubank, itau, bradesco, santander, inter, bb, digio, carrefour, bradescard"
    )
    card_bank: str | None = Field(default=None, description="Banco emissor completo")
    card_brand: str | None = Field(
        default=None, description="Bandeira: visa, mastercard, elo, hipercard, amex, diners"
    )
    card_partner: str | None = Field(
        default=None, description="Parceiro co-branded: amazon, smiles, latam, rappi, ifood, livelo"
    )
    card_last_digits: str | None = Field(default=None, description="Ultimos 4 digitos do cartao")
    card_name: str | None = Field(default=None, description="Nome completo do cartao")

    invoice_month: int = Field(description="Mes do VENCIMENTO da fatura (1-12)")
    invoice_year: int = Field(description="Ano do VENCIMENTO da fatura")
    closing_date: str | None = Field(default=None, description="Data de fechamento YYYY-MM-DD")
    closing_day: int | None = Field(default=None, description="Dia do fechamento (1-31)")
    due_date: str = Field(description="Data de vencimento YYYY-MM-DD")
    due_day: int | None = Field(default=None, description="Dia do vencimento (1-31)")
    total_amount: float = Field(description="Valor TOTAL A PAGAR desta fatura")

    credit_limit: float | None = Field(default=None, description="Limite total do cartao")
    credit_used: float | None = Field(default=None, description="Limite utilizado/comprometido")
    credit_available: float | None = Field(default=None, description="Limite disponivel")


class FaturaExtracao(BaseModel):
    """Resultado da extracao de uma fatura de cartao."""

    document_type: str = Field(
        description="Tipo: fatura_cartao, cupom_fiscal, comprovante, extrato"
    )
    card_info: CardInfo | None = Field(
        default=None,
        description="Informacoes do cartao. OBRIGATORIO se document_type=fatura_cartao",
    )
    items: list[FaturaItem] = Field(description="Lista de transacoes/itens extraidos")


# Schema simplificado para document_annotation do Mistral OCR
# Sem campos de cupom fiscal para não confundir o modelo
class AnnotationItem(BaseModel):
    """Item de fatura para document_annotation."""

    description: str = Field(
        description="Nome do estabelecimento ou descricao da transacao, exatamente como no documento"
    )
    amount: float = Field(description="Valor em reais. NEGATIVO para creditos e estornos")
    date: str | None = Field(default=None, description="Data da transacao no formato YYYY-MM-DD")
    category: str = Field(
        description="Categoria: alimentacao, transporte, mercado, veiculos, educacao, "
        "vestuario, turismo_e_entretenimento, diversos, servicos, saude, outros"
    )
    transaction_type: str = Field(
        default="compra", description="Tipo: compra, estorno, anuidade, pagamento, credito"
    )
    is_installment: bool = Field(default=False, description="Se e parcelado")
    installment_current: int | None = Field(
        default=None, description="Parcela atual (ex: 8 de 8/12)"
    )
    installment_total: int | None = Field(
        default=None, description="Total de parcelas (ex: 12 de 8/12)"
    )
    card_last_digits: str | None = Field(
        default=None, description="Ultimos 4 digitos do cartao ao qual esta transacao pertence"
    )


class AnnotationExtracao(BaseModel):
    """Schema simplificado para document_annotation do Mistral OCR."""

    document_type: str = Field(default="fatura_cartao", description="Tipo do documento")
    card_info: CardInfo | None = Field(default=None, description="Informacoes do cartao de credito")
    items: list[AnnotationItem] = Field(
        description="Lista de TODAS as transacoes dos lancamentos atuais (NAO incluir proximas faturas)"
    )
