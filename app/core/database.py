from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

# Configuração específica para cada banco
is_sqlite = settings.database_url.startswith("sqlite")

if is_sqlite:
    # SQLite não suporta pool_size
    engine = create_async_engine(
        settings.database_url,
        echo=settings.sql_echo,
        connect_args={"check_same_thread": False},
    )
else:
    # PostgreSQL com pool otimizado
    engine = create_async_engine(
        settings.database_url,
        echo=settings.sql_echo,
        pool_size=5,  # Conexões mantidas no pool
        max_overflow=10,  # Conexões extras sob demanda
        pool_pre_ping=True,  # Verifica conexão antes de usar
        pool_recycle=300,  # Recicla conexões a cada 5 min
        pool_timeout=30,  # Timeout para obter conexão do pool
    )

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,  # Controle manual de flush
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency que fornece sessão do banco.
    Auto-commit ao final da request se não houver exceção.
    Rollback automático em caso de exceção.
    """
    async with async_session_maker() as session:
        try:
            yield session
            # Auto-commit se não houver exceção
            await session.commit()
        except Exception:
            await session.rollback()
            raise
