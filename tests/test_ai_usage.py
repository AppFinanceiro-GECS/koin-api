"""Offline billing/limits tests. Synthetic provider metadata is not live billing."""

import asyncio
import io
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.ai_usage import (
    AIUnavailable,
    calculate_cost,
    load_price,
    normalize_usage,
    reserve_document,
    tracked_call,
    usage_context,
)
from app.core.config import Settings, settings
from app.core.security import create_access_token
from app.core.utils import utc_now
from app.models.ai_usage import AIDailyBudget, AIUsage, LicenseDocumentUsage
from app.models.document import Document
from app.models.license import License
from app.models.user import User
from app.modules.documents.services.document_service import DocumentService
from app.modules.documents.services.providers.google_provider import GoogleProvider

MODEL = "gemini-3.5-flash-lite"


def response():
    return SimpleNamespace(
        text='{"document_type":"cupom_fiscal","items":[]}',
        usage_metadata=SimpleNamespace(
            prompt_token_count=100,
            candidates_token_count=20,
            thoughts_token_count=7,
            cached_content_token_count=10,
        ),
    )


@pytest.fixture(autouse=True)
def billing_settings(monkeypatch):
    monkeypatch.setattr(settings, "ai_daily_budget_usd", None)
    monkeypatch.setattr(settings, "ai_call_reservation_usd", Decimal("0.1"))
    monkeypatch.setattr(settings, "ai_prices_file", "config/ai_prices.json")


async def make_document(db, user, index=1):
    document = Document(
        user_id=user.id,
        file_path="synthetic",
        file_hash=f"{index:064x}",
        file_size=10,
        mime_type="application/pdf",
        original_filename="synthetic.pdf",
    )
    db.add(document)
    await db.commit()
    return document


async def make_license(db, user, limit):
    license = License(key=f"synthetic-{user.id}", max_documents_per_month=limit)
    db.add(license)
    await db.flush()
    user.license_id = license.id
    user.license = license
    await db.commit()
    return license


@pytest.mark.parametrize("sdk", [True, False])
def test_metadata_and_thinking_are_counted_once(sdk):
    value = (
        response()
        if sdk
        else {
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 20,
                "thoughtsTokenCount": 7,
                "cachedContentTokenCount": 10,
            }
        }
    )
    counts, known = normalize_usage(value, "google")
    assert known
    _, prices = load_price("google", MODEL)
    assert calculate_cost(counts, prices) == Decimal("0.0000948")


def test_ocr_uses_pages_not_fake_tokens():
    counts, known = normalize_usage({"usage_info": {"pages_processed": 3}}, "mistral")
    assert known and counts["input_tokens"] is None
    _, prices = load_price("mistral", "mistral-ocr-latest")
    assert calculate_cost(counts, prices) == Decimal("0.012")
    assert calculate_cost(counts, prices, "annotation") == Decimal("0.015")


def test_mistral_chat_metadata():
    counts, known = normalize_usage(
        {"usage": {"prompt_tokens": 100, "completion_tokens": 20}}, "mistral"
    )
    assert known
    _, prices = load_price("mistral", "mistral-small-latest")
    assert calculate_cost(counts, prices) == Decimal("0.000027")


def test_empty_env_budget_is_disabled():
    assert Settings(_env_file=None, ai_daily_budget_usd="").ai_daily_budget_usd is None


async def test_each_retry_is_durable_and_attributed(db_session, test_user):
    doc = await make_document(db_session, test_user)
    call = AsyncMock(side_effect=[RuntimeError("synthetic failure"), response()])
    with usage_context(db_session, test_user.id, doc.id):
        with pytest.raises(RuntimeError):
            await tracked_call("google", MODEL, call)
        await tracked_call("google", MODEL, call)
    await db_session.rollback()
    rows = (await db_session.execute(select(AIUsage).order_by(AIUsage.id))).scalars().all()
    assert [(row.status, row.document_id) for row in rows] == [
        ("failed", doc.id),
        ("measured", doc.id),
    ]
    assert rows[0].cost_usd is None and rows[1].cost_usd == Decimal("0.0000948")
    assert rows[1].latency_ms >= 0


