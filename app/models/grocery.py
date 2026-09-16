from datetime import date, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.utils import utc_now

from ..core.database import Base


class GroceryCategory(str, Enum):
    """Categorias de produtos de mercado"""

    # Alimentos
    FRUITS_VEGETABLES = "fruits_vegetables"  # Frutas e Verduras
    MEAT_FISH = "meat_fish"  # Carnes e Peixes
    DAIRY = "dairy"  # Laticínios
    BAKERY = "bakery"  # Padaria
    BEVERAGES = "beverages"  # Bebidas
    SNACKS = "snacks"  # Lanches/Salgadinhos
    FROZEN = "frozen"  # Congelados
    CANNED = "canned"  # Enlatados
    GRAINS_PASTA = "grains_pasta"  # Grãos e Massas
    GRAINS = "grains"  # Grãos (arroz, feijão)
    CONDIMENTS = "condiments"  # Temperos

    # Não-Alimentos
    CLEANING = "cleaning"  # Limpeza
    HYGIENE = "hygiene"  # Higiene Pessoal
    PERSONAL_CARE = "personal_care"  # Cuidados Pessoais
    BABY = "baby"  # Bebê
    PET = "pet"  # Pet
    HOUSEHOLD = "household"  # Utilidades
    OTHER = "other"  # Outros


class NecessityType(str, Enum):
    """Tipo de necessidade do produto"""

    ESSENTIAL = "essential"  # Necessidades básicas
    NON_ESSENTIAL = "non_essential"  # Supérfluos (doces, refrigerantes, etc.)


class ShoppingListStatus(str, Enum):
    """Status da lista de compras"""

    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ShoppingListSource(str, Enum):
    """Origem da lista de compras"""

    MANUAL = "manual"
    AI_GENERATED = "ai_generated"
    HISTORY = "history"


# Display names for categories (Portuguese)
GROCERY_CATEGORY_DISPLAY = {
    GroceryCategory.FRUITS_VEGETABLES.value: "Frutas e Verduras",
    GroceryCategory.MEAT_FISH.value: "Carnes e Peixes",
    GroceryCategory.DAIRY.value: "Laticínios",
    GroceryCategory.BAKERY.value: "Padaria",
    GroceryCategory.BEVERAGES.value: "Bebidas",
    GroceryCategory.SNACKS.value: "Lanches",
    GroceryCategory.FROZEN.value: "Congelados",
    GroceryCategory.CANNED.value: "Enlatados",
    GroceryCategory.GRAINS_PASTA.value: "Grãos e Massas",
    GroceryCategory.GRAINS.value: "Grãos",
    GroceryCategory.CONDIMENTS.value: "Temperos",
    GroceryCategory.CLEANING.value: "Limpeza",
    GroceryCategory.HYGIENE.value: "Higiene",
    GroceryCategory.PERSONAL_CARE.value: "Cuidados Pessoais",
    GroceryCategory.BABY.value: "Bebê",
    GroceryCategory.PET.value: "Pet",
    GroceryCategory.HOUSEHOLD.value: "Utilidades",
    GroceryCategory.OTHER.value: "Outros",
}

NECESSITY_TYPE_DISPLAY = {
    NecessityType.ESSENTIAL.value: "Essencial",
    NecessityType.NON_ESSENTIAL.value: "Supérfluo",
}


class GroceryProduct(Base):
    """Catálogo de produtos de mercado"""

    __tablename__ = "grocery_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200), index=True)  # lowercase, sem acentos
    category: Mapped[str] = mapped_column(String(30), default=GroceryCategory.OTHER.value)
    necessity_type: Mapped[str] = mapped_column(String(20), default=NecessityType.ESSENTIAL.value)
    default_unit: Mapped[str] = mapped_column(String(10), default="un")  # kg, un, L, etc.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # Produto padrão do sistema
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    user: Mapped["User | None"] = relationship(lazy="noload")
    purchases: Mapped[list["GroceryPurchase"]] = relationship(
        back_populates="product", lazy="noload"
    )
    price_history: Mapped[list["GroceryPriceHistory"]] = relationship(
        back_populates="product", lazy="noload"
    )
    shopping_list_items: Mapped[list["ShoppingListItem"]] = relationship(
        back_populates="product", lazy="noload"
    )

    @property
    def category_display(self) -> str:
        return GROCERY_CATEGORY_DISPLAY.get(self.category, self.category)

    @property
    def necessity_type_display(self) -> str:
        return NECESSITY_TYPE_DISPLAY.get(self.necessity_type, self.necessity_type)


