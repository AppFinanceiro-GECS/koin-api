from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from .core.config import settings
from .core.database import engine
from .core.rate_limit import limiter, rate_limit_exceeded_handler
from .routers import api_router


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware para adicionar headers de segurança HTTP"""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Headers de segurança
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # HSTS apenas em produção (HTTPS)
        if not settings.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


async def migrate_credit_card_transactions():
    """Migra transações de cartão para faturas no startup."""
    from datetime import date

    from dateutil.relativedelta import relativedelta
    from sqlalchemy import text

    def calculate_invoice_period(closing_day: int, due_day: int, reference_date: date) -> dict:
        if reference_date.day > closing_day:
            next_month = reference_date + relativedelta(months=1)
            ref_month = next_month.month
            ref_year = next_month.year
        else:
            ref_month = reference_date.month
            ref_year = reference_date.year

        try:
            closing_date = date(ref_year, ref_month, min(closing_day, 28))
        except ValueError:
            closing_date = date(ref_year, ref_month, 28)

        if due_day < closing_day:
            due_date_month = closing_date + relativedelta(months=1)
            try:
                due_date = date(due_date_month.year, due_date_month.month, min(due_day, 28))
            except ValueError:
                due_date = date(due_date_month.year, due_date_month.month, 28)
        else:
            try:
                due_date = date(ref_year, ref_month, min(due_day, 28))
            except ValueError:
                due_date = date(ref_year, ref_month, 28)

        return {
            "reference_month": ref_month,
            "reference_year": ref_year,
            "closing_date": closing_date,
            "due_date": due_date,
        }

    try:
        async with engine.begin() as conn:
            # Verificar se há transações de cartão sem fatura
            result = await conn.execute(
                text("""
                SELECT COUNT(*) FROM transactions
                WHERE credit_card_id IS NOT NULL AND invoice_id IS NULL
            """)
            )
            pending_count = result.scalar()

            if pending_count == 0:
                return

            print(f"Migrando {pending_count} transações de cartão para faturas...")

            # Buscar transações pendentes
            result = await conn.execute(
                text("""
                SELECT t.id, t.user_id, t.credit_card_id, t.date, t.amount,
                       cc.closing_day, cc.due_day
                FROM transactions t
                JOIN credit_cards cc ON t.credit_card_id = cc.id
                WHERE t.credit_card_id IS NOT NULL AND t.invoice_id IS NULL
                ORDER BY t.date
            """)
            )
            transactions = result.fetchall()

            invoice_cache = {}
            today = date.today()

            for row in transactions:
                t_id, user_id, card_id, t_date, amount, closing_day, due_day = row
                period = calculate_invoice_period(closing_day, due_day, t_date)
                cache_key = (card_id, period["reference_month"], period["reference_year"])

                if cache_key in invoice_cache:
                    invoice_id = invoice_cache[cache_key]
                else:
                    existing = await conn.execute(
                        text("""
                        SELECT id FROM credit_card_invoices
                        WHERE credit_card_id = :card_id
                          AND reference_month = :month AND reference_year = :year
                    """),
                        {
                            "card_id": card_id,
                            "month": period["reference_month"],
                            "year": period["reference_year"],
                        },
                    )
                    existing_row = existing.fetchone()

                    if existing_row:
                        invoice_id = existing_row[0]
                    else:
                        if period["closing_date"] < today:
                            status = "overdue" if period["due_date"] < today else "closed"
                        else:
                            status = "open"

                        result = await conn.execute(
                            text("""
                            INSERT INTO credit_card_invoices
                            (user_id, credit_card_id, reference_month, reference_year,
                             closing_date, due_date, total_amount, paid_amount, status)
                            VALUES (:user_id, :card_id, :month, :year,
                                    :closing_date, :due_date, 0, 0, :status)
                            RETURNING id
                        """),
                            {
                                "user_id": user_id,
                                "card_id": card_id,
                                "month": period["reference_month"],
                                "year": period["reference_year"],
                                "closing_date": period["closing_date"],
                                "due_date": period["due_date"],
                                "status": status,
                            },
                        )
                        invoice_id = result.fetchone()[0]

                    invoice_cache[cache_key] = invoice_id

                await conn.execute(
                    text("""
                    UPDATE transactions SET invoice_id = :invoice_id WHERE id = :t_id
                """),
                    {"invoice_id": invoice_id, "t_id": t_id},
                )

            # Atualizar totais
            await conn.execute(
                text("""
                UPDATE credit_card_invoices
                SET total_amount = (
                    SELECT COALESCE(SUM(amount), 0) FROM transactions
                    WHERE invoice_id = credit_card_invoices.id
                )
                WHERE id IN (SELECT DISTINCT invoice_id FROM transactions WHERE invoice_id IS NOT NULL)
            """)
            )

            print(
                f"Migração concluída: {len(transactions)} transações, {len(invoice_cache)} faturas."
            )

            # Liberar memória do cache após uso
            invoice_cache.clear()

    except Exception as e:
        print(f"Aviso: Migração de transações de cartão falhou: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .core.scheduler import shutdown_scheduler, start_scheduler

    # Startup
    try:
        async with engine.begin():
            pass
    except Exception as e:
        print(f"Aviso: Conexão inicial com banco falhou: {e}")

    # Start APScheduler (replaces Celery Beat)
    # Migration de cartões roda via scheduler 30s após boot (não bloqueia startup)
    try:
        await start_scheduler()
    except Exception as e:
        print(f"Aviso: Scheduler não iniciou: {e}")

    yield

    # Shutdown
    shutdown_scheduler()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description="API para controle financeiro pessoal inteligente",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Headers de segurança (adicionar antes do CORS)
app.add_middleware(SecurityHeadersMiddleware)

# CORS - mais restritivo
# Em desenvolvimento, permitir localhost e rede local. Em produção, usar lista específica.
if settings.debug:
    allowed_origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:8081",  # Expo Web (biveto-app)
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:8081",
        "https://localhost:3000",
        "https://localhost:3001",
        "https://127.0.0.1:3000",
        "https://127.0.0.1:3001",
    ]
    # Regex para permitir IPs de rede local, localtunnel e cloudflare tunnel (para teste no celular)
    # Aceita HTTP e HTTPS em 192.168.x.x, 10.x.x.x, 172.16-31.x.x nas portas 3000 e 5173
    # Também aceita *.loca.lt e *.trycloudflare.com
    allow_origin_regex = r"^https?://((192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2[0-9]|3[01])\.\d+\.\d+):(3000|5173|8081)|[\w-]+\.loca\.lt|[\w-]+\.trycloudflare\.com)$"
else:
    allowed_origins = [
        origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()
    ]
    allow_origin_regex = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "X-API-Key"],
)

# Rotas
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health_check():
    from .core.scheduler import scheduler

    return {
        "status": "ok",
        "environment": settings.environment,
        "scheduler_active": scheduler.running,
        "scheduler_jobs": len(scheduler.get_jobs()) if scheduler.running else 0,
    }
