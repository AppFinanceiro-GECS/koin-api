"""
#27: log em JSON com request_id e Sentry sem dado pessoal.
"""

import json
import logging

import pytest

from app.core import observability
from app.core.request_context import RequestIdLogFilter, request_id_var


def _record(msg="pagamento ok", exc=None):
    record = logging.LogRecord("app.teste", logging.INFO, __file__, 1, msg, None, exc)
    token = request_id_var.set("req-123")
    try:
        RequestIdLogFilter().filter(record)
    finally:
        request_id_var.reset(token)
    return record


def test_log_json_tem_request_id():
    line = observability.JsonFormatter().format(_record("fatura lida"))
    entry = json.loads(line)
    assert entry["msg"] == "fatura lida"
    assert entry["request_id"] == "req-123"
    assert entry["level"] == "INFO"
    assert entry["time"].endswith("+00:00")


def test_log_json_inclui_a_excecao():
    try:
        raise ValueError("quebrou")
    except ValueError:
        import sys

        line = observability.JsonFormatter().format(_record(exc=sys.exc_info()))
    assert "ValueError: quebrou" in json.loads(line)["exc"]


@pytest.mark.parametrize(
    "environment,env_value,expected",
    [
        ("development", None, "text"),
        ("staging", None, "json"),
        ("production", None, "json"),
        ("production", "text", "text"),
    ],
)
def test_formato_padrao_por_ambiente(monkeypatch, environment, env_value, expected):
    monkeypatch.setattr(observability.settings, "environment", environment)
    if env_value is None:
        monkeypatch.delenv("LOG_FORMAT", raising=False)
    else:
        monkeypatch.setenv("LOG_FORMAT", env_value)
    assert observability.log_format() == expected


def test_sentry_desligado_sem_dsn(monkeypatch):
    import sentry_sdk

    monkeypatch.setattr(observability.settings, "sentry_dsn", None)
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: pytest.fail("não deveria iniciar"))
    assert observability.configure_sentry() is False


def test_sentry_sem_dado_pessoal_nem_corpo(monkeypatch):
    import sentry_sdk

    calls = []
    monkeypatch.setattr(observability.settings, "sentry_dsn", "https://chave@o0.ingest.sentry.io/1")
    monkeypatch.setattr(observability.settings, "environment", "staging")
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))

    assert observability.configure_sentry() is True
    options = calls[0]
    assert options["send_default_pii"] is False
    assert options["max_request_body_size"] == "never"
    assert options["environment"] == "staging"
    assert options["release"] == observability.COMMIT
