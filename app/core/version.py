"""
Versão da API num lugar só (#41): `version` do pyproject.toml. O commit vem do build
da imagem (GIT_COMMIT); fora do Docker fica "dev".
"""

import os
import tomllib
from pathlib import Path

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _read_version() -> str:
    try:
        return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "0.0.0"


API_VERSION = _read_version()
COMMIT = os.getenv("GIT_COMMIT") or "dev"
