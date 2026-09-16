"""Rate limiting configuration using slowapi"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def get_user_identifier(request: Request) -> str:
    """Get identifier for rate limiting - IP address or user ID if authenticated"""
    # Try to get user from request state (set by auth middleware)
    if hasattr(request.state, "user") and request.state.user:
        return f"user:{request.state.user.id}"
    # Fall back to IP address
    return get_remote_address(request)


# Create limiter instance with in-memory storage
# storage_uri="memory://" usa dict com cleanup automático baseado nos limites definidos
# Para produção com múltiplos workers, considerar usar Redis: storage_uri="redis://localhost:6379"
limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri="memory://",
    default_limits=["100/minute"],
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Custom handler for rate limit exceeded"""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Muitas requisições. Tente novamente em alguns minutos.",
            "retry_after": exc.detail.split("per")[0].strip() if exc.detail else "1 minute",
        },
    )
