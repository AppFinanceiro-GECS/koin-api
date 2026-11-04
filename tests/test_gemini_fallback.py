"""
#34: retry, modelo alternativo em 503, raciocínio mínimo e validação dos modelos na
inicialização. A IA é sempre simulada; nenhum teste chama o Google.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core import ai_models
from app.core.ai_usage import load_price
from app.core.config import Settings, settings
from app.modules.documents.services.providers.google_provider import GoogleProvider

PRIMARY = "gemini-primario-teste"
FALLBACK = "gemini-alternativo-teste"


def _provider(monkeypatch, outcomes):
    """outcomes: model → lista de exceções/respostas, consumidas na ordem."""
    monkeypatch.setattr(settings, "vision_model_fallback", FALLBACK)
    provider = GoogleProvider(model=PRIMARY, parse_response_fn=lambda text: {"text": text})
    provider.retry_delay = 0
    calls = []

    def generate(client, model, contents, config):
        calls.append(model)
        outcome = outcomes[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome)

    monkeypatch.setattr(provider, "_get_client", lambda: object())
    monkeypatch.setattr(provider, "_generate_content_sync", generate)
    return provider, calls


async def test_503_persistente_usa_modelo_alternativo(monkeypatch):
    busy = Exception("503 UNAVAILABLE. This model is currently experiencing high demand")
    provider, calls = _provider(monkeypatch, {PRIMARY: [busy] * 3, FALLBACK: ['{"ok": 1}']})

    result = await provider.extract_from_image(b"synthetic", "image/png")

    assert result == {"text": '{"ok": 1}'}
    assert calls == [PRIMARY, PRIMARY, PRIMARY, FALLBACK]


async def test_503_passageiro_resolve_no_proprio_modelo(monkeypatch):
    busy = Exception("503 UNAVAILABLE")
    provider, calls = _provider(monkeypatch, {PRIMARY: [busy, "pronto"], FALLBACK: []})

    assert await provider.extract_from_image(b"synthetic", "image/png") == {"text": "pronto"}
    assert calls == [PRIMARY, PRIMARY]


async def test_cota_esgotada_nao_troca_de_modelo(monkeypatch):
    """429 é limite da conta (RN016): trocar de modelo só martela a API."""
    quota = Exception("429 RESOURCE_EXHAUSTED")
    provider, calls = _provider(monkeypatch, {PRIMARY: [quota] * 3, FALLBACK: ["nunca"]})

    with pytest.raises(Exception, match="429"):
        await provider.extract_from_image(b"synthetic", "image/png")
    assert calls == [PRIMARY] * 3


async def test_erro_nao_transitorio_falha_sem_retry(monkeypatch):
    bad = Exception("400 INVALID_ARGUMENT")
    provider, calls = _provider(monkeypatch, {PRIMARY: [bad], FALLBACK: ["nunca"]})

    with pytest.raises(Exception, match="400"):
        await provider.extract_from_image(b"synthetic", "image/png")
    assert calls == [PRIMARY]


async def test_alternativo_que_tambem_falha_propaga_o_erro(monkeypatch):
    busy = Exception("503 UNAVAILABLE")
    provider, calls = _provider(monkeypatch, {PRIMARY: [busy] * 3, FALLBACK: [busy] * 3})

    with pytest.raises(Exception, match="503"):
        await provider.extract_from_image(b"synthetic", "image/png")
    assert calls == [PRIMARY] * 3 + [FALLBACK] * 3


async def test_sem_alternativo_configurado(monkeypatch):
    busy = Exception("503 UNAVAILABLE")
    provider, calls = _provider(monkeypatch, {PRIMARY: [busy] * 3})
    monkeypatch.setattr(settings, "vision_model_fallback", None)

    with pytest.raises(Exception, match="503"):
        await provider.extract_from_image(b"synthetic", "image/png")
    assert calls == [PRIMARY] * 3


async def test_extracao_pede_raciocinio_minimo(monkeypatch):
    provider, _ = _provider(monkeypatch, {PRIMARY: ["{}"]})
    configs = []
    original = provider._generate_content_sync
    monkeypatch.setattr(
        provider,
        "_generate_content_sync",
        lambda client, model, contents, config: (
            configs.append(config) or original(client, model, contents, config)
        ),
    )

    await provider.extract_from_image(b"synthetic", "image/png")

    thinking = configs[0].thinking_config
    # thinking_budget=0 devolve 400 nos modelos 3.x; o nível é o que eles aceitam
    assert thinking.thinking_level.lower() == "minimal"
    assert thinking.thinking_budget is None


async def test_nivel_vazio_nao_envia_thinking_config(monkeypatch):
    monkeypatch.setattr(settings, "ai_thinking_level", None)
    provider, _ = _provider(monkeypatch, {PRIMARY: ["{}"]})
    configs = []
    original = provider._generate_content_sync
    monkeypatch.setattr(
        provider,
        "_generate_content_sync",
        lambda client, model, contents, config: (
            configs.append(config) or original(client, model, contents, config)
        ),
    )

    await provider.extract_from_image(b"synthetic", "image/png")

    assert configs[0].thinking_config is None


def test_variaveis_vazias_desligam_alternativo_e_nivel(monkeypatch):
    monkeypatch.setenv("VISION_MODEL_FALLBACK", "")
    monkeypatch.setenv("AI_THINKING_LEVEL", "")
    configured = Settings(_env_file=None)
    assert configured.vision_model_fallback is None
    assert configured.ai_thinking_level is None


def test_modelos_padrao_tem_preco():
    """Sem preço, tracked_call recusa a chamada (ai_pricing_unavailable)."""
    defaults = Settings(_env_file=None)
    prices = json.loads(Path(defaults.ai_prices_file).read_text(encoding="utf-8"))["models"]
    for model in (defaults.vision_model, defaults.classifier_model, defaults.vision_model_fallback):
        assert f"google/{model}" in prices, model
        load_price("google", model)


async def test_validacao_de_modelos_sem_chave_nao_chama_o_google(monkeypatch):
    monkeypatch.setattr(settings, "google_api_key", None)
    monkeypatch.setattr(
        ai_models, "_check_models_sync", lambda: pytest.fail("não deveria chamar o Google")
    )
    assert await ai_models.check_ai_models() is None


async def test_validacao_de_modelos_loga_o_que_nao_existe(monkeypatch, caplog):
    monkeypatch.setattr(settings, "google_api_key", "synthetic-test-key")
    monkeypatch.setattr(settings, "vision_model", "gemini-existe")
    monkeypatch.setattr(settings, "classifier_model", "gemini-2.0-flash")
    monkeypatch.setattr(settings, "vision_model_fallback", None)

    class Models:
        def get(self, model):
            if model == "gemini-2.0-flash":
                raise Exception("404 NOT_FOUND models/gemini-2.0-flash is not found")
            return SimpleNamespace(name=f"models/{model}")

    monkeypatch.setattr("google.genai.Client", lambda **kwargs: SimpleNamespace(models=Models()))

    result = await ai_models.check_ai_models()

    assert result == {"VISION_MODEL": True, "CLASSIFIER_MODEL": False}
    assert "ai_model_unavailable var=CLASSIFIER_MODEL model=gemini-2.0-flash" in caplog.text
    assert "synthetic-test-key" not in caplog.text
