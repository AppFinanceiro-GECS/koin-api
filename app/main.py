import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from .core.ai_models import check_ai_models
from .core.config import settings
from .core.database import engine
from .core.errors import register_error_handlers
from .core.modules import enabled_modules
from .core.observability import configure_logging, configure_sentry
from .core.rate_limit import limiter
from .core.request_context import RequestContextMiddleware
from .core.version import API_VERSION, COMMIT
from .modules.documents.services.ai_failures import ai_circuit
from .routers import api_router

# Logs com request_id (JSON fora de development) e Sentry opcional (#27)
configure_logging()
configure_sentry()

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware para adicionar headers de segurança HTTP"""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Headers de segurança
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        # X-XSS-Protection saiu: é obsoleto e, nos navegadores antigos, pode abrir brecha (#51)
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # HSTS apenas em produção (HTTPS)
        if not settings.debug:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .core.scheduler import shutdown_scheduler, start_scheduler

    # Startup
    try:
        async with engine.begin():
            pass
    except Exception as e:
        logger.error(f"Conexão inicial com banco falhou: {e}")

    # Start APScheduler
    try:
        await start_scheduler()
        logger.info("Scheduler iniciado com sucesso.")
    except Exception as e:
        logger.error(f"Scheduler não iniciou: {e}")

    # Em segundo plano: a chamada ao Google não atrasa o /health do deploy
    app.state.ai_model_check = asyncio.create_task(check_ai_models())

    yield

    # Shutdown
    shutdown_scheduler()
    await engine.dispose()


def docs_urls(environment: str) -> dict:
    """
    Swagger, ReDoc e openapi.json ficam abertos em desenvolvimento e na hml, para os grupos,
    e fechados em produção: não expõem o mapa da API (#51). O contrato vai na release (ci.yml).
    """
    if environment == "production":
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}


app = FastAPI(
    title=settings.app_name,
    description="API para controle financeiro pessoal inteligente",
    version=API_VERSION,
    lifespan=lifespan,
    # operationId = nome da função da rota: o cliente gerado no koin-app ganha nomes
    # legíveis (login, list_transactions) em vez de login_api_v1_auth_login_post (#54)
    generate_unique_id_function=lambda route: route.name,
    **docs_urls(settings.environment),
)

# Rate limiting
app.state.limiter = limiter

# Erros no formato problem+json, com code estável e request_id (#41)
register_error_handlers(app)

# Headers de segurança (adicionar antes do CORS)
app.add_middleware(SecurityHeadersMiddleware)

# CORS - mais restritivo
if settings.debug:
    allowed_origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:8081",
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
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "X-API-Key",
        "X-Request-ID",
    ],
    expose_headers=["X-Request-ID", "X-API-Version"],
)

# Por último = mais externo: toda resposta, inclusive erro e preflight, leva o id
app.add_middleware(RequestContextMiddleware)

# Rotas
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health/live")
async def liveness():
    """O processo responde. Usado pelo healthcheck do Docker (não depende do banco)."""
    return {"status": "ok"}


@app.get("/health")
async def health_check():
    """Prontidão: banco acessível. 503 quando o banco cai, para o monitor alertar."""
    from .core.scheduler import scheduler

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.error("health_db_failed error_type=%s", type(e).__name__)
        db_ok = False

    body = {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "error",
        "version": API_VERSION,
        "commit": COMMIT,
        "environment": settings.environment,
        "scheduler_active": scheduler.running,
        "scheduler_jobs": len(scheduler.get_jobs()) if scheduler.running else 0,
        # o app esconde as telas dos módulos desligados (#42)
        "modules": sorted(enabled_modules()),
        # RN016: o app avisa antes do envio que a leitura está lenta ou pausada
        "ai": ai_circuit.state(),
    }
    return JSONResponse(body, status_code=200 if db_ok else 503)
