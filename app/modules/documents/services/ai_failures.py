"""
RN016 (#57) e catálogo de erros do processamento (#37).

Quando a leitura por IA não está disponível, o envio não se perde: o documento fica
`waiting_ai` e o job do scheduler reprocessa quando `next_retry_at` vence. O usuário vê
só a mensagem do catálogo; o erro técnico vai para o log com o document_id.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.utils import utc_now

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Failure:
    code: str
    message: str
    # None = falha definitiva; senão, espera inicial antes de tentar de novo
    retry_after: timedelta | None = None


AI_QUOTA_EXHAUSTED = Failure(
    "ai_quota_exhausted",
    "A leitura automática atingiu o limite de hoje. Sua fatura está guardada e será lida "
    "sozinha assim que o serviço voltar. Se preferir, lance as compras manualmente.",
    timedelta(minutes=15),
)
AI_BUSY = Failure(
    "ai_busy",
    "A leitura está mais lenta que o normal. Sua fatura está na fila e avisamos quando "
    "estiver pronta.",
    timedelta(minutes=5),
)
AI_UNAVAILABLE = Failure(
    "ai_unavailable",
    "A leitura automática está temporariamente indisponível. Sua fatura está guardada.",
    timedelta(minutes=30),
)
UNREADABLE_DOCUMENT = Failure(
    "unreadable_document",
    "Não conseguimos ler este arquivo. Tente uma foto com mais luz ou o PDF da fatura.",
)
PASSWORD_REQUIRED = Failure(
    "password_required",
    "Este PDF tem senha. Envie de novo informando a senha da fatura.",
)
FILE_MISSING = Failure(
    "file_missing",
    "O arquivo deste documento não está mais disponível. Envie o arquivo de novo.",
)
PROCESSING_TIMEOUT = Failure(
    "processing_timeout",
    "A leitura deste arquivo não terminou. Tente enviar de novo.",
)

CATALOG = {
    f.code: f
    for f in (
        AI_QUOTA_EXHAUSTED,
        AI_BUSY,
        AI_UNAVAILABLE,
        UNREADABLE_DOCUMENT,
        PASSWORD_REQUIRED,
        FILE_MISSING,
        PROCESSING_TIMEOUT,
    )
}

# Teto do backoff e de tentativas: depois disso o documento vira failed (ai_unavailable)
MAX_RETRY_DELAY = timedelta(hours=6)
MAX_AI_ATTEMPTS = 20

_QUOTA = re.compile(r"\b429\b|resource_exhausted|quota|rate limit", re.I)
_BUSY = re.compile(
    r"\b50[0234]\b|unavailable|overloaded|high demand|deadline|timed? ?out|timeout", re.I
)
_AUTH = re.compile(
    r"\b40[13]\b|api[_ ]?key|permission_denied|unauthenticated|nao configurada|not configured",
    re.I,
)


def classify(error: BaseException | str | None) -> Failure:
    """Mapeia exceção (ou texto de erro) do google.genai/Mistral/httpx para o catálogo."""
    if error is None:
        return UNREADABLE_DOCUMENT
    if isinstance(error, TimeoutError):
        return AI_BUSY
    text = error if isinstance(error, str) else f"{type(error).__name__} {error}"
    code = getattr(error, "code", None) or getattr(error, "status_code", None)
    if code == 429 or _QUOTA.search(text):
        return AI_QUOTA_EXHAUSTED
    if code in (500, 502, 503, 504) or _BUSY.search(text):
        return AI_BUSY
    if code in (401, 403) or _AUTH.search(text):
        return AI_UNAVAILABLE
    return UNREADABLE_DOCUMENT


def next_retry_at(failure: Failure, attempts: int, now: datetime | None = None) -> datetime:
    """Backoff exponencial a partir da espera do tipo de falha, com teto"""
    base = failure.retry_after or timedelta(minutes=5)
    delay = min(base * (2 ** max(attempts - 1, 0)), MAX_RETRY_DELAY)
    return (now or utc_now()) + delay


class AICircuit:
    """
    Disjuntor global: depois de um 429 ninguém chama a IA até a pausa vencer.
    Em memória de propósito: a API roda com um worker só (o scheduler está nele).
    """

    def __init__(self):
        self.paused_until: datetime | None = None
        self.last_busy_at: datetime | None = None

    def record(self, failure: Failure, until: datetime) -> None:
        now = utc_now()
        if failure is AI_QUOTA_EXHAUSTED:
            if self.paused_until is None or until > self.paused_until:
                self.paused_until = until
                logger.warning("ai_circuit_open until=%s", until.isoformat())
        elif failure is AI_BUSY:
            self.last_busy_at = now

    def record_success(self) -> None:
        self.paused_until = None
        self.last_busy_at = None

    def is_open(self, now: datetime | None = None) -> bool:
        return self.paused_until is not None and (now or utc_now()) < self.paused_until

    def state(self) -> str:
        """Para o /health: o app avisa antes do envio que a leitura está lenta"""
        now = utc_now()
        if self.is_open(now):
            return "quota_exhausted"
        if self.last_busy_at and now - self.last_busy_at < timedelta(minutes=10):
            return "degraded"
        return "ok"


ai_circuit = AICircuit()