class GroceryPurchase(Base):
    """Itens comprados (vinculados às transações)"""

    __tablename__ = "grocery_purchases"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), index=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    receipt_id: Mapped[int | None] = mapped_column(
        ForeignKey("receipts.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("grocery_products.id", ondelete="SET NULL"), index=True
    )
    merchant_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchants.id", ondelete="SET NULL"), index=True
    )

    # Item details
    product_name: Mapped[str] = mapped_column(String(200))  # Nome original do cupom
    quantity: Mapped[float] = mapped_column(Numeric(10, 3), default=1)
    unit: Mapped[str] = mapped_column(String(10), default="un")
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2))
    total_price: Mapped[float] = mapped_column(Numeric(10, 2))

    # Classification
    category: Mapped[str] = mapped_column(String(30), default=GroceryCategory.OTHER.value)
    necessity_type: Mapped[str] = mapped_column(String(20), default=NecessityType.ESSENTIAL.value)

    # Metadata
    purchase_date: Mapped[date] = mapped_column(Date, index=True)
    ownership_type: Mapped[str] = mapped_column(
        String(20), default="personal"
    )  # personal/household
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    user: Mapped["User"] = relationship(lazy="noload")
    transaction: Mapped["Transaction | None"] = relationship(lazy="noload")
    document: Mapped["Document | None"] = relationship(lazy="noload")
    receipt: Mapped["Receipt | None"] = relationship(
        back_populates="grocery_purchase", lazy="noload"
    )
    product: Mapped["GroceryProduct | None"] = relationship(
        back_populates="purchases", lazy="noload"
    )
    merchant: Mapped["Merchant | None"] = relationship(lazy="noload")

    @property
    def category_display(self) -> str:
        return GROCERY_CATEGORY_DISPLAY.get(self.category, self.category)

    @property
    def necessity_type_display(self) -> str:
        return NECESSITY_TYPE_DISPLAY.get(self.necessity_type, self.necessity_type)

    @property
    def merchant_name(self) -> str | None:
        return self.merchant.name if self.merchant else None


class GroceryPriceHistory(Base):
    """Histórico de preços dos produtos"""

    __tablename__ = "grocery_price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("grocery_products.id", ondelete="CASCADE"), index=True
    )
    merchant_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchants.id", ondelete="SET NULL"), index=True
    )
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    unit: Mapped[str] = mapped_column(String(10), default="un")
    recorded_at: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    product: Mapped["GroceryProduct"] = relationship(back_populates="price_history", lazy="noload")
    merchant: Mapped["Merchant | None"] = relationship(lazy="noload")

    @property
    def merchant_name(self) -> str | None:
        return self.merchant.name if self.merchant else None


class ShoppingList(Base):
    """Listas de compras (compartilhadas no household)"""

    __tablename__ = "shopping_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    license_id: Mapped[int | None] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"), index=True
    )  # Compartilhada com household via license
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default=ShoppingListStatus.DRAFT.value)
    source: Mapped[str] = mapped_column(String(20), default=ShoppingListSource.MANUAL.value)
    ownership_type: Mapped[str] = mapped_column(String(20), default="household")  # sempre household
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationships
    user: Mapped["User"] = relationship(lazy="noload")
    license: Mapped["License | None"] = relationship(lazy="noload")
    items: Mapped[list["ShoppingListItem"]] = relationship(
        back_populates="shopping_list", lazy="noload", cascade="all, delete-orphan"
    )

    @property
    def total_items(self) -> int:
        return len(self.items) if self.items else 0

    @property
    def checked_items(self) -> int:
        if not self.items:
            return 0
        return sum(1 for item in self.items if item.is_checked)

    @property
    def progress_percent(self) -> float:
        if not self.items:
            return 0
        return (self.checked_items / self.total_items) * 100

    @property
    def estimated_total(self) -> float:
        if not self.items:
            return 0
        return sum(
            float(item.estimated_price or 0) * float(item.quantity or 1) for item in self.items
        )

    @property
    def creator_name(self) -> str | None:
        return self.user.name if self.user else None


class ShoppingListItem(Base):
    """Itens da lista de compras"""

    __tablename__ = "shopping_list_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(
        ForeignKey("shopping_lists.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("grocery_products.id", ondelete="SET NULL"), index=True
    )
    product_name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[float] = mapped_column(Numeric(10, 3), default=1)
    unit: Mapped[str] = mapped_column(String(10), default="un")
    estimated_price: Mapped[float | None] = mapped_column(Numeric(10, 2))  # Baseado no histórico
    category: Mapped[str] = mapped_column(String(30), default=GroceryCategory.OTHER.value)
    necessity_type: Mapped[str] = mapped_column(String(20), default=NecessityType.ESSENTIAL.value)
    is_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)  # 0 = normal, higher = more important
    notes: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    # Relationships
    shopping_list: Mapped["ShoppingList"] = relationship(back_populates="items", lazy="noload")
    product: Mapped["GroceryProduct | None"] = relationship(
        back_populates="shopping_list_items", lazy="noload"
    )

    @property
    def category_display(self) -> str:
        return GROCERY_CATEGORY_DISPLAY.get(self.category, self.category)

    @property
    def necessity_type_display(self) -> str:
        return NECESSITY_TYPE_DISPLAY.get(self.necessity_type, self.necessity_type)

    @property
    def estimated_total(self) -> float:
        if not self.estimated_price:
            return 0
        return float(self.estimated_price) * float(self.quantity)


# Import for relationships
from .document import Document
from .license import License
from .merchant import Merchant
from .receipt import Receipt
from .transaction import Transaction
from .user import User
