"""Testes para detecção de duplicatas em transações individuais"""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.transaction import Transaction
from app.modules.installments.services.duplicate_detection_service import DuplicateDetectionService


@pytest.fixture
def mock_db():
    """Mock da sessão do banco de dados"""
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    """Instância do serviço de detecção de duplicatas"""
    return DuplicateDetectionService(mock_db)


def create_mock_transaction(
    tx_id: int,
    description: str,
    amount: float,
    tx_date: date,
    installment_series_id: int | None = None,
    installment_number: int | None = None,
    installment_total: int | None = None,
    created_at: datetime | None = None,
) -> Transaction:
    """Cria uma transação mock para testes"""
    tx = Mock(spec=Transaction)
    tx.id = tx_id
    tx.description = description
    tx.amount = Decimal(str(amount))
    tx.date = tx_date
    tx.installment_series_id = installment_series_id
    tx.installment_number = installment_number
    tx.installment_total = installment_total
    tx.created_at = created_at or datetime.now(UTC)
    return tx


class TestTransactionDuplicateDetection:
    """Testes para detecção de duplicatas em transações"""

    def test_detects_identical_values_similar_descriptions(self, service):
        """Detecta transações com valores idênticos e descrições similares"""
        tx_a = create_mock_transaction(
            tx_id=1,
            description="cartao protegido",
            amount=14.50,
            tx_date=date(2026, 1, 22),
        )
        tx_b = create_mock_transaction(
            tx_id=2,
            description="Seg. Cartão Protegido com Piv. jan/26",
            amount=14.50,
            tx_date=date(2026, 1, 20),  # 2 dias de diferença (dentro dos 3 dias)
        )

        is_duplicate, score = service._check_transaction_duplicate(tx_a, tx_b)

        assert is_duplicate is True, "Deveria detectar como duplicata"
        assert score >= 0.80, f"Score deveria ser >= 80%, foi {score:.2%}"

    def test_blocks_very_different_amounts(self, service):
        """Bloqueia transações com valores muito diferentes"""
        tx_a = create_mock_transaction(
            tx_id=1,
            description="CASAS BECKER",
            amount=47.61,
            tx_date=date(2026, 1, 22),
        )
        tx_b = create_mock_transaction(
            tx_id=2,
            description="CASAS BECKER",
            amount=119.04,
            tx_date=date(2026, 1, 22),
        )

        is_duplicate, score = service._check_transaction_duplicate(tx_a, tx_b)

        assert is_duplicate is False, "Valores muito diferentes não devem ser duplicata"
        assert score == 0.0

    def test_blocks_very_different_dates(self, service):
        """Bloqueia transações com datas muito distantes"""
        tx_a = create_mock_transaction(
            tx_id=1,
            description="Netflix",
            amount=49.90,
            tx_date=date(2026, 1, 1),
        )
        tx_b = create_mock_transaction(
            tx_id=2,
            description="Netflix",
            amount=49.90,
            tx_date=date(2026, 1, 10),  # 9 dias depois
        )

        is_duplicate, score = service._check_transaction_duplicate(tx_a, tx_b)

        assert is_duplicate is False, "Datas muito distantes (>3 dias) não devem ser duplicata"
        assert score == 0.0

    def test_allows_small_amount_difference(self, service):
        """Permite pequena diferença de valores (arredondamento)"""
        tx_a = create_mock_transaction(
            tx_id=1,
            description="Netflix",
            amount=49.90,
            tx_date=date(2026, 1, 22),
        )
        tx_b = create_mock_transaction(
            tx_id=2,
            description="Netflix",
            amount=49.94,  # Diff = R$ 0,04
            tx_date=date(2026, 1, 22),
        )

        is_duplicate, score = service._check_transaction_duplicate(tx_a, tx_b)

        assert is_duplicate is True, "Pequena diferença de R$ 0,04 deveria ser permitida"
        assert score >= 0.80

    def test_blocks_different_descriptions(self, service):
        """Bloqueia transações com descrições muito diferentes"""
        tx_a = create_mock_transaction(
            tx_id=1,
            description="Netflix",
            amount=49.90,
            tx_date=date(2026, 1, 22),
        )
        tx_b = create_mock_transaction(
            tx_id=2,
            description="Spotify",
            amount=49.90,
            tx_date=date(2026, 1, 22),
        )

        is_duplicate, score = service._check_transaction_duplicate(tx_a, tx_b)

        assert is_duplicate is False, "Descrições muito diferentes não devem ser duplicata"
        assert score == 0.0

    def test_suggests_delete_standalone_when_comparing_with_installment(self, service):
        """Sugere deletar transação avulsa quando comparando com série"""
        tx_installment = create_mock_transaction(
            tx_id=1,
            description="cartao protegido",
            amount=14.50,
            tx_date=date(2026, 1, 22),
            installment_series_id=100,  # Faz parte de uma série
        )
        tx_standalone = create_mock_transaction(
            tx_id=2,
            description="Seg. Cartão Protegido",
            amount=14.50,
            tx_date=date(2026, 1, 5),
            installment_series_id=None,  # Transação avulsa
        )

        action = service._suggest_duplicate_action(tx_installment, tx_standalone)

        assert action == "delete_b", "Deveria sugerir deletar a transação avulsa (tx_b)"

    def test_suggests_delete_newer_when_both_standalone(self, service):
        """Sugere deletar a mais recente quando ambas são avulsas"""
        tx_older = create_mock_transaction(
            tx_id=1,
            description="Netflix",
            amount=49.90,
            tx_date=date(2026, 1, 22),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        tx_newer = create_mock_transaction(
            tx_id=2,
            description="Netflix",
            amount=49.90,
            tx_date=date(2026, 1, 23),
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
        )

        action = service._suggest_duplicate_action(tx_older, tx_newer)

        assert action == "delete_b", "Deveria sugerir deletar a mais recente (tx_b)"


class TestRealWorldScenarios:
    """Testes com cenários reais"""

    def test_cartao_protegido_duplicate(self, service):
        """
        Cenário real da fatura 456:
        - "cartao protegido" R$ 14,50 (parcela 1/9)
        - "Seg. Cartão Protegido com Piv. jan/26" R$ 14,50 (avulsa)

        NOTA: Ajustamos as datas para estarem dentro dos 3 dias de diferença
        (critério de hard rule). No mundo real, podem estar mais distantes,
        mas para este teste validamos a lógica de detecção.
        """
        tx_installment = create_mock_transaction(
            tx_id=3481,
            description="cartao protegido",
            amount=14.50,
            tx_date=date(2026, 1, 22),
            installment_series_id=999,
        )
        tx_standalone = create_mock_transaction(
            tx_id=3899,
            description="Seg. Cartão Protegido com Piv. jan/26",
            amount=14.50,
            tx_date=date(2026, 1, 20),  # 2 dias de diferença (dentro dos 3 dias)
            installment_series_id=None,
        )

        is_duplicate, score = service._check_transaction_duplicate(tx_installment, tx_standalone)

        assert is_duplicate is True, "Deveria detectar como duplicata"
        assert score >= 0.80, f"Score deveria ser alto, foi {score:.2%}"

        # Verificar sugestão de ação
        action = service._suggest_duplicate_action(tx_installment, tx_standalone)
        assert action == "delete_b", "Deveria sugerir deletar a transação avulsa"

    def test_netflix_different_months_not_duplicate(self, service):
        """Netflix de meses diferentes não são duplicatas"""
        tx_jan = create_mock_transaction(
            tx_id=1,
            description="Netflix Jan/26",
            amount=49.90,
            tx_date=date(2026, 1, 15),
        )
        tx_feb = create_mock_transaction(
            tx_id=2,
            description="Netflix Fev/26",
            amount=49.90,
            tx_date=date(2026, 2, 15),  # 31 dias depois
        )

        is_duplicate, score = service._check_transaction_duplicate(tx_jan, tx_feb)

        assert is_duplicate is False, "Meses diferentes com >3 dias não são duplicata"

    def test_same_merchant_different_amounts_not_duplicate(self, service):
        """Mesmo merchant com valores diferentes não são duplicatas"""
        tx_a = create_mock_transaction(
            tx_id=1,
            description="Mercado Livre - Produto A",
            amount=100.00,
            tx_date=date(2026, 1, 22),
        )
        tx_b = create_mock_transaction(
            tx_id=2,
            description="Mercado Livre - Produto B",
            amount=150.00,
            tx_date=date(2026, 1, 22),
        )

        is_duplicate, score = service._check_transaction_duplicate(tx_a, tx_b)

        assert is_duplicate is False, "Valores diferentes (R$ 50 diff) não são duplicata"


class TestEdgeCases:
    """Testes de casos extremos"""

    def test_handles_none_amounts(self, service):
        """Lida com valores None"""
        tx_a = create_mock_transaction(
            tx_id=1,
            description="Test",
            amount=100.00,
            tx_date=date(2026, 1, 22),
        )
        tx_b = create_mock_transaction(
            tx_id=2,
            description="Test",
            amount=100.00,
            tx_date=date(2026, 1, 22),
        )
        tx_b.amount = None

        is_duplicate, score = service._check_transaction_duplicate(tx_a, tx_b)

        assert is_duplicate is False
        assert score == 0.0

    def test_handles_none_descriptions(self, service):
        """Lida com descrições None"""
        tx_a = create_mock_transaction(
            tx_id=1,
            description="Test",
            amount=100.00,
            tx_date=date(2026, 1, 22),
        )
        tx_b = create_mock_transaction(
            tx_id=2,
            description="Test",
            amount=100.00,
            tx_date=date(2026, 1, 22),
        )
        tx_b.description = None

        is_duplicate, score = service._check_transaction_duplicate(tx_a, tx_b)

        assert is_duplicate is False
        assert score == 0.0

    def test_handles_none_dates(self, service):
        """Lida com datas None"""
        tx_a = create_mock_transaction(
            tx_id=1,
            description="Test",
            amount=100.00,
            tx_date=date(2026, 1, 22),
        )
        tx_b = create_mock_transaction(
            tx_id=2,
            description="Test",
            amount=100.00,
            tx_date=date(2026, 1, 22),
        )
        tx_b.date = None

        is_duplicate, score = service._check_transaction_duplicate(tx_a, tx_b)

        assert is_duplicate is False
        assert score == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