async def test_missing_usage_is_unknown_and_keeps_reservation(db_session, test_user, monkeypatch):
    await db_session.commit()
    monkeypatch.setattr(settings, "ai_daily_budget_usd", Decimal("0.1"))
    call = AsyncMock(return_value={"text": "private synthetic response"})
    with usage_context(db_session, test_user.id):
        await tracked_call("google", MODEL, call)
        with pytest.raises(AIUnavailable):
            await tracked_call("google", MODEL, call)
    row = await db_session.scalar(select(AIUsage))
    assert row.cost_usd is None and row.input_tokens is None and row.status == "unknown_usage"
    assert call.await_count == 1
    assert (await db_session.scalar(select(AIDailyBudget))).committed_usd == Decimal("0.1")


async def test_price_missing_blocks_before_provider(db_session, test_user):
    call = AsyncMock()
    with usage_context(db_session, test_user.id):
        with pytest.raises(AIUnavailable) as error:
            await tracked_call("google", "unpriced-model", call)
    assert error.value.status_code == 503
    call.assert_not_awaited()


async def test_concurrent_daily_calls_cannot_bypass_reservation(db_session, test_user, monkeypatch):
    await db_session.commit()
    monkeypatch.setattr(settings, "ai_daily_budget_usd", Decimal("0.1"))
    started, release = asyncio.Event(), asyncio.Event()

    async def provider():
        started.set()
        await release.wait()
        return response()

    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def first():
        async with factory() as db:
            with usage_context(db, test_user.id):
                await tracked_call("google", MODEL, provider)

    task = asyncio.create_task(first())
    await asyncio.wait_for(started.wait(), timeout=5)
    try:
        with usage_context(db_session, test_user.id):
            with pytest.raises(AIUnavailable):
                await tracked_call("google", MODEL, AsyncMock())
    finally:
        release.set()
        await task
    assert await db_session.scalar(select(func.count(AIUsage.id))) == 1


@pytest.mark.parametrize("limit", [0, 1])
async def test_monthly_quota_and_zero(db_session, test_user, limit):
    license = await make_license(db_session, test_user, limit)
    if limit:
        await reserve_document(db_session, test_user)
        await db_session.commit()
    with pytest.raises(HTTPException) as error:
        await reserve_document(db_session, test_user)
    assert error.value.status_code == 402
    assert "limite do plano" in error.value.detail["message"]
    if limit:
        counter = await db_session.get(
            LicenseDocumentUsage, (license.id, utc_now().date().replace(day=1))
        )
        assert counter.documents == 1


async def test_quota_shared_by_license_and_survives_delete(db_session, test_user):
    license = await make_license(db_session, test_user, 1)
    member = User(
        email="member@synthetic.test", name="Member", hashed_password="x", license=license
    )
    db_session.add(member)
    await db_session.commit()
    await reserve_document(db_session, test_user)
    doc = await make_document(db_session, test_user)
    await db_session.delete(doc)
    await db_session.commit()
    with pytest.raises(HTTPException):
        await reserve_document(db_session, member)


async def test_existing_documents_count_at_first_reservation(db_session, test_user):
    await make_license(db_session, test_user, 1)
    await make_document(db_session, test_user)
    with pytest.raises(HTTPException):
        await reserve_document(db_session, test_user)


@pytest.mark.parametrize("method", ["upload", "upload_async", "upload_batch"])
async def test_all_upload_paths_block_before_extraction(
    db_session, test_user, monkeypatch, tmp_path, method
):
    await make_license(db_session, test_user, 0)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    service = DocumentService(db_session)
    extract = AsyncMock()
    monkeypatch.setattr(service, "_process_document", extract)
    monkeypatch.setattr(service, "_process_batch_images", extract)
    file = UploadFile(file=io.BytesIO(b"synthetic-image"), filename="synthetic.png")
    args = [test_user, [file]] if method == "upload_batch" else [test_user, file]
    if method == "upload_async":
        args.append(BackgroundTasks())
    with pytest.raises(HTTPException) as error:
        await getattr(service, method)(*args)
    assert error.value.status_code == 402
    extract.assert_not_awaited()
    assert not list(tmp_path.rglob("*.png"))


async def test_google_records_even_when_response_parser_fails(
    db_session, test_user, monkeypatch, caplog, capsys
):
    await db_session.commit()
    provider = GoogleProvider(
        model=MODEL,
        prompt="PRIVATE SYNTHETIC PROMPT",
        parse_response_fn=lambda text: (_ for _ in ()).throw(ValueError("parse")),
    )
    monkeypatch.setattr(provider, "_get_client", lambda: object())
    monkeypatch.setattr(provider, "_generate_content_sync", lambda *args: response())
    with usage_context(db_session, test_user.id):
        with pytest.raises(ValueError):
            await provider.extract_from_image(b"synthetic", "image/png")
    assert (await db_session.scalar(select(AIUsage))).status == "measured"
    assert "PRIVATE SYNTHETIC PROMPT" not in caplog.text + capsys.readouterr().out


