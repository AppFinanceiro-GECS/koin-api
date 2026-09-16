from typing import Any

from pydantic import BaseModel, Field


class ColumnInfo(BaseModel):
    """Informações de uma coluna"""

    name: str
    description: str


class TableInfo(BaseModel):
    """Informações de uma tabela"""

    name: str
    description: str
    columns: list[ColumnInfo]


class TableListResponse(BaseModel):
    """Lista de tabelas disponíveis"""

    tables: list[TableInfo]
    total: int


class QueryRequest(BaseModel):
    """Requisição de query"""

    table: str = Field(..., description="Nome da tabela para consultar")
    filters: dict[str, Any] | None = Field(None, description="Filtros exatos {coluna: valor}")
    search: str | None = Field(
        None, description="Busca em description/name (ex: 'carne', 'mercado')"
    )
    date_from: str | None = Field(None, description="Data inicial YYYY-MM-DD (ex: '2026-01-01')")
    date_to: str | None = Field(None, description="Data final YYYY-MM-DD (ex: '2026-01-31')")
    amount_min: float | None = Field(None, description="Valor mínimo")
    amount_max: float | None = Field(None, description="Valor máximo")
    order_by: str | None = Field(None, description="Coluna para ordenação")
    order_desc: bool = Field(True, description="Ordenar descendente")
    limit: int = Field(50, ge=1, le=200, description="Limite de resultados (máx 200)")
    offset: int = Field(0, ge=0, description="Offset para paginação")


class QueryResponse(BaseModel):
    """Resposta de query"""

    data: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class TableStatsResponse(BaseModel):
    """Estatísticas de uma tabela"""

    table: str
    total_records: int
    columns: dict[str, str]  # {coluna: descrição}


class ContextRequest(BaseModel):
    """
    Requisição de contexto financeiro agregado.
    RECOMENDADO para perguntas de análise financeira.
    """

    month: int | str | None = Field(
        None, description="Mês para análise (1-12 ou nome: 'janeiro', 'fevereiro', etc.)"
    )
    year: int | None = Field(
        None,
        description="Ano para análise (ex: 2026). Se não informado, usa ano atual ou anterior conforme o mês.",
    )
    date_from: str | None = Field(None, description="Data inicial YYYY-MM-DD (alternativa ao mês)")
    date_to: str | None = Field(None, description="Data final YYYY-MM-DD (alternativa ao mês)")
    search: str | None = Field(
        None,
        description="Busca por palavra-chave em descrição/estabelecimento (ex: 'carne', 'mercado', 'uber')",
    )
