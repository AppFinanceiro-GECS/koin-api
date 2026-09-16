"""
Grocery Service - CRUD operations for products and purchases
"""

import unicodedata
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.grocery import (
    GROCERY_CATEGORY_DISPLAY,
    NECESSITY_TYPE_DISPLAY,
    GroceryCategory,
    GroceryPriceHistory,
    GroceryProduct,
    GroceryPurchase,
    NecessityType,
)
from app.models.merchant import Merchant
from app.models.transaction import Transaction
from app.models.user import User
from app.modules.grocery.schemas.product import (
    GroceryProductCreate,
    GroceryProductResponse,
    GroceryProductUpdate,
)
from app.modules.grocery.schemas.purchase import (
    BackfillRequest,
    BackfillResponse,
    BackfillTransactionDetail,
    CategorySummary,
    GroceryPurchaseBulkCreate,
    GroceryPurchaseComparison,
    GroceryPurchaseCreate,
    GroceryPurchaseResponse,
    GroceryPurchaseSummary,
    GroceryPurchaseUpdate,
    MonthData,
    NecessitySummary,
)
from app.modules.household.utils import (
    build_ownership_filter,
    get_household_member,
    get_household_user_ids,
)


def normalize_text(text: str) -> str:
    """Normalize text for matching (lowercase, remove accents)"""
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text


class GroceryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== PRODUCTS ====================

    async def list_products(
        self,
        user: User,
        search: str | None = None,
        category: GroceryCategory | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GroceryProductResponse]:
        """List products (user's + system products)"""
        query = select(GroceryProduct).where(
            or_(GroceryProduct.user_id == user.id, GroceryProduct.is_system == True)
        )

        if search:
            normalized_search = normalize_text(search)
            query = query.where(GroceryProduct.normalized_name.ilike(f"%{normalized_search}%"))

        if category:
            query = query.where(GroceryProduct.category == category.value)

        query = query.order_by(GroceryProduct.name).offset(offset).limit(limit)
        result = await self.db.execute(query)
        products = result.scalars().all()

        return [self._build_product_response(p) for p in products]

    async def get_product(self, user: User, product_id: int) -> GroceryProductResponse | None:
        """Get a single product"""
        result = await self.db.execute(
            select(GroceryProduct).where(
                GroceryProduct.id == product_id,
                or_(GroceryProduct.user_id == user.id, GroceryProduct.is_system == True),
            )
        )
        product = result.scalar_one_or_none()
        if not product:
            return None
        return self._build_product_response(product)

    async def create_product(self, user: User, data: GroceryProductCreate) -> GroceryProduct:
        """Create a new product"""
        product = GroceryProduct(
            user_id=user.id,
            name=data.name,
            normalized_name=normalize_text(data.name),
            category=data.category.value,
            necessity_type=data.necessity_type.value,
            default_unit=data.default_unit,
            is_system=False,
        )
        self.db.add(product)
        await self.db.flush()
        await self.db.refresh(product)
        return product

    async def update_product(
        self, user: User, product_id: int, data: GroceryProductUpdate
    ) -> GroceryProduct:
        """Update a product"""
        result = await self.db.execute(
            select(GroceryProduct).where(
                GroceryProduct.id == product_id,
                GroceryProduct.user_id == user.id,  # Can only update own products
                GroceryProduct.is_system == False,
            )
        )
        product = result.scalar_one_or_none()

        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Produto não encontrado ou não pode ser editado",
            )

        for field, value in data.model_dump(exclude_unset=True).items():
            if field == "name" and value:
                setattr(product, "normalized_name", normalize_text(value))
            if field in ("category", "necessity_type") and value:
                value = value.value
            setattr(product, field, value)

        await self.db.flush()
        await self.db.refresh(product)
        return product

    async def delete_product(self, user: User, product_id: int) -> None:
        """Delete a product"""
        result = await self.db.execute(
            select(GroceryProduct).where(
                GroceryProduct.id == product_id,
                GroceryProduct.user_id == user.id,
                GroceryProduct.is_system == False,
            )
        )
        product = result.scalar_one_or_none()

        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Produto não encontrado ou não pode ser excluído",
            )

        await self.db.delete(product)

    async def find_or_create_product(
        self,
        user: User,
        name: str,
        category: GroceryCategory = GroceryCategory.OTHER,
        necessity_type: NecessityType = NecessityType.ESSENTIAL,
        unit: str = "un",
    ) -> GroceryProduct:
        """Find existing product by name or create new one"""
        normalized = normalize_text(name)

        # Check for existing product
        result = await self.db.execute(
            select(GroceryProduct).where(
                or_(
                    and_(
                        GroceryProduct.user_id == user.id,
                        GroceryProduct.normalized_name == normalized,
                    ),
                    and_(
                        GroceryProduct.is_system == True,
                        GroceryProduct.normalized_name == normalized,
                    ),
                )
            )
        )
        product = result.scalar_one_or_none()

        if product:
            return product

        # Create new product
        product = GroceryProduct(
            user_id=user.id,
            name=name,
            normalized_name=normalized,
            category=category.value,
            necessity_type=necessity_type.value,
            default_unit=unit,
            is_system=False,
        )
        self.db.add(product)
        await self.db.flush()
        await self.db.refresh(product)
        return product

    def _build_product_response(self, product: GroceryProduct) -> GroceryProductResponse:
        """Build product response"""
        return GroceryProductResponse(
            id=product.id,
            user_id=product.user_id,
            name=product.name,
            normalized_name=product.normalized_name,
            category=GroceryCategory(product.category),
            necessity_type=NecessityType(product.necessity_type),
            default_unit=product.default_unit,
            is_system=product.is_system,
            created_at=product.created_at,
            category_display=GROCERY_CATEGORY_DISPLAY.get(product.category),
            necessity_type_display=NECESSITY_TYPE_DISPLAY.get(product.necessity_type),
        )

    # ==================== PURCHASES ====================

    async def list_purchases(
        self,
        user: User,
        start_date: date | None = None,
        end_date: date | None = None,
        category: GroceryCategory | None = None,
        necessity_type: NecessityType | None = None,
        merchant_id: int | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GroceryPurchaseResponse]:
        """List purchases with filters"""
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        query = select(GroceryPurchase).where(
            build_ownership_filter(
                GroceryPurchase,
                GroceryPurchase.user_id,
                GroceryPurchase.ownership_type,
                user.id,
                household_user_ids,
                member,
            )
        )

        if start_date:
            query = query.where(GroceryPurchase.purchase_date >= start_date)
        if end_date:
            query = query.where(GroceryPurchase.purchase_date <= end_date)
        if category:
            query = query.where(GroceryPurchase.category == category.value)
        if necessity_type:
            query = query.where(GroceryPurchase.necessity_type == necessity_type.value)
        if merchant_id:
            query = query.where(GroceryPurchase.merchant_id == merchant_id)
        if search:
            query = query.where(GroceryPurchase.product_name.ilike(f"%{search}%"))

        query = (
            query.order_by(GroceryPurchase.purchase_date.desc(), GroceryPurchase.id.desc())
            .offset(offset)
            .limit(limit)
        )

        # Load merchant relationship
        query = query.options(selectinload(GroceryPurchase.merchant))

        result = await self.db.execute(query)
        purchases = result.scalars().all()

        return [self._build_purchase_response(p) for p in purchases]

    async def get_purchase(self, user: User, purchase_id: int) -> GroceryPurchaseResponse | None:
        """Get a single purchase"""
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        query = (
            select(GroceryPurchase)
            .where(
                GroceryPurchase.id == purchase_id,
                build_ownership_filter(
                    GroceryPurchase,
                    GroceryPurchase.user_id,
                    GroceryPurchase.ownership_type,
                    user.id,
                    household_user_ids,
                    member,
                ),
            )
            .options(selectinload(GroceryPurchase.merchant))
        )

        result = await self.db.execute(query)
        purchase = result.scalar_one_or_none()

        if not purchase:
            return None
        return self._build_purchase_response(purchase)

    async def create_purchase(self, user: User, data: GroceryPurchaseCreate) -> GroceryPurchase:
        """Create a single purchase"""
        # Get or create merchant if name provided
        merchant_id = data.merchant_id
        if data.merchant_name and not merchant_id:
            merchant = await self._get_or_create_merchant(data.merchant_name)
            merchant_id = merchant.id

        # Find or create product
        product = await self.find_or_create_product(
            user,
            data.product_name,
            data.category,
            data.necessity_type,
            data.unit,
        )

        purchase = GroceryPurchase(
            user_id=user.id,
            transaction_id=data.transaction_id,
            document_id=data.document_id,
            product_id=product.id,
            merchant_id=merchant_id,
            product_name=data.product_name,
            quantity=data.quantity,
            unit=data.unit,
            unit_price=data.unit_price,
            total_price=data.total_price,
            category=data.category.value,
            necessity_type=data.necessity_type.value,
            purchase_date=data.purchase_date,
            ownership_type=data.ownership_type.value,
        )

        self.db.add(purchase)
        await self.db.flush()

        # Update price history
        await self._update_price_history(
            product.id, merchant_id, data.unit_price, data.unit, data.purchase_date
        )

        await self.db.refresh(purchase)
        return purchase

    async def create_purchases_bulk(
        self, user: User, data: GroceryPurchaseBulkCreate
    ) -> list[GroceryPurchase]:
        """Create multiple purchases at once (from a single receipt)"""
        # Get or create merchant if name provided
        merchant_id = data.merchant_id
        if data.merchant_name and not merchant_id:
            merchant = await self._get_or_create_merchant(data.merchant_name)
            merchant_id = merchant.id

        purchases = []
        for item in data.items:
            # Find or create product
            product = await self.find_or_create_product(
                user,
                item.product_name,
                item.category,
                item.necessity_type,
                item.unit,
            )

            purchase = GroceryPurchase(
                user_id=user.id,
                transaction_id=data.transaction_id,
                document_id=data.document_id,
                product_id=product.id,
                merchant_id=merchant_id,
                product_name=item.product_name,
                quantity=item.quantity,
                unit=item.unit,
                unit_price=item.unit_price,
                total_price=item.total_price,
                category=item.category.value,
                necessity_type=item.necessity_type.value,
                purchase_date=data.purchase_date,
                ownership_type=data.ownership_type.value,
            )
            self.db.add(purchase)
            purchases.append(purchase)

            # Update price history
            await self._update_price_history(
                product.id, merchant_id, item.unit_price, item.unit, data.purchase_date
            )

        await self.db.flush()
        for p in purchases:
            await self.db.refresh(p)

        return purchases

    async def update_purchase(
        self, user: User, purchase_id: int, data: GroceryPurchaseUpdate
    ) -> GroceryPurchase:
        """Update a purchase"""
        result = await self.db.execute(
            select(GroceryPurchase).where(
                GroceryPurchase.id == purchase_id,
                GroceryPurchase.user_id == user.id,
            )
        )
        purchase = result.scalar_one_or_none()

        if not purchase:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Compra não encontrada"
            )

        for field, value in data.model_dump(exclude_unset=True).items():
            if field in ("category", "necessity_type") and value:
                value = value.value
            setattr(purchase, field, value)

        await self.db.flush()
        await self.db.refresh(purchase)
        return purchase

    async def delete_purchase(self, user: User, purchase_id: int) -> None:
        """Delete a purchase"""
        result = await self.db.execute(
            select(GroceryPurchase).where(
                GroceryPurchase.id == purchase_id,
                GroceryPurchase.user_id == user.id,
            )
        )
        purchase = result.scalar_one_or_none()

        if not purchase:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Compra não encontrada"
            )

        await self.db.delete(purchase)

    async def get_purchase_summary(
        self, user: User, month: int, year: int
    ) -> GroceryPurchaseSummary:
        """Get monthly summary of purchases"""
        household_user_ids = await get_household_user_ids(self.db, user)
        member = await get_household_member(self.db, user)

        # Get all purchases for the month
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)

        query = select(GroceryPurchase).where(
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
        purchases = result.scalars().all()

        # Calculate totals
        total = sum(float(p.total_price) for p in purchases)
        essential_total = sum(
            float(p.total_price)
            for p in purchases
            if p.necessity_type == NecessityType.ESSENTIAL.value
        )
        non_essential_total = sum(
            float(p.total_price)
            for p in purchases
            if p.necessity_type == NecessityType.NON_ESSENTIAL.value
        )

        # Group by category
        category_totals: dict[str, float] = {}
        category_counts: dict[str, int] = {}
        for p in purchases:
            cat = p.category
            category_totals[cat] = category_totals.get(cat, 0) + float(p.total_price)
            category_counts[cat] = category_counts.get(cat, 0) + 1

        by_category = [
            CategorySummary(
                category=cat,
                category_display=GROCERY_CATEGORY_DISPLAY.get(cat, cat),
                total=amount,
                count=category_counts[cat],
                percentage=(amount / total * 100) if total > 0 else 0,
            )
            for cat, amount in sorted(category_totals.items(), key=lambda x: -x[1])
        ]

        # Group by necessity
        by_necessity = [
            NecessitySummary(
                necessity_type=NecessityType.ESSENTIAL.value,
                necessity_type_display=NECESSITY_TYPE_DISPLAY[NecessityType.ESSENTIAL.value],
                total=essential_total,
                count=sum(
                    1 for p in purchases if p.necessity_type == NecessityType.ESSENTIAL.value
                ),
                percentage=(essential_total / total * 100) if total > 0 else 0,
            ),
            NecessitySummary(
                necessity_type=NecessityType.NON_ESSENTIAL.value,
                necessity_type_display=NECESSITY_TYPE_DISPLAY[NecessityType.NON_ESSENTIAL.value],
                total=non_essential_total,
                count=sum(
                    1 for p in purchases if p.necessity_type == NecessityType.NON_ESSENTIAL.value
                ),
                percentage=(non_essential_total / total * 100) if total > 0 else 0,
            ),
        ]

        return GroceryPurchaseSummary(
            month=month,
            year=year,
            total=total,
            essential_total=essential_total,
            non_essential_total=non_essential_total,
            item_count=len(purchases),
            by_category=by_category,
            by_necessity=by_necessity,
        )

    async def get_purchase_comparison(
        self, user: User, month: int, year: int
    ) -> GroceryPurchaseComparison:
        """Compare purchases between current and previous month"""
        # Get current month summary
        current = await self.get_purchase_summary(user, month, year)

        # Get previous month
        if month == 1:
            prev_month, prev_year = 12, year - 1
        else:
            prev_month, prev_year = month - 1, year

        previous = await self.get_purchase_summary(user, prev_month, prev_year)

        # Build comparison
        total_diff = current.total - previous.total
        total_diff_pct = (total_diff / previous.total * 100) if previous.total > 0 else 0

        comparison = {
            "total_diff": total_diff,
            "total_diff_percent": round(total_diff_pct, 1),
            "essential_diff": current.essential_total - previous.essential_total,
            "non_essential_diff": current.non_essential_total - previous.non_essential_total,
        }

        return GroceryPurchaseComparison(
            current_month=MonthData(
                total=current.total,
                essential=current.essential_total,
                non_essential=current.non_essential_total,
                item_count=current.item_count,
                by_category={c.category: c.total for c in current.by_category},
            ),
            previous_month=MonthData(
                total=previous.total,
                essential=previous.essential_total,
                non_essential=previous.non_essential_total,
                item_count=previous.item_count,
                by_category={c.category: c.total for c in previous.by_category},
            ),
            comparison=comparison,
        )

    def _build_purchase_response(self, purchase: GroceryPurchase) -> GroceryPurchaseResponse:
        """Build purchase response"""
        return GroceryPurchaseResponse(
            id=purchase.id,
            user_id=purchase.user_id,
            transaction_id=purchase.transaction_id,
            document_id=purchase.document_id,
            product_id=purchase.product_id,
            merchant_id=purchase.merchant_id,
            product_name=purchase.product_name,
            quantity=float(purchase.quantity),
            unit=purchase.unit,
            unit_price=float(purchase.unit_price),
            total_price=float(purchase.total_price),
            category=GroceryCategory(purchase.category),
            necessity_type=NecessityType(purchase.necessity_type),
            purchase_date=purchase.purchase_date,
            ownership_type=purchase.ownership_type,
            created_at=purchase.created_at,
            category_display=GROCERY_CATEGORY_DISPLAY.get(purchase.category),
            necessity_type_display=NECESSITY_TYPE_DISPLAY.get(purchase.necessity_type),
            merchant_name=purchase.merchant.name if purchase.merchant else None,
        )

    async def _get_or_create_merchant(self, name: str) -> Merchant:
        """Get or create merchant by name"""
        normalized = normalize_text(name)
        result = await self.db.execute(
            select(Merchant).where(Merchant.normalized_name == normalized)
        )
        merchant = result.scalar_one_or_none()

        if merchant:
            return merchant

        merchant = Merchant(
            name=name,
            normalized_name=normalized,
        )
        self.db.add(merchant)
        await self.db.flush()
        await self.db.refresh(merchant)
        return merchant

    async def _update_price_history(
        self,
        product_id: int,
        merchant_id: int | None,
        price: float,
        unit: str,
        recorded_at: date,
    ) -> None:
        """Update price history for a product"""
        # Check if we already have a record for this product/merchant/date
        query = select(GroceryPriceHistory).where(
            GroceryPriceHistory.product_id == product_id,
            GroceryPriceHistory.recorded_at == recorded_at,
        )
        if merchant_id:
            query = query.where(GroceryPriceHistory.merchant_id == merchant_id)

        result = await self.db.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing record
            existing.price = price
            existing.unit = unit
        else:
            # Create new record
            history = GroceryPriceHistory(
                product_id=product_id,
                merchant_id=merchant_id,
                price=price,
                unit=unit,
                recorded_at=recorded_at,
            )
            self.db.add(history)

    # ==================== HELPER FOR TRANSACTION SERVICE ====================

    async def create_purchase_from_transaction(
        self,
        user: User,
        transaction_id: int,
        document_id: int | None,
        merchant_id: int | None,
        product_name: str,
        total_price: float,
        purchase_date: date,
        quantity: float | None = None,
        unit: str | None = None,
        unit_price: float | None = None,
        grocery_category: str | None = None,
        necessity_type: str | None = None,
        ownership_type: str = "personal",
    ) -> GroceryPurchase | None:
        """
        Create a GroceryPurchase from transaction confirmation data.
        This is called by the transaction service when a cupom fiscal item is confirmed.
        Returns None if not enough data to create purchase.
        """
        # Need at least grocery_category to be a cupom fiscal item
        if not grocery_category:
            return None

        # Default values
        qty = Decimal(str(quantity)) if quantity else Decimal("1")
        unit_val = unit or "un"
        u_price = Decimal(str(unit_price)) if unit_price else Decimal(str(total_price))

        # Parse category
        try:
            cat = GroceryCategory(grocery_category)
        except ValueError:
            cat = GroceryCategory.OTHER

        # Parse necessity type
        try:
            nec_type = NecessityType(necessity_type) if necessity_type else NecessityType.ESSENTIAL
        except ValueError:
            nec_type = NecessityType.ESSENTIAL

        # Find or create product
        product = await self.find_or_create_product(
            user,
            product_name,
            cat,
            nec_type,
            unit_val,
        )

        # Create purchase
        purchase = GroceryPurchase(
            user_id=user.id,
            transaction_id=transaction_id,
            document_id=document_id,
            product_id=product.id,
            merchant_id=merchant_id,
            product_name=product_name,
            quantity=qty,
            unit=unit_val,
            unit_price=u_price,
            total_price=Decimal(str(total_price)),
            category=cat.value,
            necessity_type=nec_type.value,
            purchase_date=purchase_date,
            ownership_type=ownership_type,
        )

        self.db.add(purchase)
        await self.db.flush()

        # Update price history
        await self._update_price_history(
            product.id, merchant_id, float(u_price), unit_val, purchase_date
        )

        await self.db.refresh(purchase)
        return purchase

    # ==================== BACKFILL ====================

    # Default category names that indicate grocery purchases
    MARKET_CATEGORY_NAMES = [
        "supermercado",
        "alimentação",
        "alimentacao",
        "mercado",
        "grocery",
    ]

    async def backfill_grocery_purchases(
        self,
        user: User,
        request: BackfillRequest,
    ) -> BackfillResponse:
        """
        Backfill grocery purchases from existing transactions.
        Creates GroceryPurchase records for transactions in market-related categories
        that don't already have associated grocery purchases.
        """
        household_user_ids = await get_household_user_ids(self.db, user)

        # Determine which category names to use
        category_names = request.category_names or self.MARKET_CATEGORY_NAMES
        category_names_lower = [name.lower() for name in category_names]

        # Find category IDs matching the names
        category_query = select(Category).where(func.lower(Category.name).in_(category_names_lower))
        category_result = await self.db.execute(category_query)
        categories = category_result.scalars().all()

        if not categories:
            return BackfillResponse(
                transactions_found=0,
                already_have_purchases=0,
                to_create=0,
                created=0,
                details=[],
            )

        category_ids = [c.id for c in categories]

        # Find transaction IDs that already have grocery purchases
        existing_query = select(GroceryPurchase.transaction_id).where(
            GroceryPurchase.transaction_id.isnot(None),
            GroceryPurchase.user_id.in_(household_user_ids),
        )
        existing_result = await self.db.execute(existing_query)
        existing_transaction_ids = set(row[0] for row in existing_result.all())

        # Find transactions in market categories without grocery purchases
        transactions_query = (
            select(Transaction)
            .options(selectinload(Transaction.merchant))
            .where(
                Transaction.category_id.in_(category_ids),
                Transaction.type == "expense",
                Transaction.user_id.in_(household_user_ids),
            )
            .order_by(Transaction.date.desc())
        )
        transactions_result = await self.db.execute(transactions_query)
        all_transactions = transactions_result.scalars().all()

        # Separate transactions
        to_backfill = [t for t in all_transactions if t.id not in existing_transaction_ids]
        already_have = [t for t in all_transactions if t.id in existing_transaction_ids]

        details: list[BackfillTransactionDetail] = []
        created_count = 0

        for tx in to_backfill:
            product_name = tx.description or tx.merchant_name or "Compra de mercado"
            merchant_id = tx.merchant_id

            if request.dry_run:
                detail_status = "would_create"
            else:
                # Create GroceryPurchase
                purchase = GroceryPurchase(
                    user_id=tx.user_id,
                    transaction_id=tx.id,
                    document_id=None,
                    product_id=None,
                    merchant_id=merchant_id,
                    product_name=product_name,
                    quantity=1,
                    unit="un",
                    unit_price=float(tx.amount),
                    total_price=float(tx.amount),
                    category=GroceryCategory.OTHER.value,
                    necessity_type=NecessityType.ESSENTIAL.value,
                    purchase_date=tx.date,
                    ownership_type=tx.ownership_type or "personal",
                )
                self.db.add(purchase)
                created_count += 1
                detail_status = "created"

            details.append(
                BackfillTransactionDetail(
                    transaction_id=tx.id,
                    description=tx.description,
                    amount=float(tx.amount),
                    date=tx.date.isoformat(),
                    status=detail_status,
                )
            )

        # Add skipped transactions
        for tx in already_have:
            details.append(
                BackfillTransactionDetail(
                    transaction_id=tx.id,
                    description=tx.description,
                    amount=float(tx.amount),
                    date=tx.date.isoformat(),
                    status="skipped",
                )
            )

        if not request.dry_run and created_count > 0:
            await self.db.commit()

        return BackfillResponse(
            transactions_found=len(all_transactions),
            already_have_purchases=len(already_have),
            to_create=len(to_backfill),
            created=created_count,
            details=details,
        )
