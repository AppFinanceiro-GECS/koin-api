"""
Price Tracking Service - Track and analyze price history
"""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.grocery import (
    GroceryPriceHistory,
    GroceryProduct,
)
from app.models.user import User
from app.modules.grocery.schemas.analytics import (
    CheapestPriceResponse,
    MerchantPrice,
    PriceHistoryResponse,
    PricePoint,
)


class PriceTrackingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_price_history(
        self,
        user: User,
        product_id: int,
        days: int = 90,
    ) -> PriceHistoryResponse | None:
        """Get price history for a product"""
        # Get product
        result = await self.db.execute(
            select(GroceryProduct).where(GroceryProduct.id == product_id)
        )
        product = result.scalar_one_or_none()

        if not product:
            return None

        # Get price history
        start_date = date.today() - timedelta(days=days)
        query = (
            select(GroceryPriceHistory)
            .where(
                GroceryPriceHistory.product_id == product_id,
                GroceryPriceHistory.recorded_at >= start_date,
            )
            .options(selectinload(GroceryPriceHistory.merchant))
            .order_by(GroceryPriceHistory.recorded_at.asc())
        )

        result = await self.db.execute(query)
        history_records = result.scalars().all()

        if not history_records:
            return PriceHistoryResponse(
                product_id=product_id,
                product_name=product.name,
                unit=product.default_unit,
                current_price=None,
                min_price=None,
                max_price=None,
                avg_price=None,
                history=[],
            )

        # Build history points
        history = [
            PricePoint(
                date=h.recorded_at,
                price=float(h.price),
                merchant_name=h.merchant.name if h.merchant else None,
            )
            for h in history_records
        ]

        # Calculate stats
        prices = [float(h.price) for h in history_records]
        current_price = prices[-1] if prices else None
        min_price = min(prices) if prices else None
        max_price = max(prices) if prices else None
        avg_price = sum(prices) / len(prices) if prices else None

        return PriceHistoryResponse(
            product_id=product_id,
            product_name=product.name,
            unit=history_records[-1].unit if history_records else product.default_unit,
            current_price=current_price,
            min_price=min_price,
            max_price=max_price,
            avg_price=round(avg_price, 2) if avg_price else None,
            history=history,
        )

    async def get_cheapest_prices(
        self,
        user: User,
        product_ids: list[int] | None = None,
        limit: int = 20,
    ) -> CheapestPriceResponse:
        """Get cheapest prices for products across merchants"""
        # Get latest prices for each product/merchant combination
        # Using subquery to get the latest date for each product/merchant
        subquery = (
            select(
                GroceryPriceHistory.product_id,
                GroceryPriceHistory.merchant_id,
                func.max(GroceryPriceHistory.recorded_at).label("max_date"),
            )
            .group_by(
                GroceryPriceHistory.product_id,
                GroceryPriceHistory.merchant_id,
            )
            .subquery()
        )

        query = (
            select(GroceryPriceHistory)
            .join(
                subquery,
                (GroceryPriceHistory.product_id == subquery.c.product_id)
                & (GroceryPriceHistory.merchant_id == subquery.c.merchant_id)
                & (GroceryPriceHistory.recorded_at == subquery.c.max_date),
            )
            .options(
                selectinload(GroceryPriceHistory.product),
                selectinload(GroceryPriceHistory.merchant),
            )
        )

        if product_ids:
            query = query.where(GroceryPriceHistory.product_id.in_(product_ids))

        result = await self.db.execute(query)
        records = result.scalars().all()

        # Group by product and find cheapest
        product_prices: dict[int, list[dict]] = {}
        for record in records:
            if record.product_id not in product_prices:
                product_prices[record.product_id] = {
                    "product_id": record.product_id,
                    "product_name": record.product.name if record.product else "Unknown",
                    "unit": record.unit,
                    "merchants": [],
                }

            merchant_data = MerchantPrice(
                merchant_id=record.merchant_id or 0,
                merchant_name=record.merchant.name if record.merchant else "Desconhecido",
                price=float(record.price),
                unit=record.unit,
                last_seen=record.recorded_at,
            )
            product_prices[record.product_id]["merchants"].append(merchant_data.model_dump())

        # Sort merchants by price for each product
        products_list = []
        for product_data in product_prices.values():
            product_data["merchants"].sort(key=lambda x: x["price"])
            products_list.append(product_data)

        # Sort products by name
        products_list.sort(key=lambda x: x["product_name"])

        return CheapestPriceResponse(products=products_list[:limit])

    async def compare_prices(
        self,
        user: User,
        product_id: int,
    ) -> list[MerchantPrice]:
        """Compare prices for a product across different merchants"""
        # Get latest price for each merchant
        subquery = (
            select(
                GroceryPriceHistory.merchant_id,
                func.max(GroceryPriceHistory.recorded_at).label("max_date"),
            )
            .where(GroceryPriceHistory.product_id == product_id)
            .group_by(GroceryPriceHistory.merchant_id)
            .subquery()
        )

        query = (
            select(GroceryPriceHistory)
            .join(
                subquery,
                (GroceryPriceHistory.merchant_id == subquery.c.merchant_id)
                & (GroceryPriceHistory.recorded_at == subquery.c.max_date),
            )
            .where(GroceryPriceHistory.product_id == product_id)
            .options(selectinload(GroceryPriceHistory.merchant))
            .order_by(GroceryPriceHistory.price.asc())
        )

        result = await self.db.execute(query)
        records = result.scalars().all()

        return [
            MerchantPrice(
                merchant_id=r.merchant_id or 0,
                merchant_name=r.merchant.name if r.merchant else "Desconhecido",
                price=float(r.price),
                unit=r.unit,
                last_seen=r.recorded_at,
            )
            for r in records
        ]
