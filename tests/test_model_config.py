"""
O nome do modelo Gemini vive só em app/core/config.py (VISION_MODEL, CLASSIFIER_MODEL, CHAT_MODEL).
Modelo fixo no código fica para trás quando o Google desliga uma família (a 2.0 saiu em 01/06/2026).
"""

import ast
import asyncio
import re
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings

APP_DIR = Path(__file__).resolve().parent.parent / "app"
CONFIG_FILE = APP_DIR / "core" / "config.py"
MODEL_LITERAL = re.compile(r"gemini-[a-zA-Z0-9][a-zA-Z0-9._-]*")


def model_literal_lines(source: str) -> list[int]:
    """Inspect decoded Python strings, including URL/f-string parts; ignore comments."""
    return sorted(
        {
            node.lineno
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and MODEL_LITERAL.search(node.value)
        }
    )


def test_nenhum_modelo_gemini_fixo_fora_do_config():
    ofensores = [
        f"{path.relative_to(APP_DIR.parent)}:{n}"
        for path in APP_DIR.rglob("*.py")
        if path != CONFIG_FILE
        for n in model_literal_lines(path.read_text(encoding="utf-8"))
    ]
    assert not ofensores, f"Use settings.vision_model/classifier_model/chat_model: {ofensores}"


@pytest.mark.parametrize(
    "source",
    [
        'model = "gemini-3.8-flash"',
        'model = "gemini-flash-latest"',
        'model = "gemini-flash-lite-latest"',
        'url = f"https://example.test/models/gemini-flash-latest:{action}"',
        'model = "gemini-" "3.5-flash-lite"',
        r'model = "\x67emini-flash-latest"',
    ],
)
def test_detector_cobre_ids_e_aliases(source):
    assert model_literal_lines(source) == [1]


@pytest.mark.parametrize(
    "source",
    [
        '# Gemini model example: "gemini-flash-latest"\nmodel = settings.vision_model',
        '"""Integração Google Gemini."""\nmodel = settings.chat_model',
        'name = "Google Gemini"',
    ],
)
def test_detector_ignora_comentarios_e_mencoes_genericas(source):
    assert model_literal_lines(source) == []


def test_modelos_padrao_nao_sao_da_familia_desligada():
    settings = Settings(_env_file=None)
    for model in (settings.vision_model, settings.classifier_model):
        assert not model.startswith("gemini-2.0"), model


def test_modelos_configuraveis_por_ambiente(monkeypatch):
    monkeypatch.setenv("VISION_MODEL", "gemini-x-teste")
    monkeypatch.setenv("CLASSIFIER_MODEL", "gemini-y-teste")
    monkeypatch.setenv("CHAT_MODEL", "gemini-z-teste")
    settings = Settings(_env_file=None)
    assert settings.vision_model == "gemini-x-teste"
    assert settings.classifier_model == "gemini-y-teste"
    assert settings.chat_model == "gemini-z-teste"


def test_chat_sem_override_mantem_heranca(monkeypatch):
    monkeypatch.delenv("CHAT_MODEL", raising=False)
    monkeypatch.setenv("VISION_MODEL", "gemini-vision-teste")
    configured = Settings(_env_file=None)
    assert configured.chat_model is None
    assert (configured.chat_model or configured.vision_model) == "gemini-vision-teste"


@pytest.mark.parametrize(
    "chat_override,expected_model",
    [
        (None, "gemini-vision-teste"),
        ("gemini-chat-teste", "gemini-chat-teste"),
    ],
)
def test_chat_google_consume_override_ou_vision(monkeypatch, chat_override, expected_model):
    """Exercise the real chat model resolver through a local HTTP mock, never the API."""
    from app.modules.chat.services import financial_agent_service

    configured = Settings(
        _env_file=None,
        google_api_key="synthetic-test-key",
        vision_model="gemini-vision-teste",
        chat_model=chat_override,
    )
    monkeypatch.setattr(financial_agent_service, "settings", configured)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "Resposta sintética"}]}}],
            },
        )

    client_type = httpx.AsyncClient

    def mock_client(**kwargs):
        return client_type(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(financial_agent_service.httpx, "AsyncClient", mock_client)
    service = financial_agent_service.FinancialAgentService(None)
    response = asyncio.run(service._call_google("Prompt sintético", []))
    assert response == "Resposta sintética"
    assert len(requests) == 1
    assert requests[0].url.path == f"/v1beta/models/{expected_model}:generateContent"
