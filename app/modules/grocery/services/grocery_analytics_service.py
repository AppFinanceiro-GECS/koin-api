"""
Grocery Analytics Service - Analytics and insights
"""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.grocery import (
    GROCERY_CATEGORY_DISPLAY,
    NECESSITY_TYPE_DISPLAY,
    GroceryPurchase,
    NecessityType,
)
from app.models.user import User
from app.modules.grocery.schemas.analytics import (
    CategoryBreakdown,
    GroceryAnalyticsByCategory,
    GroceryAnalyticsByNecessity,
    GroceryAnalyticsSpending,
    GroceryBudgetStatus,
    GroceryInsights,
    Insight,
    NecessityBreakdown,
    SpendingPoint,
)
from app.modules.household.utils import (
    build_ownership_filter,
    get_household_member,
    get_household_user_ids,
)


class GroceryAnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_spending_over_time(
        self,
        user: User,
        start_date: date | None = None,
        end_date: date | None = None,
        granularity: str = "week",  # "day", "week", "month"
    ) -> GroceryAnalyticsSpending:
        """Get spending analytics over time"""
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=90)

        # Get all purchases in range
        query = select(GroceryPurchase).where(
            GroceryPurchase.purchase_date >= start_date,
            GroceryPurchase.purchase_date <= end_date,
            build_ownership_filter(
                GroceryPurchase,
                GroceryPurchase.user_id,
                GroceryPurchase.ownership_type,
                user.id,
                household_user_ids,
                member,
            ),
        )

        result = await self.db.execute(query)
        purchases = result.scalars().all()

        # Group by date based on granularity
        spending_by_period: dict[date, dict] = defaultdict(
            lambda: {"total": 0, "essential": 0, "non_essential": 0}
        )

        for purchase in purchases:
            period_date = self._get_period_date(purchase.purchase_date, granularity)
            amount = float(purchase.total_price)

            spending_by_period[period_date]["total"] += amount
            if purchase.necessity_type == NecessityType.ESSENTIAL.value:
                spending_by_period[period_date]["essential"] += amount
            else:
                spending_by_period[period_date]["non_essential"] += amount

        # Convert to data points
        data_points = [
            SpendingPoint(
                date=d,
                total=round(data["total"], 2),
                essential=round(data["essential"], 2),
                non_essential=round(data["non_essential"], 2),
            )
            for d, data in sorted(spending_by_period.items())
        ]

        # Calculate totals and averages
        total = sum(p.total for p in data_points)
        weeks = max(1, (end_date - start_date).days / 7)
        avg_per_week = total / weeks

        # Determine trend
        if len(data_points) >= 2:
            first_half = sum(p.total for p in data_points[: len(data_points) // 2])
            second_half = sum(p.total for p in data_points[len(data_points) // 2 :])
            if second_half > first_half * 1.1:
                trend = "up"
            elif second_half < first_half * 0.9:
                trend = "down"
            else:
                trend = "stable"
        else:
            trend = "stable"

        return GroceryAnalyticsSpending(
            period_start=start_date,
            period_end=end_date,
            total=round(total, 2),
            data_points=data_points,
            trend=trend,
            average_per_week=round(avg_per_week, 2),
        )

    async def get_by_category(
        self,
        user: User,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> GroceryAnalyticsByCategory:
        """Get spending analytics grouped by category"""
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        query = select(GroceryPurchase).where(
            GroceryPurchase.purchase_date >= start_date,
            GroceryPurchase.purchase_date <= end_date,
            build_ownership_filter(
                GroceryPurchase,
                GroceryPurchase.user_id,
                GroceryPurchase.ownership_type,
                user.id,
                household_user_ids,
                member,
            ),
        )

        result = await self.db.execute(query)
        purchases = result.scalars().all()

        # Group by category
        category_data: dict[str, dict] = defaultdict(lambda: {"total": 0, "count": 0, "prices": []})

        for purchase in purchases:
            cat = purchase.category
            amount = float(purchase.total_price)
            price = float(purchase.unit_price)

            category_data[cat]["total"] += amount
            category_data[cat]["count"] += 1
            category_data[cat]["prices"].append(price)

        total = sum(d["total"] for d in category_data.values())

        categories = [
            CategoryBreakdown(
                category=cat,
                category_display=GROCERY_CATEGORY_DISPLAY.get(cat, cat),
                total=round(data["total"], 2),
                percentage=round(data["total"] / total * 100, 1) if total > 0 else 0,
                item_count=data["count"],
                average_price=round(sum(data["prices"]) / len(data["prices"]), 2)
                if data["prices"]
                else 0,
            )
            for cat, data in category_data.items()
        ]

        # Sort by total descending
        categories.sort(key=lambda x: -x.total)

        return GroceryAnalyticsByCategory(
            period_start=start_date,
            period_end=end_date,
            total=round(total, 2),
            categories=categories,
        )

    async def get_by_necessity(
        self,
        user: User,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> GroceryAnalyticsByNecessity:
        """Get spending analytics grouped by necessity type"""
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        query = select(GroceryPurchase).where(
            GroceryPurchase.purchase_date >= start_date,
            GroceryPurchase.purchase_date <= end_date,
            build_ownership_filter(
                GroceryPurchase,
                GroceryPurchase.user_id,
                GroceryPurchase.ownership_type,
                user.id,
                household_user_ids,
                member,
            ),
        )

        result = await self.db.execute(query)
        purchases = result.scalars().all()

        essential_total = 0
        essential_count = 0
        non_essential_total = 0
        non_essential_count = 0

        for purchase in purchases:
            amount = float(purchase.total_price)
            if purchase.necessity_type == NecessityType.ESSENTIAL.value:
                essential_total += amount
                essential_count += 1
            else:
                non_essential_total += amount
                non_essential_count += 1

        total = essential_total + non_essential_total

        return GroceryAnalyticsByNecessity(
            period_start=start_date,
            period_end=end_date,
            total=round(total, 2),
            essential=NecessityBreakdown(
                necessity_type=NecessityType.ESSENTIAL.value,
                necessity_type_display=NECESSITY_TYPE_DISPLAY[NecessityType.ESSENTIAL.value],
                total=round(essential_total, 2),
                percentage=round(essential_total / total * 100, 1) if total > 0 else 0,
                item_count=essential_count,
            ),
            non_essential=NecessityBreakdown(
                necessity_type=NecessityType.NON_ESSENTIAL.value,
                necessity_type_display=NECESSITY_TYPE_DISPLAY[NecessityType.NON_ESSENTIAL.value],
                total=round(non_essential_total, 2),
                percentage=round(non_essential_total / total * 100, 1) if total > 0 else 0,
                item_count=non_essential_count,
            ),
        )

    async def get_insights(
        self,
        user: User,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> GroceryInsights:
        """Generate insights about grocery spending"""
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        if not end_date:
            end_date = date.today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        query = select(GroceryPurchase).where(
            GroceryPurchase.purchase_date >= start_date,
            GroceryPurchase.purchase_date <= end_date,
            build_ownership_filter(
                GroceryPurchase,
                GroceryPurchase.user_id,
                GroceryPurchase.ownership_type,
                user.id,
                household_user_ids,
                member,
            ),
        )

        result = await self.db.execute(query)
        purchases = result.scalars().all()

        insights = []

        # Calculate totals
        total = sum(float(p.total_price) for p in purchases)
        non_essential_total = sum(
            float(p.total_price)
            for p in purchases
            if p.necessity_type == NecessityType.NON_ESSENTIAL.value
        )

        # Insight 1: Non-essential spending
        if total > 0:
            non_essential_pct = non_essential_total / total * 100
            if non_essential_pct > 30:
                insights.append(
                    Insight(
                        type="warning",
                        title="Gastos supérfluos elevados",
                        description=f"Você gastou {non_essential_pct:.0f}% do total em itens não essenciais. Considere reduzir.",
                        percentage=round(non_essential_pct, 1),
                    )
                )
            elif non_essential_pct < 15:
                insights.append(
                    Insight(
                        type="success",
                        title="Bom controle de supérfluos",
                        description=f"Apenas {non_essential_pct:.0f}% dos gastos foram em itens não essenciais.",
                        percentage=round(non_essential_pct, 1),
                    )
                )

        # Insight 2: Most expensive items
        expensive_items = sorted(purchases, key=lambda p: float(p.total_price), reverse=True)[:5]

        top_expensive = [
            {
                "name": p.product_name,
                "total": float(p.total_price),
                "category": p.category,
            }
            for p in expensive_items
        ]

        if expensive_items:
            top_item = expensive_items[0]
            insights.append(
                Insight(
                    type="info",
                    title="Item mais caro",
                    description=f"{top_item.product_name} foi seu item mais caro (R$ {float(top_item.total_price):.2f}).",
                    value=float(top_item.total_price),
                )
            )

        # Insight 3: Most frequent items
        item_counts: dict[str, int] = defaultdict(int)
        for p in purchases:
            item_counts[p.product_name.lower()] += 1

        most_frequent = sorted(item_counts.items(), key=lambda x: -x[1])[:5]

        frequent_items = [{"name": name.title(), "count": count} for name, count in most_frequent]

        # Potential savings (assume 10% reduction in non-essential)
        potential_savings = non_essential_total * 0.1

        return GroceryInsights(
            insights=insights,
            potential_savings=round(potential_savings, 2),
            top_expensive_items=top_expensive,
            most_frequent_items=frequent_items,
        )

    async def get_budget_status(self, user: User, month: int, year: int) -> GroceryBudgetStatus:
        """Get budget status for the market category"""
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        # Get market budget for the period
        # Look for budget with category named "Mercado" or similar
        budget_amount = None

        # Get actual spending
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)

        query = select(func.sum(GroceryPurchase.total_price)).where(
            GroceryPurchase.purchase_date >= start_date,
            GroceryPurchase.purchase_date < end_date,
            build_ownership_filter(
                GroceryPurchase,
                GroceryPurchase.user_id,
                GroceryPurchase.ownership_type,
                user.id,
                household_user_ids,
                member,
            ),
        )

        result = await self.db.execute(query)
        spent_amount = float(result.scalar() or 0)

        # Project to end of month
        today = date.today()
        if today.year == year and today.month == month:
            days_passed = today.day
            days_in_month = (end_date - start_date).days
            if days_passed > 0:
                projected_total = spent_amount * days_in_month / days_passed
            else:
                projected_total = spent_amount
        else:
            projected_total = spent_amount

        remaining = None
        percentage_used = None
        on_track = True

        if budget_amount:
            remaining = budget_amount - spent_amount
            percentage_used = spent_amount / budget_amount * 100
            on_track = projected_total <= budget_amount

        return GroceryBudgetStatus(
            budget_amount=budget_amount,
            spent_amount=round(spent_amount, 2),
            remaining=round(remaining, 2) if remaining is not None else None,
            percentage_used=round(percentage_used, 1) if percentage_used is not None else None,
            projected_total=round(projected_total, 2),
            on_track=on_track,
        )

    def _get_period_date(self, d: date, granularity: str) -> date:
        """Get the period start date for a given date"""
        if granularity == "day":
            return d
        elif granularity == "week":
            # Start of week (Monday)
            return d - timedelta(days=d.weekday())
        elif granularity == "month":
            return date(d.year, d.month, 1)
        return d
