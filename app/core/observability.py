"""
Logs e erros rastreáveis (#27).

- LOG_FORMAT=json (padrão fora de development): uma linha JSON por evento, com
  request_id, para filtrar no `docker compose logs` ou num agregador. text = formato
  antigo, mais fácil de ler no terminal local.
- SENTRY_DSN: erros 500 vão para o Sentry com environment, release (commit) e
  request_id. Vazio = desligado. Nunca manda dado pessoal nem corpo de requisição
  (fatura, senha de PDF).
"""

import json
import logging
import os
from datetime import UTC, datetime

from app.core.config import settings
from app.core.request_context import RequestIdLogFilter
from app.core.version import COMMIT

TEXT_FORMAT = (
    'time="%(asctime)s" level=%(levelname)s module=%(module)s '
    'request_id=%(request_id)s msg="%(message)s"'
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def log_format() -> str:
    default = "text" if settings.environment == "development" else "json"
    return os.getenv("LOG_FORMAT", default).lower()


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format=TEXT_FORMAT,
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(RequestIdLogFilter())
        if log_format() == "json":
            handler.setFormatter(JsonFormatter())


def configure_sentry() -> bool:
    """Liga o Sentry se houver DSN. Devolve se ligou."""
    if not settings.sentry_dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=COMMIT,
        send_default_pii=False,
        # corpo da requisição pode ter fatura, senha de PDF e dados da conta
        max_request_body_size="never",
        traces_sample_rate=0.0,
    )
    return True
