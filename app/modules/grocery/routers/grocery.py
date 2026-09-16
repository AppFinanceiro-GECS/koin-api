"""Grocery (Mercado) API Endpoints"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import CurrentUser, DbSession
from app.models.grocery import (
    GroceryCategory,
    NecessityType,
    ShoppingListStatus,
)
from app.modules.grocery.schemas.analytics import (
    CheapestPriceResponse,
    GroceryAnalyticsByCategory,
    GroceryAnalyticsByNecessity,
    GroceryAnalyticsSpending,
    GroceryBudgetStatus,
    GroceryInsights,
    PriceHistoryResponse,
)
from app.modules.grocery.schemas.product import (
    GroceryProductCreate,
    GroceryProductResponse,
    GroceryProductUpdate,
)
from app.modules.grocery.schemas.purchase import (
    BackfillRequest,
    BackfillResponse,
    GroceryPurchaseBulkCreate,
    GroceryPurchaseComparison,
    GroceryPurchaseCreate,
    GroceryPurchaseResponse,
    GroceryPurchaseSummary,
    GroceryPurchaseUpdate,
)
from app.modules.grocery.schemas.shopping_list import (
    ShoppingListCreate,
    ShoppingListGenerateRequest,
    ShoppingListItemCreate,
    ShoppingListItemResponse,
    ShoppingListItemUpdate,
    ShoppingListResponse,
    ShoppingListUpdate,
)
from app.modules.grocery.schemas.smart_list import (
    SmartListFullResponse,
    SmartListGenerateRequest,
)
from app.modules.grocery.services import (
    GroceryAnalyticsService,
    GroceryService,
    PriceTrackingService,
    ShoppingListService,
    SmartListService,
)

router = APIRouter()


# ============================================
# Products
# ============================================


@router.get("/products", response_model=list[GroceryProductResponse])
async def list_products(
    current_user: CurrentUser,
    db: DbSession,
    search: str | None = None,
    category: GroceryCategory | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Lista produtos cadastrados (do usuário + sistema)"""
    service = GroceryService(db)
    return await service.list_products(current_user, search, category, limit, offset)


