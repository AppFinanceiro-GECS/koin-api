import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from .core.config import settings
from .core.database import engine
from .core.rate_limit import limiter, rate_limit_exceeded_handler
from .routers import api_router

# Configuracao do novo log estruturado
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format='time="%(asctime)s" level=%(levelname)s module=%(module)s msg="%(message)s"',
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .core.scheduler import shutdown_scheduler, start_scheduler

    # Startup
    try:
        async with engine.begin():
            pass
    except Exception as e:
        # Substituído print() por logger.error()
        logger.error(f"Conexão inicial com banco falhou: {e}")

    # Start APScheduler
    try:
        await start_scheduler()
        logger.info("Scheduler iniciado com sucesso.")
    except Exception as e:
        # Substituído print() por logger.error()
        logger.error(f"Scheduler não iniciou: {e}")

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