"""
Identificador por requisição (#27/#41): o `X-Request-ID` recebido (ou um novo) volta no
header da resposta, entra em todo log da requisição e no corpo dos erros. Com ele,
"minha fatura deu erro" vira uma busca no log.
"""

import logging
import re
import uuid
from contextvars import ContextVar

import sentry_sdk
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.version import API_VERSION

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Aceita o id do cliente só se for curto e sem caracteres de controle (log injection)
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def current_request_id(request: Request | None = None) -> str:
    if request is not None:
        rid = getattr(request.state, "request_id", None)
        if rid:
            return rid
    return request_id_var.get()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("X-Request-ID", "")
        rid = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        request.state.request_id = rid
        request_id_var.set(rid)
        # no-op sem SENTRY_DSN; com ele, o erro no Sentry acha a linha do log
        sentry_sdk.set_tag("request_id", rid)

        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers["X-API-Version"] = API_VERSION
        return response


class RequestIdLogFilter(logging.Filter):
    """Disponibiliza %(request_id)s no formato do log ("-" fora de requisição)"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True
