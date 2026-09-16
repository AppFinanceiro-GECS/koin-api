"""
Módulo MCP (Model Context Protocol) para acesso externo via Claude Code.

Endpoints otimizados para consultas de dados financeiros,
autenticados via API Key (header X-API-Key).
"""

from .routers.mcp import router

__all__ = ["router"]
