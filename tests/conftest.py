import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.deps import get_db
from app.core.security import get_password_hash
from app.main import app
from app.models.account import Account, AccountType
from app.models.category import Category, CategoryType
from app.models.credit_card import CreditCard
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.user import User

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine):
    """Create a new database session for a test."""
    async_session_maker = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(db_session):
    """Create test client with database override."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Usuário básico para testes de serviço."""
    user = User(
        email="test@example.com",
        hashed_password=get_password_hash("TestPass123!"),
        name="Test User",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def bank_account(db_session: AsyncSession, test_user: User) -> Account:
    account = Account(
        user_id=test_user.id,
        name="Conta Corrente",
        type=AccountType.BANK.value,
        balance=5000,
    )
    db_session.add(account)
    await db_session.flush()
    await db_session.refresh(account)
    return account


@pytest_asyncio.fixture
async def credit_card_account(db_session: AsyncSession, test_user: User) -> Account:
    account = Account(
        user_id=test_user.id,
        name="Nubank Roxinho",
        type=AccountType.CREDIT_CARD.value,
        balance=0,
    )
    db_session.add(account)
    await db_session.flush()
    await db_session.refresh(account)
    return account


@pytest_asyncio.fixture
async def credit_card(
    db_session: AsyncSession, test_user: User, credit_card_account: Account
) -> CreditCard:
    """Cartão com fechamento dia 15 e vencimento dia 25."""
    card = CreditCard(
        user_id=test_user.id,
        account_id=credit_card_account.id,
        closing_day=15,
        due_day=25,
        credit_limit=10000,
        last_four_digits="1234",
        is_active=True,
    )
    db_session.add(card)
    await db_session.flush()
    await db_session.refresh(card)
    return card


@pytest_asyncio.fixture
async def credit_card_due_before_closing(db_session: AsyncSession, test_user: User) -> CreditCard:
    """Cartão com due_day < closing_day (vencimento no mês seguinte ao fechamento)."""
    account = Account(
        user_id=test_user.id,
        name="Cartão Due Antes",
        type=AccountType.CREDIT_CARD.value,
        balance=0,
    )
    db_session.add(account)
    await db_session.flush()

    card = CreditCard(
        user_id=test_user.id,
        account_id=account.id,
        closing_day=20,
        due_day=10,
        credit_limit=10000,
        last_four_digits="5678",
        is_active=True,
    )
    db_session.add(card)
    await db_session.flush()
    await db_session.refresh(card)
    return card


@pytest_asyncio.fixture
async def expense_category(db_session: AsyncSession, test_user: User) -> Category:
    category = Category(
        user_id=test_user.id,
        name="Alimentação",
        type=CategoryType.EXPENSE.value,
        icon="utensils",
    )
    db_session.add(category)
    await db_session.flush()
    await db_session.refresh(category)
    return category


@pytest_asyncio.fixture
async def document(db_session: AsyncSession, test_user: User) -> Document:
    doc = Document(
        user_id=test_user.id,
        file_path="/tmp/test-invoice.pdf",
        file_hash="a" * 64,
        file_size=1024,
        mime_type="application/pdf",
        original_filename="fatura.pdf",
        status=DocumentStatus.COMPLETED.value,
        document_type=DocumentType.FATURA_CARTAO.value,
    )
    db_session.add(doc)
    await db_session.flush()
    await db_session.refresh(doc)
    return doc


@pytest.fixture
def second_document_factory(db_session: AsyncSession, test_user: User):
    """Factory para criar documentos adicionais (ex.: reenvio de PDF)."""

    async def _create(suffix: str = "2") -> Document:
        # file_hash precisa ter até 64 chars (SHA256 hex)
        digest = (suffix.encode().hex() + "0" * 64)[:64]
        doc = Document(
            user_id=test_user.id,
            file_path=f"/tmp/test-invoice-{suffix}.pdf",
            file_hash=digest,
            file_size=2048,
            mime_type="application/pdf",
            original_filename=f"fatura-{suffix}.pdf",
            status=DocumentStatus.COMPLETED.value,
            document_type=DocumentType.FATURA_CARTAO.value,
        )
        db_session.add(doc)
        await db_session.flush()
        await db_session.refresh(doc)
        return doc

    return _create