async def test_admin_usage_permissions_grouping_and_unknown_cost(client, db_session, test_user):
    token = create_access_token(test_user.id)
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/v1/admin/ai-usage", headers=headers)).status_code == 403
    test_user.is_admin = True
    await db_session.commit()
    with usage_context(db_session, test_user.id, feature="chat"):
        await tracked_call("google", MODEL, AsyncMock(return_value=response()))
        await tracked_call("google", MODEL, AsyncMock(return_value={}))
    for grouping in ("user", "feature", "model"):
        result = await client.get(f"/api/v1/admin/ai-usage?group_by={grouping}", headers=headers)
        assert result.status_code == 200
        row = result.json()["items"][0]
        assert row["calls"] == 2 and row["unmeasured_calls"] == 1 and row["cost_usd"] is None
    assert (
        await client.get("/api/v1/admin/ai-usage?group_by=invalid", headers=headers)
    ).status_code == 422
    assert (
        await client.get("/api/v1/admin/ai-usage?from=2026-10-08&to=2026-10-07", headers=headers)
    ).status_code == 422


async def test_thirty_synthetic_documents_offline(db_session, test_user):
    """Thirty mocked invoices validate attribution; this does not satisfy hml acceptance."""
    for index in range(30):
        document = await make_document(db_session, test_user, index + 1)
        with usage_context(db_session, test_user.id, document.id):
            await tracked_call("google", MODEL, AsyncMock(return_value=response()))
            await tracked_call(
                "google", MODEL, AsyncMock(return_value=response()), feature="classification"
            )
    totals = (
        await db_session.execute(
            select(
                func.count(func.distinct(AIUsage.document_id)),
                func.count(AIUsage.id),
                func.sum(AIUsage.cost_usd),
            )
        )
    ).one()
    assert totals == (30, 60, Decimal("0.005688"))


async def test_month_rollover_and_unlimited(db_session, test_user):
    license = await make_license(db_session, test_user, 1)
    db_session.add(
        LicenseDocumentUsage(
            license_id=license.id,
            month=(utc_now().replace(day=1) - timedelta(days=1)).date().replace(day=1),
            documents=100,
        )
    )
    await db_session.commit()
    await reserve_document(db_session, test_user)
    await db_session.commit()
    license.max_documents_per_month = None
    await db_session.commit()
    await reserve_document(db_session, test_user)


async def test_monthly_reservation_rolls_back_on_rejected_upload(db_session, test_user):
    await make_license(db_session, test_user, 1)
    await reserve_document(db_session, test_user)
    await db_session.rollback()
    await db_session.refresh(test_user)
    await reserve_document(db_session, test_user)
    await db_session.commit()
    with pytest.raises(HTTPException):
        await reserve_document(db_session, test_user)


async def test_retry_cannot_bypass_monthly_quota(db_session, test_user, tmp_path):
    await make_license(db_session, test_user, 1)
    doc = await make_document(db_session, test_user)
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(b"synthetic")
    doc.file_path = str(path)
    await db_session.commit()
    with pytest.raises(HTTPException) as error:
        await DocumentService(db_session).retry_processing(test_user, doc.id)
    assert error.value.status_code == 402


async def test_zero_daily_budget_never_calls_provider(db_session, test_user, monkeypatch):
    monkeypatch.setattr(settings, "ai_daily_budget_usd", Decimal("0"))
    call = AsyncMock()
    with usage_context(db_session, test_user.id):
        with pytest.raises(AIUnavailable):
            await tracked_call("google", MODEL, call)
    call.assert_not_awaited()


async def test_resolved_model_is_preserved(db_session, test_user):
    value = response()
    value.model_version = "gemini-3.5-flash-lite-resolved"
    with usage_context(db_session, test_user.id):
        await tracked_call("google", MODEL, AsyncMock(return_value=value))
    row = await db_session.scalar(select(AIUsage))
    assert row.model == value.model_version and row.requested_model == MODEL


