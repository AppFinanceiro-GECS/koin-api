"""
O nome do modelo Gemini vive só em app/core/config.py (VISION_MODEL, CLASSIFIER_MODEL, CHAT_MODEL).
Modelo fixo no código fica para trás quando o Google desliga uma família (a 2.0 saiu em 01/06/2026).
"""

import re
from pathlib import Path

from app.core.config import Settings

APP_DIR = Path(__file__).resolve().parent.parent / "app"
CONFIG_FILE = APP_DIR / "core" / "config.py"
MODEL_LITERAL = re.compile(r"""["'/]gemini-\d""")


def test_nenhum_modelo_gemini_fixo_fora_do_config():
    ofensores = [
        f"{path.relative_to(APP_DIR.parent)}:{n}"
        for path in APP_DIR.rglob("*.py")
        if path != CONFIG_FILE
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if MODEL_LITERAL.search(line)
    ]
    assert not ofensores, f"Use settings.vision_model/classifier_model: {ofensores}"


def test_modelos_padrao_nao_sao_da_familia_desligada():
    settings = Settings(_env_file=None)
    for model in (settings.vision_model, settings.classifier_model):
        assert not model.startswith("gemini-2.0"), model


def test_modelos_configuraveis_por_ambiente(monkeypatch):
    monkeypatch.setenv("VISION_MODEL", "gemini-x-teste")
    monkeypatch.setenv("CLASSIFIER_MODEL", "gemini-y-teste")
    settings = Settings(_env_file=None)
    assert settings.vision_model == "gemini-x-teste"
    assert settings.classifier_model == "gemini-y-teste"
