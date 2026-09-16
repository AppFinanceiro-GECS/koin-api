"""Router para o Agente IA Financeiro"""

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.modules.chat.schemas.chat import ChatRequest, ChatResponse
from app.modules.chat.services.financial_agent_service import FinancialAgentService

router = APIRouter()


@router.post("", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Envia mensagem para o Agente IA Financeiro.

    O agente analisa seus dados financeiros (transacoes, dividas, metas, orcamentos)
    e fornece recomendacoes personalizadas.

    - **message**: Sua pergunta ou mensagem para o agente
    - **conversation_id**: ID da conversa (opcional, para continuar uma conversa existente)
    """
    service = FinancialAgentService(db)
    return await service.chat(current_user, request.message, request.conversation_id)


@router.get("/suggestions")
async def get_suggestions(
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Retorna sugestoes de perguntas iniciais baseadas nos dados do usuario.
    """
    service = FinancialAgentService(db)
    # Usa periodo vazio (sera preenchido com mes atual pelo servico)
    query_context = {"period": {}}
    context = await service.get_suggestions_context(current_user, query_context)
    suggestions = service.generate_smart_suggestions("", context)

    return {
        "suggestions": suggestions,
        "welcome_message": "Ola! Sou o Fin, seu assistente financeiro pessoal. Como posso ajudar voce hoje?",
    }
