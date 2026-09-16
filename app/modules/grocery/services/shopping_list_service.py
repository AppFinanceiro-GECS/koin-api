"""
Shopping List Service - CRUD and AI generation for shopping lists
"""

from collections import defaultdict
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.utils import utc_now
from app.models.grocery import (
    GROCERY_CATEGORY_DISPLAY,
    NECESSITY_TYPE_DISPLAY,
    GroceryCategory,
    GroceryPriceHistory,
    GroceryPurchase,
    NecessityType,
    ShoppingList,
    ShoppingListItem,
    ShoppingListSource,
    ShoppingListStatus,
)
from app.models.user import User
from app.modules.grocery.schemas.shopping_list import (
    ShoppingListCreate,
    ShoppingListGenerateRequest,
    ShoppingListItemCreate,
    ShoppingListItemResponse,
    ShoppingListItemUpdate,
    ShoppingListResponse,
    ShoppingListUpdate,
)
from app.modules.household.utils import (
    get_household_user_ids,
)


class ShoppingListService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_shopping_lists(
        self,
        user: User,
        status_filter: ShoppingListStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ShoppingListResponse]:
        """List shopping lists (user's + household shared lists)"""
        # For shopping lists, we show all lists from the same household
        query = select(ShoppingList)

        if user.license_id:
            # Show lists shared with household
            query = query.where(
                or_(
                    ShoppingList.user_id == user.id,
                    ShoppingList.license_id == user.license_id,
                )
            )
        else:
            # No household, only show user's own lists
            query = query.where(ShoppingList.user_id == user.id)

        if status_filter:
            query = query.where(ShoppingList.status == status_filter.value)

        query = (
            query.options(
                selectinload(ShoppingList.items),
                selectinload(ShoppingList.user),
            )
            .order_by(ShoppingList.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(query)
        lists = result.scalars().all()

        return [self._build_list_response(lst) for lst in lists]

    async def get_shopping_list(self, user: User, list_id: int) -> ShoppingListResponse | None:
        """Get a single shopping list with items"""
        query = select(ShoppingList).where(ShoppingList.id == list_id)

        if user.license_id:
            query = query.where(
                or_(
                    ShoppingList.user_id == user.id,
                    ShoppingList.license_id == user.license_id,
                )
            )
        else:
            query = query.where(ShoppingList.user_id == user.id)

        query = query.options(
            selectinload(ShoppingList.items),
            selectinload(ShoppingList.user),
        )

        result = await self.db.execute(query)
        lst = result.scalar_one_or_none()

        if not lst:
            return None
        return self._build_list_response(lst)

    async def create_shopping_list(self, user: User, data: ShoppingListCreate) -> ShoppingList:
        """Create a new shopping list"""
        shopping_list = ShoppingList(
            user_id=user.id,
            license_id=user.license_id,  # Share with household
            name=data.name,
            notes=data.notes,
            status=ShoppingListStatus.DRAFT.value,
            source=ShoppingListSource.MANUAL.value,
            ownership_type="household",
        )
        self.db.add(shopping_list)
        await self.db.flush()

        # Add items if provided
        if data.items:
            for item_data in data.items:
                item = ShoppingListItem(
                    list_id=shopping_list.id,
                    product_id=item_data.product_id,
                    product_name=item_data.product_name,
                    quantity=item_data.quantity,
                    unit=item_data.unit,
                    estimated_price=item_data.estimated_price,
                    category=item_data.category.value,
                    necessity_type=item_data.necessity_type.value,
                    priority=item_data.priority,
                    notes=item_data.notes,
                )
                self.db.add(item)

        await self.db.flush()
        await self.db.refresh(shopping_list)
        return shopping_list

    async def update_shopping_list(
        self, user: User, list_id: int, data: ShoppingListUpdate
    ) -> ShoppingList:
        """Update a shopping list"""
        result = await self.db.execute(
            select(ShoppingList).where(
                ShoppingList.id == list_id,
                or_(
                    ShoppingList.user_id == user.id,
                    ShoppingList.license_id == user.license_id,
                )
                if user.license_id
                else ShoppingList.user_id == user.id,
            )
        )
        lst = result.scalar_one_or_none()

        if not lst:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Lista não encontrada"
            )

        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "status" and value:
                value = value.value
                # Set completed_at when completing
                if value == ShoppingListStatus.COMPLETED.value:
                    lst.completed_at = utc_now()
            setattr(lst, field, value)

        await self.db.flush()
        await self.db.refresh(lst)
        return lst

    async def delete_shopping_list(self, user: User, list_id: int) -> None:
        """Delete a shopping list"""
        result = await self.db.execute(
            select(ShoppingList).where(
                ShoppingList.id == list_id,
                ShoppingList.user_id == user.id,  # Only creator can delete
            )
        )
        lst = result.scalar_one_or_none()

        if not lst:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lista não encontrada ou você não tem permissão para excluí-la",
            )

        await self.db.delete(lst)

    # ==================== ITEMS ====================

    async def add_item(
        self, user: User, list_id: int, data: ShoppingListItemCreate
    ) -> ShoppingListItem:
        """Add item to shopping list"""
        # Verify access to list
        result = await self.db.execute(
            select(ShoppingList).where(
                ShoppingList.id == list_id,
                or_(
                    ShoppingList.user_id == user.id,
                    ShoppingList.license_id == user.license_id,
                )
                if user.license_id
                else ShoppingList.user_id == user.id,
            )
        )
        lst = result.scalar_one_or_none()

        if not lst:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Lista não encontrada"
            )

        # Get estimated price from history if not provided
        estimated_price = data.estimated_price
        if not estimated_price and data.product_id:
            price = await self._get_latest_price(data.product_id)
            if price:
                estimated_price = price

        item = ShoppingListItem(
            list_id=list_id,
            product_id=data.product_id,
            product_name=data.product_name,
            quantity=data.quantity,
            unit=data.unit,
            estimated_price=estimated_price,
            category=data.category.value,
            necessity_type=data.necessity_type.value,
            priority=data.priority,
            notes=data.notes,
        )
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def update_item(
        self, user: User, list_id: int, item_id: int, data: ShoppingListItemUpdate
    ) -> ShoppingListItem:
        """Update a shopping list item"""
        # Verify access to list
        result = await self.db.execute(
            select(ShoppingListItem)
            .where(
                ShoppingListItem.id == item_id,
                ShoppingListItem.list_id == list_id,
            )
            .options(selectinload(ShoppingListItem.shopping_list))
        )
        item = result.scalar_one_or_none()

        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado")

        # Check access
        lst = item.shopping_list
        if lst.user_id != user.id and lst.license_id != user.license_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para editar esta lista"
            )

        for field, value in data.model_dump(exclude_unset=True).items():
            if field in ("category", "necessity_type") and value:
                value = value.value
            setattr(item, field, value)

        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def delete_item(self, user: User, list_id: int, item_id: int) -> None:
        """Delete an item from shopping list"""
        result = await self.db.execute(
            select(ShoppingListItem)
            .where(
                ShoppingListItem.id == item_id,
                ShoppingListItem.list_id == list_id,
            )
            .options(selectinload(ShoppingListItem.shopping_list))
        )
        item = result.scalar_one_or_none()

        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item não encontrado")

        # Check access
        lst = item.shopping_list
        if lst.user_id != user.id and lst.license_id != user.license_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Sem permissão para editar esta lista"
            )

        await self.db.delete(item)

    # ==================== AI GENERATION ====================

    async def generate_from_history(
        self, user: User, request: ShoppingListGenerateRequest
    ) -> ShoppingList:
        """Generate shopping list based on purchase history with urgency score"""
        household_user_ids = await get_household_user_ids(self.db, user)

        # Get purchases from the specified period (90 days by default)
        start_date = date.today() - timedelta(days=request.period_days)

        query = select(GroceryPurchase).where(GroceryPurchase.purchase_date >= start_date)

        if household_user_ids:
            query = query.where(GroceryPurchase.user_id.in_(household_user_ids))
        else:
            query = query.where(GroceryPurchase.user_id == user.id)

        if not request.include_non_essential:
            query = query.where(GroceryPurchase.necessity_type == NecessityType.ESSENTIAL.value)

        result = await self.db.execute(query)
        purchases = result.scalars().all()

        # Group by product and collect purchase dates for cycle calculation
        product_stats: dict[str, dict] = defaultdict(
            lambda: {
                "purchases": [],  # List of purchases to calculate cycle
                "total_quantity": 0,
                "category": GroceryCategory.OTHER.value,
                "necessity_type": NecessityType.ESSENTIAL.value,
                "unit": "un",
                "product_id": None,
                "last_price": None,
            }
        )

        for purchase in purchases:
            name = purchase.product_name.lower().strip()
            stats = product_stats[name]
            stats["purchases"].append(
                {
                    "date": purchase.purchase_date,
                    "quantity": float(purchase.quantity),
                }
            )
            stats["total_quantity"] += float(purchase.quantity)
            stats["category"] = purchase.category
            stats["necessity_type"] = purchase.necessity_type
            stats["unit"] = purchase.unit
            stats["product_id"] = purchase.product_id
            stats["last_price"] = float(purchase.unit_price)

        # Calculate urgency score for each product
        items_to_add = []
        today = date.today()

        for name, stats in product_stats.items():
            purchase_count = len(stats["purchases"])

            # Filter by minimum frequency
            if purchase_count < request.min_frequency:
                continue

            # Sort purchases by date
            purchase_dates = sorted([p["date"] for p in stats["purchases"]])
            last_purchase_date = purchase_dates[-1]
            days_since_last = (today - last_purchase_date).days

            # Calculate average repurchase cycle
            if purchase_count >= 2:
                intervals = [
                    (purchase_dates[i + 1] - purchase_dates[i]).days
                    for i in range(len(purchase_dates) - 1)
                ]
                avg_cycle = sum(intervals) / len(intervals)
                # Avoid division by zero and very short cycles
                avg_cycle = max(avg_cycle, 3)  # Minimum 3 days to avoid same-day duplicates skewing
            else:
                # If only 1 purchase, use configurable default cycle
                avg_cycle = request.default_cycle_days

            # Calculate urgency score
            urgency_score = days_since_last / avg_cycle

            # Filter by minimum urgency (exclude recent purchases)
            if urgency_score < request.min_urgency:
                continue

            # Calculate average quantity
            avg_quantity = stats["total_quantity"] / purchase_count

            items_to_add.append(
                {
                    "name": name.title(),
                    "quantity": round(avg_quantity, 2),
                    "unit": stats["unit"],
                    "category": stats["category"],
                    "necessity_type": stats["necessity_type"],
                    "product_id": stats["product_id"],
                    "estimated_price": stats["last_price"],
                    "frequency": purchase_count,
                    "urgency_score": urgency_score,
                    "avg_cycle_days": round(avg_cycle, 1),
                    "days_since_last": days_since_last,
                }
            )

        # Sort by: essentials first, then urgency (highest first)
        items_to_add.sort(
            key=lambda x: (
                x["necessity_type"] != NecessityType.ESSENTIAL.value,
                -x["urgency_score"],  # Higher urgency first
            )
        )

        # Create the shopping list
        list_name = request.name or f"Lista Sugerida - {today.strftime('%d/%m/%Y')}"

        shopping_list = ShoppingList(
            user_id=user.id,
            license_id=user.license_id,
            name=list_name,
            status=ShoppingListStatus.DRAFT.value,
            source=ShoppingListSource.AI_GENERATED.value,
            ownership_type="household",
            notes=f"Gerada com base nos últimos {request.period_days} dias. "
            f"Itens ordenados por urgência de recompra. "
            f"Total: {len(items_to_add)} itens.",
        )
        self.db.add(shopping_list)
        await self.db.flush()

        # Add items with priority based on necessity and urgency
        for item_data in items_to_add:
            priority = 2 if item_data["necessity_type"] == NecessityType.ESSENTIAL.value else 0
            # Increase priority for very urgent items
            if item_data["urgency_score"] > 1.5:
                priority += 1

            item = ShoppingListItem(
                list_id=shopping_list.id,
                product_id=item_data["product_id"],
                product_name=item_data["name"],
                quantity=item_data["quantity"],
                unit=item_data["unit"],
                estimated_price=item_data["estimated_price"],
                category=item_data["category"],
                necessity_type=item_data["necessity_type"],
                priority=priority,
                notes=f"Ciclo: ~{item_data['avg_cycle_days']}d | Última compra: {item_data['days_since_last']}d atrás",
            )
            self.db.add(item)

        await self.db.flush()
        await self.db.refresh(shopping_list)
        return shopping_list

    # ==================== HELPERS ====================

    async def _get_latest_price(self, product_id: int) -> float | None:
        """Get the latest price for a product"""
        result = await self.db.execute(
            select(GroceryPriceHistory)
            .where(GroceryPriceHistory.product_id == product_id)
            .order_by(GroceryPriceHistory.recorded_at.desc())
            .limit(1)
        )
        history = result.scalar_one_or_none()
        return float(history.price) if history else None

    def _build_list_response(self, lst: ShoppingList) -> ShoppingListResponse:
        """Build shopping list response"""
        items = [self._build_item_response(item) for item in (lst.items or [])]

        # Sort items: unchecked first, then by priority (high to low)
        items.sort(key=lambda x: (x.is_checked, -x.priority))

        total_items = len(items)
        checked_items = sum(1 for i in items if i.is_checked)
        progress = (checked_items / total_items * 100) if total_items > 0 else 0
        estimated_total = sum((i.estimated_price or 0) * i.quantity for i in items)

        return ShoppingListResponse(
            id=lst.id,
            user_id=lst.user_id,
            license_id=lst.license_id,
            name=lst.name,
            notes=lst.notes,
            status=ShoppingListStatus(lst.status),
            source=ShoppingListSource(lst.source),
            ownership_type=lst.ownership_type,
            created_at=lst.created_at,
            updated_at=lst.updated_at,
            completed_at=lst.completed_at,
            items=items,
            total_items=total_items,
            checked_items=checked_items,
            progress_percent=round(progress, 1),
            estimated_total=round(estimated_total, 2),
            creator_name=lst.user.name if lst.user else None,
        )

    def _build_item_response(self, item: ShoppingListItem) -> ShoppingListItemResponse:
        """Build shopping list item response"""
        estimated_total = None
        if item.estimated_price:
            estimated_total = float(item.estimated_price) * float(item.quantity)

        return ShoppingListItemResponse(
            id=item.id,
            list_id=item.list_id,
            product_id=item.product_id,
            product_name=item.product_name,
            quantity=float(item.quantity),
            unit=item.unit,
            estimated_price=float(item.estimated_price) if item.estimated_price else None,
            category=GroceryCategory(item.category),
            necessity_type=NecessityType(item.necessity_type),
            is_checked=item.is_checked,
            priority=item.priority,
            notes=item.notes,
            created_at=item.created_at,
            category_display=GROCERY_CATEGORY_DISPLAY.get(item.category),
            necessity_type_display=NECESSITY_TYPE_DISPLAY.get(item.necessity_type),
            estimated_total=round(estimated_total, 2) if estimated_total else None,
        )
