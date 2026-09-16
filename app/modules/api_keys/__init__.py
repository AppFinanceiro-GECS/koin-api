"""
Módulo de API Keys para acesso externo (MCP, integrações).

Permite que usuários gerem e gerenciem chaves de API pessoais
para acessar seus dados financeiros via ferramentas externas.
"""

from .routers.api_keys import router

__all__ = ["router"]
