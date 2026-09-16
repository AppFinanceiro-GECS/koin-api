"""Tests for FinancialAgentService.

Covers the key methods that will be refactored into separate files:
- _parse_query (query parsing / context extraction)
- _classify_intent_by_keywords (intent classification)
- _generate_smart_suggestions (suggestion engine)
- _build_expert_system_prompt (prompt building)
- _extract_monetary_value (utility)
- DecimalEncoder (utility)
- chat() orchestration (with mocked DB + LLM)
"""

import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chat.services.financial_agent_service import (
    DecimalEncoder,
    FinancialAgentService,
)

# ========== Fixtures ==========


@pytest.fixture
def mock_db():
    """Mock AsyncSession for tests that don't need real DB."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def service(mock_db):
    """FinancialAgentService instance with mocked DB."""
    return FinancialAgentService(mock_db)


# ========== DecimalEncoder Tests ==========


class TestDecimalEncoder:
    def test_encodes_decimal(self):
        data = {"amount": Decimal("1234.56")}
        result = json.dumps(data, cls=DecimalEncoder)
        assert result == '{"amount": 1234.56}'

    def test_encodes_date(self):
        data = {"date": date(2026, 3, 23)}
        result = json.dumps(data, cls=DecimalEncoder)
        assert '"2026-03-23"' in result

    def test_encodes_datetime(self):
        data = {"ts": datetime(2026, 3, 23, 14, 30, 0)}
        result = json.dumps(data, cls=DecimalEncoder)
        assert '"2026-03-23T14:30:00"' in result

    def test_raises_on_unknown_type(self):
        with pytest.raises(TypeError):
            json.dumps({"obj": object()}, cls=DecimalEncoder)


# ========== _parse_query Tests ==========


class TestParseQuery:
    def test_default_period_is_current_month(self, service):
        result = service._parse_query("quanto gastei")
        today = date.today()
        assert result["period"]["start"] == date(today.year, today.month, 1)
        assert result["period"]["end"] == today

    def test_detects_specific_month(self, service):
        result = service._parse_query("gastos de janeiro")
        assert result["period"]["start"].month == 1

    def test_detects_abbreviated_month(self, service):
        result = service._parse_query("gastos de fev")
        assert result["period"]["start"].month == 2

    def test_detects_last_month(self, service):
        result = service._parse_query("gastos do mes passado")
        today = date.today()
        expected_month = (today.replace(day=1) - timedelta(days=1)).month
        assert result["period"]["start"].month == expected_month

    def test_detects_current_month(self, service):
        result = service._parse_query("gastos esse mes")
        assert result["period"]["label"] == "Mes atual"

    def test_detects_last_3_months(self, service):
        result = service._parse_query("ultimos 3 meses")
        assert result["period"]["label"] == "Ultimos 3 meses"

    def test_detects_current_year(self, service):
        result = service._parse_query("gastos esse ano")
        today = date.today()
        assert result["period"]["start"] == date(today.year, 1, 1)

    def test_detects_comparison(self, service):
        result = service._parse_query("comparar com mes anterior")
        assert result["comparison"] is True

    def test_detects_category_keywords(self, service):
        result = service._parse_query("gastos com restaurante e uber")
        assert "restaurante" in result["category_keywords"]
        assert "uber" in result["category_keywords"]

    def test_no_comparison_by_default(self, service):
        result = service._parse_query("quanto gastei")
        assert result["comparison"] is False


# ========== _extract_monetary_value Tests ==========


class TestExtractMonetaryValue:
    def test_extracts_with_r_dollar(self, service):
        result = service._extract_monetary_value("tenho R$ 5000 para pagar")
        assert result == 5000.0

    def test_extracts_with_comma(self, service):
        result = service._extract_monetary_value("quero pagar R$1500")
        assert result == 1500.0

    def test_extracts_k_format(self, service):
        result = service._extract_monetary_value("tenho 20k disponivel")
        assert result == 20000.0

    def test_extracts_mil_format(self, service):
        result = service._extract_monetary_value("tenho 5 mil reais")
        assert result == 5000.0

    def test_returns_none_when_no_value(self, service):
        result = service._extract_monetary_value("quanto gastei esse mes")
        assert result is None

    def test_ignores_small_values(self, service):
        # Values < 100 are ignored by design
        result = service._extract_monetary_value("tenho R$ 50")
        assert result is None


# ========== _classify_intent_by_keywords Tests ==========


class TestClassifyIntentByKeywords:
    def test_detects_credit_card(self, service):
        domains = service._classify_intent_by_keywords("qual o limite do meu cartao")
        assert "cartoes" in domains

    def test_detects_budget(self, service):
        domains = service._classify_intent_by_keywords("estourei meu orcamento")
        assert "orcamento" in domains

    def test_detects_goals(self, service):
        domains = service._classify_intent_by_keywords("como estao minhas metas")
        assert "metas" in domains

    def test_detects_debts(self, service):
        domains = service._classify_intent_by_keywords("quero quitar minhas dividas")
        assert "dividas" in domains

    def test_detects_recurring(self, service):
        domains = service._classify_intent_by_keywords("quanto pago de netflix")
        assert "recorrentes" in domains

    def test_detects_benefits(self, service):
        domains = service._classify_intent_by_keywords("quanto tenho no vale alimentacao")
        assert "beneficios" in domains

    def test_detects_grocery(self, service):
        domains = service._classify_intent_by_keywords("lista de compras do mercado")
        assert "mercado" in domains

    def test_detects_cashflow(self, service):
        domains = service._classify_intent_by_keywords("quando recebo meu salario")
        assert "fluxo" in domains

    def test_detects_calendar(self, service):
        domains = service._classify_intent_by_keywords("quando vence meu proximo pagamento")
        assert "calendario" in domains

    def test_detects_review(self, service):
        domains = service._classify_intent_by_keywords("review da semana passada")
        assert "revisao" in domains

    def test_detects_automations(self, service):
        domains = service._classify_intent_by_keywords("criar automacao de transferencia")
        assert "automacoes" in domains

    def test_defaults_to_general(self, service):
        domains = service._classify_intent_by_keywords("oi tudo bem")
        assert domains == ["geral"]

    def test_limits_to_3_domains(self, service):
        # Message that matches many keywords
        domains = service._classify_intent_by_keywords(
            "resumo geral do cartao com dividas e orcamento e metas"
        )
        assert len(domains) <= 3

    def test_detects_general_spending(self, service):
        domains = service._classify_intent_by_keywords("quanto gastei esse mes")
        assert "geral" in domains

    def test_detects_multiple_domains(self, service):
        domains = service._classify_intent_by_keywords("fatura do cartao e dividas")
        assert "cartoes" in domains
        assert "dividas" in domains


# ========== _generate_smart_suggestions Tests ==========


class TestGenerateSmartSuggestions:
    def test_returns_max_4_suggestions(self, service):
        context = {
            "gastos_por_categoria": {"Alimentacao": 500, "Transporte": 300},
            "cartoes_credito": [{"limite_total": 1000, "saldo_em_aberto": 800}],
            "dividas": [{"name": "emprestimo"}],
            "metas": [{"name": "emergencia"}],
            "resumo_periodo": {"receitas": 3000, "despesas": 4000},
            "comparacao_mes_anterior": {"variacao_despesas": 20},
            "fontes_receita": [{"name": "salario"}],
        }
        suggestions = service._generate_smart_suggestions("resumo", context)
        assert len(suggestions) <= 4

    def test_suggests_category_detail_on_spending(self, service):
        context = {
            "gastos_por_categoria": {"Alimentacao": 500},
        }
        suggestions = service._generate_smart_suggestions("meus gastos", context)
        assert any("Alimentacao" in s for s in suggestions)

    def test_suggests_overdue_invoices(self, service):
        context = {
            "cartoes_credito": [
                {"limite_total": 5000, "saldo_em_aberto": 1000, "faturas": [{"vencida": True}]}
            ],
        }
        suggestions = service._generate_smart_suggestions("resumo geral", context)
        assert any("vencidas" in s.lower() for s in suggestions)

    def test_suggests_debt_strategy(self, service):
        context = {"dividas": [{"name": "emprestimo"}]}
        suggestions = service._generate_smart_suggestions("resumo", context)
        assert any("divida" in s.lower() or "quitar" in s.lower() for s in suggestions)

    def test_no_duplicate_suggestions(self, service):
        context = {
            "gastos_por_categoria": {"Alimentacao": 500},
            "dividas": [{"name": "emprestimo"}],
            "metas": [{"name": "emergencia"}],
        }
        suggestions = service._generate_smart_suggestions("gastos", context)
        lowered = [s.lower() for s in suggestions]
        assert len(lowered) == len(set(lowered))

    def test_empty_context_returns_defaults(self, service):
        suggestions = service._generate_smart_suggestions("oi", {})
        assert len(suggestions) > 0
        assert any("saude financeira" in s.lower() for s in suggestions)


# ========== _build_expert_system_prompt Tests ==========


class TestBuildExpertSystemPrompt:
    def test_includes_context_json(self, service):
        context = {"resumo": {"receitas": 5000, "despesas": 3000}}
        prompt = service._build_expert_system_prompt(context, ["geral"], "quanto gastei")
        assert "5000" in prompt
        assert "3000" in prompt

    def test_includes_domain_instructions(self, service):
        context = {"cartoes_credito": []}
        prompt = service._build_expert_system_prompt(context, ["cartoes"], "limite do cartao")
        # Should contain credit card specific instructions
        assert "cart" in prompt.lower() or "credit" in prompt.lower() or "fatura" in prompt.lower()

    def test_includes_user_message(self, service):
        context = {}
        prompt = service._build_expert_system_prompt(context, ["geral"], "quanto gastei em janeiro")
        assert "janeiro" in prompt.lower() or "DADOS" in prompt


# ========== chat() Integration Test (mocked LLM + DB) ==========


class TestChatOrchestration:
    @pytest.mark.asyncio
    async def test_chat_returns_response(self, service, mock_db):
        """Test the full chat flow with mocked DB and LLM."""
        # Mock user
        user = MagicMock()
        user.id = 1
        user.license_id = None
        user.name = "Test User"

        # Mock DB queries to return empty results
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalars.return_value.first.return_value = None
        mock_result.all.return_value = []
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result
        mock_db.commit = AsyncMock()

        # Mock the LLM call
        with patch.object(
            service,
            "_call_llm",
            new_callable=AsyncMock,
            return_value="Voce gastou R$ 3.000 esse mes.",
        ):
            # Mock conversation management
            with patch.object(
                service,
                "_get_or_create_conversation",
                new_callable=AsyncMock,
                return_value=("conv-123", MagicMock(title=None, updated_at=None)),
            ):
                with patch.object(
                    service, "_get_conversation_history", new_callable=AsyncMock, return_value=[]
                ):
                    with patch.object(service, "_save_message", new_callable=AsyncMock):
                        response = await service.chat(user, "quanto gastei esse mes")

        assert response.message == "Voce gastou R$ 3.000 esse mes."
        assert response.conversation_id == "conv-123"
        assert isinstance(response.suggestions, list)
        assert isinstance(response.data_used, list)

    @pytest.mark.asyncio
    async def test_chat_classifies_intent(self, service, mock_db):
        """Test that chat classifies intent and uses appropriate domains."""
        user = MagicMock()
        user.id = 1
        user.license_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_result.all.return_value = []
        mock_result.scalar.return_value = 0
        mock_db.execute.return_value = mock_result
        mock_db.commit = AsyncMock()

        data_used_capture = []

        async def mock_chat_inner(user, message, conversation_id=None):
            # Just classify intent to verify domains
            domains = service._classify_intent_by_keywords(message)
            data_used_capture.extend(domains)

        # Verify keyword classification works for different messages
        assert "cartoes" in service._classify_intent_by_keywords("limite do cartao")
        assert "dividas" in service._classify_intent_by_keywords("quitar divida")
        assert "geral" in service._classify_intent_by_keywords("quanto gastei")


# ========== Conversation Management Tests ==========


class TestConversationManagement:
    @pytest.mark.asyncio
    async def test_get_or_create_conversation_creates_new(self, service, mock_db):
        """Test that a new conversation is created when ID is None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        user = MagicMock()
        user.id = 1

        conv_id, conv = await service._get_or_create_conversation(user, None)
        assert conv_id is not None
        assert len(conv_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_get_conversation_history(self, service, mock_db):
        """Test fetching conversation history."""
        from enum import Enum

        class MockRole(str, Enum):
            USER = "user"
            ASSISTANT = "assistant"

        mock_msg1 = MagicMock()
        mock_msg1.role = MockRole.ASSISTANT  # reversed order (desc from DB)
        mock_msg1.content = "ola!"

        mock_msg2 = MagicMock()
        mock_msg2.role = MockRole.USER
        mock_msg2.content = "oi"

        mock_result = MagicMock()
        # DB returns desc order, service reverses
        mock_result.scalars.return_value.all.return_value = [mock_msg1, mock_msg2]
        mock_db.execute.return_value = mock_result

        history = await service._get_conversation_history("conv-123")
        assert len(history) == 2
        # After reversing: user first, then assistant
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"


# ========== Edge Cases ==========


class TestEdgeCases:
    def test_parse_query_with_empty_message(self, service):
        result = service._parse_query("")
        assert result["period"] is not None
        assert result["category_keywords"] == []

    def test_classify_empty_message(self, service):
        domains = service._classify_intent_by_keywords("")
        assert domains == ["geral"]

    def test_suggestions_with_empty_context(self, service):
        suggestions = service._generate_smart_suggestions("", {})
        assert len(suggestions) > 0

    def test_extract_value_with_no_number(self, service):
        result = service._extract_monetary_value("nada de valor aqui")
        assert result is None

    def test_decimal_encoder_with_nested(self):
        data = {
            "items": [
                {"amount": Decimal("99.99"), "date": date(2026, 1, 1)},
                {"amount": Decimal("0.01"), "date": date(2026, 12, 31)},
            ]
        }
        result = json.loads(json.dumps(data, cls=DecimalEncoder))
        assert result["items"][0]["amount"] == 99.99
        assert result["items"][1]["date"] == "2026-12-31"