async def test_document_survives_daily_breaker(
    client, db_session, test_user, monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "ai_daily_budget_usd", Decimal("0"))
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "vision_provider", "google")
    monkeypatch.setattr(settings, "vision_model", MODEL)
    monkeypatch.setattr(settings, "google_api_key", "synthetic-test-key")
    monkeypatch.setattr(settings, "mistral_api_key", None)
    monkeypatch.setattr(GoogleProvider, "_get_client", lambda self: object())
    calls = []
    monkeypatch.setattr(GoogleProvider, "_generate_content_sync", lambda *args: calls.append(1))
    headers = {"Authorization": f"Bearer {create_access_token(test_user.id)}"}
    result = await client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": ("synthetic.png", b"synthetic", "image/png")},
    )
    assert result.status_code == 429
    document_id = result.json()["detail"]["document_id"]
    doc = await db_session.get(Document, document_id)
    assert doc.status == "failed"
    from pathlib import Path

    assert Path(doc.file_path).read_bytes() == b"synthetic"
    assert not calls


async def test_new_migration_upgrade_and_downgrade(test_engine):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    spec = importlib.util.spec_from_file_location(
        "issue38_migration", Path("alembic/versions/add_ai_usage_and_limits.py")
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    async with test_engine.begin() as connection:

        def exercise(conn):
            for table in ("license_document_usage", "ai_daily_budget", "ai_usage"):
                conn.exec_driver_sql(f"DROP TABLE {table}")
            context = MigrationContext.configure(conn)
            with Operations.context(context):
                migration.upgrade()
                assert {"ai_usage", "ai_daily_budget", "license_document_usage"}.issubset(
                    inspect(conn).get_table_names()
                )
                assert "requested_model" in {
                    column["name"] for column in inspect(conn).get_columns("ai_usage")
                }
                migration.downgrade()
                assert "ai_usage" not in inspect(conn).get_table_names()

        await connection.run_sync(exercise)


def test_google_sdk_pydantic_response_is_not_confused_with_http_json():
    from google.genai import types

    value = types.GenerateContentResponse(
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=100, candidates_token_count=20, thoughts_token_count=7
        )
    )
    counts, known = normalize_usage(value, "google")
    assert known and counts["thinking_tokens"] == 7


async def test_benchmark_runner_with_mock_http(monkeypatch, tmp_path):
    import json

    import httpx

    from scripts.benchmark_ai_usage import run, synthetic_invoice

    monkeypatch.setenv("KOIN_BENCHMARK_USER_TOKEN", "PRIVATE_USER_TOKEN")
    monkeypatch.setenv("KOIN_BENCHMARK_ADMIN_TOKEN", "PRIVATE_ADMIN_TOKEN")
    uploads = []

    def handler(request):
        if request.method == "POST":
            uploads.append(request.content)
            return httpx.Response(202, json={"id": len(uploads)})
        if "admin/ai-usage" in request.url.path:
            return httpx.Response(
                200, json={"items": [{"unmeasured_calls": 0, "measured_cost_usd": "0.01"}]}
            )
        return httpx.Response(200, json={"status": "completed"})

    output = tmp_path / "report.json"
    args = SimpleNamespace(
        base_url="https://hml.example.test",
        count=30,
        poll_attempts=1,
        poll_interval=0,
        output=str(output),
    )
    assert await run(args, transport=httpx.MockTransport(handler))
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["measured_cost_usd"] == "0.30" and len(uploads) == 30
    assert "PRIVATE_" not in output.read_text(encoding="utf-8")
    assert synthetic_invoice(0, "run") != synthetic_invoice(1, "run")


async def test_concurrent_upload_reservations_share_last_monthly_slot(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.database import Base

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path.as_posix()}/quota.sqlite")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as db:
            license = License(key="concurrent-synthetic", max_documents_per_month=1)
            user = User(
                email="concurrent@synthetic.test", hashed_password="x", name="Test", license=license
            )
            db.add(user)
            await db.commit()
            user_id = user.id

        async def reserve():
            async with factory() as db:
                user = await db.scalar(select(User).where(User.id == user_id))
                try:
                    await reserve_document(db, user)
                    await db.commit()
                    return "accepted"
                except HTTPException as error:
                    await db.rollback()
                    assert error.status_code == 402
                    return "blocked"

        assert sorted(await asyncio.gather(reserve(), reserve())) == ["accepted", "blocked"]
    finally:
        await engine.dispose()
