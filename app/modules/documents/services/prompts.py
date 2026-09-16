"""Prompts para extracao de documentos financeiros.

Prompts são carregados de arquivos .md em documents/prompts/ com cache global.
Para iterar em prompts, edite os .md sem alterar código Python.
"""

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


@lru_cache(maxsize=32)
def _load_prompt_file(filepath: str) -> str:
    """Load prompt from file with LRU cache (persistent across requests)."""
    path = Path(filepath)
    if path.exists():
        return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Prompt file not found: {filepath}")


def load_prompt(name: str) -> str:
    """Load a prompt by name from the prompts directory.

    Args:
        name: Filename (with or without .md extension)

    Returns:
        Prompt content as string
    """
    if not name.endswith(".md"):
        name = f"{name}.md"
    return _load_prompt_file(str(PROMPTS_DIR / name))


def clear_prompt_cache():
    """Clear the prompt cache (useful for hot-reload in dev)."""
    _load_prompt_file.cache_clear()


# Backward compatibility: EXTRACTION_PROMPT loaded from file
try:
    EXTRACTION_PROMPT = load_prompt("extraction_main")
except FileNotFoundError:
    # Fallback: try fatura_cartao_focused (existing prompt file)
    try:
        EXTRACTION_PROMPT = load_prompt("fatura_cartao_focused")
    except FileNotFoundError:
        EXTRACTION_PROMPT = "Extract financial data from this document."
