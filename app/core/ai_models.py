"""
Confere, na inicialização, se os modelos Gemini configurados existem para a chave.

Modelo desligado ou com nome errado só aparecia no primeiro upload, como documento
`failed`. Aqui vira um erro claro no log do deploy, sem impedir a API de subir.
"""

import asyncio
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

CHECK_TIMEOUT_SECONDS = 30


def configured_models() -> dict[str, str]:
    """Variável de ambiente → modelo configurado"""
    models = {
        "VISION_MODEL": settings.vision_model,
        "CLASSIFIER_MODEL": settings.classifier_model,
    }
    if settings.vision_model_fallback:
        models["VISION_MODEL_FALLBACK"] = settings.vision_model_fallback
    return models


def _check_models_sync() -> dict[str, bool]:
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=settings.google_api_key,
        http_options=types.HttpOptions(timeout=10_000),  # ms
    )
    result = {}
    for var, model in configured_models().items():
        try:
            client.models.get(model=model)
            result[var] = True
            logger.info("ai_model_ok var=%s model=%s", var, model)
        except Exception as e:
            result[var] = False
            logger.error(
                "ai_model_unavailable var=%s model=%s error_type=%s detail=%s",
                var,
                model,
                type(e).__name__,
                str(e)[:200],
            )
    return result


async def check_ai_models() -> dict[str, bool] | None:
    """Valida os modelos; None quando não há chave do Google para validar ou quando o provedor não é Google."""
    if settings.vision_provider != "google" or not settings.google_api_key:
        logger.info("ai_model_check_skipped reason=provider_not_google_or_no_key")
        return None
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_check_models_sync), timeout=CHECK_TIMEOUT_SECONDS
        )
    except Exception as e:
        logger.error("ai_model_check_failed error_type=%s", type(e).__name__)
        return None
