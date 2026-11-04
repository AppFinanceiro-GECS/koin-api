#!/usr/bin/env python3
"""
Exporta o contrato OpenAPI da API para um arquivo (#54), sem subir servidor nem banco.

O CI publica o resultado como artefato de cada build e anexa à release da prod; o
koin-app gera os tipos TypeScript a partir dele (ou do /openapi.json da hml).

Uso: python scripts/export_openapi.py [saida.json]   (padrão: openapi.json)
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Contrato completo, independente do ENABLED_MODULES do ambiente que exporta
os.environ["ENABLED_MODULES"] = "all"
os.environ.setdefault("SECRET_KEY", "export-openapi")


def main() -> int:
    from app.main import app

    output = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"
    with open(output, "w", encoding="utf-8") as f:
        json.dump(app.openapi(), f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    print(f"{output}: {len(app.openapi()['paths'])} caminhos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
