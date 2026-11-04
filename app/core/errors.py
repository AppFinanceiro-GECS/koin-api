"""
Contrato de erro (#41), no formato RFC 9457 (application/problem+json):

    {"type": "about:blank", "title": "Not Found", "status": 404,
     "detail": "Documento não encontrado", "code": "not_found",
     "request_id": "3f9c...", "errors": [{"field": "body.email", "message": "..."}]}

O app decide pelo `code`, que é estável. `detail` mantém o formato de antes
(texto, objeto ou a lista do Pydantic) para o koin-app atual continuar lendo.
"""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import current_request_id

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"

STATUS_CODES = {
    400: "bad_request",
    401: "not_authenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
}

# Mensagens padrão do Starlette/FastAPI que chegariam em inglês ao usuário
TRANSLATED = {
    "Not authenticated": "Não autenticado",
    "Not Found": "Recurso não encontrado",
    "Method Not Allowed": "Método não permitido",
}


def problem(
    request: Request,
    status: int,
    detail,
    code: str | None = None,
    errors: list[dict] | None = None,
    headers: dict | None = None,
    **extra,
) -> JSONResponse:
    request_id = current_request_id(request)
    try:
        title = HTTPStatus(status).phrase
    except ValueError:
        title = "Error"
    body = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code or STATUS_CODES.get(status, "error"),
        "request_id": request_id,
        **extra,
    }
    if errors:
        body["errors"] = errors
    response = JSONResponse(
        jsonable_encoder(body), status_code=status, headers=headers, media_type=PROBLEM_JSON
    )
    response.headers["X-Request-ID"] = request_id
    return response


def _code_from_detail(detail) -> str | None:
    """Rotas que já mandam {"code"/"error": "..."} no detail mantêm o próprio código"""
    if isinstance(detail, dict):
        for key in ("code", "error"):
            if isinstance(detail.get(key), str):
                return detail[key]
    return None


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, str):
        detail = TRANSLATED.get(detail, detail)
    return problem(
        request,
        exc.status_code,
        detail,
        code=_code_from_detail(detail),
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    raw = jsonable_encoder(exc.errors(), custom_encoder={Exception: str})
    errors = [
        {
            "field": ".".join(str(part) for part in err.get("loc", [])),
            "message": err.get("msg", ""),
            "type": err.get("type", ""),
        }
        for err in raw
    ]
    return problem(request, 422, raw, errors=errors)


async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return problem(
        request,
        429,
        "Muitas requisições. Tente novamente em alguns minutos.",
        retry_after=exc.detail.split("per")[0].strip() if exc.detail else "1 minute",
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    # detalhe técnico só no log; a resposta leva o id para achar esta linha
    logger.exception("unhandled_error path=%s error_type=%s", request.url.path, type(exc).__name__)
    request_id = current_request_id(request)
    return problem(
        request,
        500,
        f"Erro interno. Tente de novo; se continuar, informe o código {request_id}.",
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
