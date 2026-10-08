"""Meter individual billable calls and reserve budget atomically in the database."""

import inspect
import json
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from functools import wraps
from pathlib import Path
from time import perf_counter

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.utils import utc_now
from app.models.ai_usage import AIDailyBudget, AIUsage, LicenseDocumentUsage
from app.models.document import Document
from app.models.user import User


class AIUnavailable(HTTPException):
    def __init__(self, code="ai_daily_limit", message="IA indisponivel: limite diario de gasto"):
        super().__init__(
            429 if code == "ai_daily_limit" else 503, {"error": code, "message": message}
        )


@dataclass
class UsageContext:
    db: object
    user_id: int
    document_id: int | None
    feature: str


_context: ContextVar[UsageContext | None] = ContextVar("ai_usage_context", default=None)


@contextmanager
def usage_context(db, user_id, document_id=None, feature="extraction"):
    token = _context.set(UsageContext(db, user_id, document_id, feature))
    try:
        yield
    finally:
        _context.reset(token)


def metered(feature, document_arg=None):
    """Bind attribution explicitly at service boundaries; context is task-local."""

    def decorate(fn):
        signature = inspect.signature(fn)

        @wraps(fn)
        async def wrapped(*args, **kwargs):
            values = signature.bind(*args, **kwargs).arguments
            service = values["self"]
            document = values.get(document_arg) if document_arg else None
            user = values.get("user")
            user_id = document.user_id if document is not None else user.id
            with usage_context(
                service.db, user_id, document.id if document is not None else None, feature
            ):
                try:
                    return await fn(*args, **kwargs)
                except AIUnavailable as error:
                    if document is not None:
                        document.status = "failed"
                        document.error_message = error.detail["message"]
                        await service.db.commit()
                        error.detail["document_id"] = document.id
                    raise

        return wrapped

    return decorate


def _field(obj, *names):
    for name in names:
        value = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
        if isinstance(value, (int, str)) and not isinstance(value, bool):
            return value
    return None


def normalize_usage(response, provider):
    if isinstance(response, httpx.Response):
        response = response.json()

    def get(name):
        return response.get(name) if isinstance(response, dict) else getattr(response, name, None)

    if provider == "google":
        raw = get("usage_metadata") or get("usageMetadata")
        names = [
            ("prompt_token_count", "promptTokenCount"),
            ("candidates_token_count", "candidatesTokenCount"),
            ("thoughts_token_count", "thoughtsTokenCount"),
            ("cached_content_token_count", "cachedContentTokenCount"),
        ]
    else:
        raw = get("usage")
        names = [
            ("prompt_tokens", "input_tokens"),
            ("completion_tokens", "output_tokens"),
            ("reasoning_tokens",),
            ("cached_tokens",),
        ]
    counts = [int(_field(raw, *keys) or 0) for keys in names]
    if any(count < 0 for count in counts):
        raise ValueError("Invalid token metadata")
    pages = _field(get("usage_info"), "pages_processed")
    token_usage_known = (
        raw is not None
        and _field(raw, *names[0]) is not None
        and _field(raw, *names[1]) is not None
    )
    known = token_usage_known or pages is not None
    if pages is not None and int(pages) < 0:
        raise ValueError("Invalid page metadata")
    if counts[3] > counts[0]:
        raise ValueError("Invalid cache metadata")
    return {
        "input_tokens": int(_field(raw, *names[0])) if _field(raw, *names[0]) is not None else None,
        "output_tokens": int(_field(raw, *names[1]))
        if _field(raw, *names[1]) is not None
        else None,
        "thinking_tokens": counts[2] if token_usage_known else None,
        "cached_input_tokens": counts[3] if token_usage_known else None,
        "pages": int(pages) if pages is not None else None,
    }, known


def load_price(provider, model):
    try:
        config = json.loads(Path(settings.ai_prices_file).read_text(encoding="utf-8"))
        if not isinstance(config["version"], str) or not 1 <= len(config["version"]) <= 50:
            raise ValueError("Invalid pricing version")
        price = config["models"][f"{provider}/{model}"]
        price = {key: Decimal(str(value)) for key, value in price.items()}
        if any(not value.is_finite() or value < 0 for value in price.values()):
            raise ValueError("Invalid price")
        if "per_page" not in price and not {
            "input_per_million",
            "output_per_million",
            "thinking_per_million",
        }.issubset(price):
            raise ValueError("Incomplete price")
        return config["version"], price
    except (OSError, KeyError, ValueError, TypeError, ArithmeticError):
        raise AIUnavailable(
            "ai_pricing_unavailable", "IA indisponivel: preco do modelo nao configurado"
        ) from None


