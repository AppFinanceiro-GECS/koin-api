# Modulo Chat

## Descricao
Modulo responsavel pelo assistente financeiro IA. Utiliza um agente inteligente que analisa os dados financeiros do usuario e fornece recomendacoes personalizadas, respondendo perguntas sobre financas pessoais.

## Responsabilidades
- Processamento de mensagens do usuario
- Analise de dados financeiros (transacoes, dividas, metas, orcamentos)
- Geracao de recomendacoes personalizadas
- Manutencao de contexto da conversa
- Sugestoes de perguntas baseadas nos dados

## Estrutura
```
chat/
├── __init__.py
├── schemas/
│   └── chat.py           # ChatMessage, ChatRequest, ChatResponse, ConversationSummary
├── services/
│   └── financial_agent_service.py # FinancialAgentService (processamento, IA)
└── routers/
    └── chat.py           # Endpoints do chat
```

## Dependencias
- **Models**: `Transaction`, `Debt`, `Goal`, `Budget`, `Category`, `Account`
- **Outros Modulos**: `analytics`, `debts`, `goals`, `budgets` (para contexto)
- **Core**: `deps` (CurrentUser, DbSession)

## Endpoints

### Router Chat (`/chat`)
| Metodo | Rota | Descricao |
|--------|------|-----------|
| POST | `` | Envia mensagem para o agente IA |
| GET | `/suggestions` | Retorna sugestoes de perguntas iniciais |

## Uso
```python
from app.modules.chat import (
    router,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ConversationSummary,
    MessageRole,
    FinancialAgentService,
)
```

## Roles de Mensagem
- `user`: Mensagem do usuario
- `assistant`: Resposta do agente
- `system`: Mensagem do sistema (contexto)

## Funcionalidades do Agente
- Responde perguntas sobre gastos e receitas
- Analisa padroes de consumo
- Sugere estrategias de economia
- Acompanha progresso de metas
- Recomenda estrategias de quitacao de dividas
- Fornece insights sobre o orcamento

## Exemplo de Uso
```
Usuario: "Quanto gastei com alimentacao esse mes?"
Agente: "Voce gastou R$ 1.234,56 com alimentacao este mes,
        distribuidos em 15 transacoes. Isso representa
        25% do seu orcamento de R$ 5.000 para esta categoria."
```