@router.post("/products", response_model=GroceryProductResponse, status_code=201)
async def create_product(
    data: GroceryProductCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cria novo produto personalizado"""
    service = GroceryService(db)
    product = await service.create_product(current_user, data)
    return service._build_product_response(product)


@router.get("/products/{product_id}", response_model=GroceryProductResponse)
async def get_product(
    product_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna um produto específico"""
    service = GroceryService(db)
    product = await service.get_product(current_user, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado")
    return product


@router.patch("/products/{product_id}", response_model=GroceryProductResponse)
async def update_product(
    product_id: int,
    data: GroceryProductUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza categoria/necessidade de um produto"""
    service = GroceryService(db)
    product = await service.update_product(current_user, product_id, data)
    return service._build_product_response(product)


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(
    product_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove um produto personalizado"""
    service = GroceryService(db)
    await service.delete_product(current_user, product_id)


# ============================================
# Purchases
# ============================================


@router.get("/purchases", response_model=list[GroceryPurchaseResponse])
async def list_purchases(
    current_user: CurrentUser,
    db: DbSession,
    start_date: date | None = None,
    end_date: date | None = None,
    category: GroceryCategory | None = None,
    necessity_type: NecessityType | None = None,
    merchant_id: int | None = None,
    search: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Lista compras de mercado com filtros"""
    service = GroceryService(db)
    return await service.list_purchases(
        current_user,
        start_date,
        end_date,
        category,
        necessity_type,
        merchant_id,
        search,
        limit,
        offset,
    )


@router.post("/purchases", response_model=GroceryPurchaseResponse, status_code=201)
async def create_purchase(
    data: GroceryPurchaseCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Adiciona uma compra manual (sem cupom)"""
    service = GroceryService(db)
    purchase = await service.create_purchase(current_user, data)
    return service._build_purchase_response(purchase)


@router.post("/purchases/bulk", response_model=list[GroceryPurchaseResponse], status_code=201)
async def create_purchases_bulk(
    data: GroceryPurchaseBulkCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Adiciona múltiplos itens de uma vez (de um cupom)"""
    service = GroceryService(db)
    purchases = await service.create_purchases_bulk(current_user, data)
    return [service._build_purchase_response(p) for p in purchases]


@router.get("/purchases/summary", response_model=GroceryPurchaseSummary)
async def get_purchase_summary(
    current_user: CurrentUser,
    db: DbSession,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
):
    """Resumo mensal de compras por categoria"""
    service = GroceryService(db)
    return await service.get_purchase_summary(current_user, month, year)


@router.get("/purchases/comparison", response_model=GroceryPurchaseComparison)
async def get_purchase_comparison(
    current_user: CurrentUser,
    db: DbSession,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
):
    """Comparação de gastos entre meses"""
    service = GroceryService(db)
    return await service.get_purchase_comparison(current_user, month, year)


@router.get("/purchases/{purchase_id}", response_model=GroceryPurchaseResponse)
async def get_purchase(
    purchase_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna uma compra específica"""
    service = GroceryService(db)
    purchase = await service.get_purchase(current_user, purchase_id)
    if not purchase:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compra não encontrada")
    return purchase


@router.patch("/purchases/{purchase_id}", response_model=GroceryPurchaseResponse)
async def update_purchase(
    purchase_id: int,
    data: GroceryPurchaseUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza categoria/necessidade de uma compra"""
    service = GroceryService(db)
    purchase = await service.update_purchase(current_user, purchase_id, data)
    return service._build_purchase_response(purchase)


@router.delete("/purchases/{purchase_id}", status_code=204)
async def delete_purchase(
    purchase_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove uma compra"""
    service = GroceryService(db)
    await service.delete_purchase(current_user, purchase_id)


# ============================================
# Shopping Lists
# ============================================


@router.get("/lists", response_model=list[ShoppingListResponse])
async def list_shopping_lists(
    current_user: CurrentUser,
    db: DbSession,
    status_filter: ShoppingListStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Lista todas as listas de compras (compartilhadas no household)"""
    service = ShoppingListService(db)
    return await service.list_shopping_lists(current_user, status_filter, limit, offset)


@router.post("/lists", response_model=ShoppingListResponse, status_code=201)
async def create_shopping_list(
    data: ShoppingListCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Cria nova lista de compras manual"""
    service = ShoppingListService(db)
    lst = await service.create_shopping_list(current_user, data)
    return await service.get_shopping_list(current_user, lst.id)


@router.post("/lists/generate", response_model=ShoppingListResponse, status_code=201)
async def generate_shopping_list(
    data: ShoppingListGenerateRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Gera lista de compras baseada no histórico"""
    service = ShoppingListService(db)
    lst = await service.generate_from_history(current_user, data)
    return await service.get_shopping_list(current_user, lst.id)


@router.post("/lists/generate-smart", response_model=SmartListFullResponse, status_code=201)
async def generate_smart_shopping_list(
    data: SmartListGenerateRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Gera lista de compras inteligente usando IA (LLM).

    A IA analisa o historico de compras e:
    - Agrupa produtos similares por tipo (ignora marca)
    - Normaliza nomes abreviados de cupons fiscais
    - Filtra itens que nao sao de supermercado (restaurantes, delivery)
    - Calcula urgencia de recompra baseada na frequencia
    - Gera insights sobre habitos de compra
    """
    service = SmartListService(db)
    return await service.generate_smart_list(current_user, data)


@router.get("/lists/{list_id}", response_model=ShoppingListResponse)
async def get_shopping_list(
    list_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Retorna lista com itens"""
    service = ShoppingListService(db)
    lst = await service.get_shopping_list(current_user, list_id)
    if not lst:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lista não encontrada")
    return lst


@router.patch("/lists/{list_id}", response_model=ShoppingListResponse)
async def update_shopping_list(
    list_id: int,
    data: ShoppingListUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza lista de compras"""
    service = ShoppingListService(db)
    await service.update_shopping_list(current_user, list_id, data)
    return await service.get_shopping_list(current_user, list_id)


@router.delete("/lists/{list_id}", status_code=204)
async def delete_shopping_list(
    list_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Deleta lista de compras"""
    service = ShoppingListService(db)
    await service.delete_shopping_list(current_user, list_id)


# ============================================
# Shopping List Items
# ============================================


@router.post("/lists/{list_id}/items", response_model=ShoppingListItemResponse, status_code=201)
async def add_list_item(
    list_id: int,
    data: ShoppingListItemCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Adiciona item à lista"""
    service = ShoppingListService(db)
    item = await service.add_item(current_user, list_id, data)
    return service._build_item_response(item)


@router.patch("/lists/{list_id}/items/{item_id}", response_model=ShoppingListItemResponse)
async def update_list_item(
    list_id: int,
    item_id: int,
    data: ShoppingListItemUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Atualiza item (marcar/desmarcar, editar quantidade)"""
    service = ShoppingListService(db)
    item = await service.update_item(current_user, list_id, item_id, data)
    return service._build_item_response(item)


@router.delete("/lists/{list_id}/items/{item_id}", status_code=204)
async def delete_list_item(
    list_id: int,
    item_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove item da lista"""
    service = ShoppingListService(db)
    await service.delete_item(current_user, list_id, item_id)


# ============================================
# Price Tracking
# ============================================


@router.get("/prices/{product_id}", response_model=PriceHistoryResponse)
async def get_price_history(
    product_id: int,
    current_user: CurrentUser,
    db: DbSession,
    days: int = Query(90, ge=7, le=365),
):
    """Histórico de preços de um produto"""
    service = PriceTrackingService(db)
    history = await service.get_price_history(current_user, product_id, days)
    if not history:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Produto não encontrado")
    return history


@router.get("/prices/cheapest", response_model=CheapestPriceResponse)
async def get_cheapest_prices(
    current_user: CurrentUser,
    db: DbSession,
    product_ids: str | None = Query(None, description="Comma-separated product IDs"),
    limit: int = Query(20, ge=1, le=100),
):
    """Onde comprar mais barato"""
    service = PriceTrackingService(db)

    ids = None
    if product_ids:
        ids = [int(x.strip()) for x in product_ids.split(",")]

    return await service.get_cheapest_prices(current_user, ids, limit)


# ============================================
# Analytics
# ============================================


@router.get("/analytics/spending", response_model=GroceryAnalyticsSpending)
async def get_spending_analytics(
    current_user: CurrentUser,
    db: DbSession,
    start_date: date | None = None,
    end_date: date | None = None,
    granularity: str = Query("week", pattern="^(day|week|month)$"),
):
    """Gastos totais ao longo do tempo"""
    service = GroceryAnalyticsService(db)
    return await service.get_spending_over_time(current_user, start_date, end_date, granularity)


@router.get("/analytics/by-category", response_model=GroceryAnalyticsByCategory)
async def get_category_analytics(
    current_user: CurrentUser,
    db: DbSession,
    start_date: date | None = None,
    end_date: date | None = None,
):
    """Gastos por categoria"""
    service = GroceryAnalyticsService(db)
    return await service.get_by_category(current_user, start_date, end_date)


@router.get("/analytics/by-necessity", response_model=GroceryAnalyticsByNecessity)
async def get_necessity_analytics(
    current_user: CurrentUser,
    db: DbSession,
    start_date: date | None = None,
    end_date: date | None = None,
):
    """Essencial vs Supérfluo"""
    service = GroceryAnalyticsService(db)
    return await service.get_by_necessity(current_user, start_date, end_date)


@router.get("/insights", response_model=GroceryInsights)
async def get_insights(
    current_user: CurrentUser,
    db: DbSession,
    start_date: date | None = None,
    end_date: date | None = None,
):
    """Insights de gastos de mercado"""
    service = GroceryAnalyticsService(db)
    return await service.get_insights(current_user, start_date, end_date)


@router.get("/budget/status", response_model=GroceryBudgetStatus)
async def get_budget_status(
    current_user: CurrentUser,
    db: DbSession,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
):
    """Status do orçamento de mercado do mês"""
    service = GroceryAnalyticsService(db)
    return await service.get_budget_status(current_user, month, year)


# ============================================
# Backfill
# ============================================


@router.post("/backfill", response_model=BackfillResponse)
async def backfill_grocery_purchases(
    data: BackfillRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Migra transações antigas de categorias de mercado para grocery_purchases.

    Por padrão executa em modo dry_run (apenas simula).
    Defina dry_run=false para criar os registros.

    Categorias padrão: Supermercado, alimentação, Mercado
    """
    service = GroceryService(db)
    return await service.backfill_grocery_purchases(current_user, data)