def calculate_cost(counts, price, billing_mode="standard"):
    if "per_page" in price:
        rate = price["annotation_per_page"] if billing_mode == "annotation" else price["per_page"]
        return None if counts["pages"] is None else Decimal(counts["pages"]) * rate
    if counts["input_tokens"] is None or counts["output_tokens"] is None:
        return None
    cached = counts["cached_input_tokens"]
    return (
        Decimal(counts["input_tokens"] - cached) * price["input_per_million"]
        + Decimal(cached) * price.get("cached_input_per_million", price["input_per_million"])
        + Decimal(counts["output_tokens"]) * price["output_per_million"]
        + Decimal(counts["thinking_tokens"]) * price["thinking_per_million"]
    ) / Decimal(1_000_000)


async def insert_if_missing(db, model, values):
    if db.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    await db.execute(insert(model).values(**values).on_conflict_do_nothing())


async def tracked_call(provider, model, invoke, feature=None, billing_mode="standard"):
    """Record before parsing. Unknown consumption remains NULL, never a fake zero.

    Calls without a user context are offline tools/unit tests; application entry
    points establish a context. Reservations survive crashes and timeouts.
    """
    context = _context.get()
    if context is None:
        return await invoke()
    # Preserve an accepted upload even if billing configuration is unavailable.
    await context.db.commit()
    version, price = load_price(provider, model)
    if billing_mode == "annotation" and "annotation_per_page" not in price:
        raise AIUnavailable(
            "ai_pricing_unavailable", "IA indisponivel: preco de anotacao nao configurado"
        )
    factory = async_sessionmaker(context.db.bind, expire_on_commit=False)
    day = utc_now().date()
    reserve = settings.ai_call_reservation_usd
    async with factory() as db:
        await insert_if_missing(db, AIDailyBudget, {"day": day, "committed_usd": 0})
        stmt = update(AIDailyBudget).where(AIDailyBudget.day == day)
        if settings.ai_daily_budget_usd is not None:
            stmt = stmt.where(AIDailyBudget.committed_usd + reserve <= settings.ai_daily_budget_usd)
        result = await db.execute(stmt.values(committed_usd=AIDailyBudget.committed_usd + reserve))
        if result.rowcount != 1:
            raise AIUnavailable()
        row = AIUsage(
            user_id=context.user_id,
            document_id=context.document_id,
            feature=feature or context.feature,
            provider=provider,
            model=model,
            requested_model=model,
            billing_mode=billing_mode,
            pricing_version=version,
            status="pending",
        )
        db.add(row)
        await db.commit()
        usage_id = row.id
    started = perf_counter()
    counts = {}
    cost = None
    state = "failed"
    resolved_model = model
    try:
        response = await invoke()
        metadata_response = response.json() if isinstance(response, httpx.Response) else response
        resolved_model = (
            _field(metadata_response, "model_version", "modelVersion", "model") or model
        )
        state = "unknown_usage"
        counts, known = normalize_usage(response, provider)
        cost = calculate_cost(counts, price, billing_mode) if known else None
        state = "measured" if cost is not None else "unknown_usage"
        return response
    finally:
        async with factory() as db:
            await db.execute(
                update(AIUsage)
                .where(AIUsage.id == usage_id)
                .values(
                    **counts,
                    cost_usd=cost,
                    status=state,
                    model=resolved_model,
                    latency_ms=int((perf_counter() - started) * 1000),
                )
            )
            if cost is not None:
                await db.execute(
                    update(AIDailyBudget)
                    .where(AIDailyBudget.day == day)
                    .values(committed_usd=AIDailyBudget.committed_usd + cost - reserve)
                )
            await db.commit()


async def reserve_document(db, user):
    """A license shares a monthly quota across members; reprocessing consumes quota.

    Legacy users without a license retain existing behavior. None means unlimited;
    zero blocks uploads. Counters survive document deletion.
    """
    license = user.license
    if license is None:
        return
    if not license.is_valid:
        raise HTTPException(
            402, {"error": "plan_limit", "message": "limite do plano: licenca inativa"}
        )
    limit = license.max_documents_per_month
    if limit is None:
        return
    month = utc_now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    baseline = await db.scalar(
        select(func.count(Document.id))
        .join(User, User.id == Document.user_id)
        .where(User.license_id == license.id, Document.created_at >= month)
    )
    await insert_if_missing(
        db,
        LicenseDocumentUsage,
        {"license_id": license.id, "month": month.date(), "documents": baseline or 0},
    )
    result = await db.execute(
        update(LicenseDocumentUsage)
        .where(
            LicenseDocumentUsage.license_id == license.id,
            LicenseDocumentUsage.month == month.date(),
            LicenseDocumentUsage.documents < limit,
        )
        .values(documents=LicenseDocumentUsage.documents + 1)
    )
    if result.rowcount != 1:
        raise HTTPException(
            402, {"error": "plan_limit", "message": "limite do plano: documentos mensais esgotados"}
        )
