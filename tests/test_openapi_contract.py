"""
#54: operationId legível e único (nome da função da rota) e export do contrato.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from app.main import app

ROOT = Path(__file__).resolve().parent.parent


def _operation_ids(spec) -> list[str]:
    return [
        op["operationId"]
        for item in spec["paths"].values()
        for op in item.values()
        if isinstance(op, dict) and "operationId" in op
    ]


def test_operation_ids_sao_unicos_e_legiveis():
    ids = _operation_ids(app.openapi())
    duplicated = sorted({i for i in ids if ids.count(i) > 1})
    # duas rotas com a mesma função geram o mesmo nome no cliente do app
    assert not duplicated, f"Renomeie as funções das rotas: {duplicated}"
    assert "login" in ids
    assert not [i for i in ids if "_api_v1_" in i]


def test_export_gera_o_contrato_completo(tmp_path):
    output = tmp_path / "openapi.json"
    env = {**os.environ, "ENABLED_MODULES": "mvp"}

    subprocess.run(
        [sys.executable, "scripts/export_openapi.py", str(output)],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
    )

    spec = json.loads(output.read_text(encoding="utf-8"))
    assert spec["info"]["title"] == "Koin API"
    # módulo fora do MVP também entra: o contrato não depende do ambiente que exporta
    assert any(path.startswith("/api/v1/grocery") for path in spec["paths"])
