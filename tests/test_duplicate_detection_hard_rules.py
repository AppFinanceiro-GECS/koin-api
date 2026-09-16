"""Testes para hard rules de detecção de duplicatas"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.installment import InstallmentSeries, InstallmentSeriesStatus
from app.modules.installments.services.duplicate_detection_service import DuplicateDetectionService


@pytest.fixture
def mock_db():
    """Mock da sessão do banco de dados"""
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    """Instância do serviço de detecção de duplicatas"""
    return DuplicateDetectionService(mock_db)


def create_mock_series(
    series_id: int,
    merchant_name: str,
    amount: float,
    installment_count: int,
    credit_card_id: int | None = None,
) -> InstallmentSeries:
    """Cria uma série mock para testes"""
    series = Mock(spec=InstallmentSeries)
    series.id = series_id
    series.merchant_name = merchant_name
    series.installment_amount = Decimal(str(amount))
    series.installment_count = installment_count
    series.credit_card_id = credit_card_id
    series.status = InstallmentSeriesStatus.ACTIVE
    series.created_at = datetime.now(UTC)
    return series


class TestHardRuleAmountDifference:
    """Testes para HARD RULE 1: Diferença absoluta de valor"""

    def test_blocks_large_amount_difference(self, service):
        """Bloqueia séries com valores muito diferentes (R$ 47,61 vs R$ 119,04)"""
        # Exemplo real do bug: CASAS BECKER
        series_a = create_mock_series(
            series_id=1, merchant_name="CASAS BECKER", amount=47.61, installment_count=21
        )
        series_b = create_mock_series(
            series_id=2, merchant_name="CASAS BECKER", amount=119.04, installment_count=21
        )

        score = service._calculate_similarity_score(series_a, series_b)

        # Deve retornar 0.0 (bloqueado pela hard rule)
        assert score == 0.0, (
            f"Deveria bloquear valores muito diferentes (diff=R$ 71,43), score={score}"
        )

    def test_allows_identical_amounts(self, service):
        """Permite valores idênticos"""
        series_a = create_mock_series(
            series_id=1, merchant_name="NETFLIX", amount=49.90, installment_count=12
        )
        series_b = create_mock_series(
            series_id=2, merchant_name="NETFLIX", amount=49.90, installment_count=12
        )

        score = service._calculate_similarity_score(series_a, series_b)

        # Deve ter score alto (não bloqueado)
        assert score > 0.5, f"Valores idênticos devem ter score alto, score={score}"

    def test_allows_small_difference_within_threshold(self, service):
        """Permite diferença menor que R$ 0,05"""
        series_a = create_mock_series(
            series_id=1, merchant_name="NETFLIX", amount=49.90, installment_count=12
        )
        series_b = create_mock_series(
            series_id=2,
            merchant_name="NETFLIX",
            amount=49.94,  # Diff = R$ 0,04 (< R$ 0,05)
            installment_count=12,
        )

        score = service._calculate_similarity_score(series_a, series_b)

        # Deve ter score alto (dentro do threshold)
        assert score > 0.5, f"Diferença de R$ 0,04 deve ser permitida, score={score}"

    def test_blocks_small_difference_above_threshold(self, service):
        """Bloqueia diferença maior que R$ 0,05"""
        series_a = create_mock_series(
            series_id=1, merchant_name="NETFLIX", amount=49.90, installment_count=12
        )
        series_b = create_mock_series(
            series_id=2,
            merchant_name="NETFLIX",
            amount=49.96,  # Diff = R$ 0,06 (> R$ 0,05)
            installment_count=12,
        )

        score = service._calculate_similarity_score(series_a, series_b)

        # Deve retornar 0.0 (bloqueado)
        assert score == 0.0, f"Diferença de R$ 0,06 (> R$ 0,05) deve ser bloqueada, score={score}"


class TestHardRuleNameOverlap:
    """Testes para HARD RULE 2: Sobreposição mínima de nome (80%)"""

    def test_blocks_different_merchants(self, service):
        """Bloqueia merchants completamente diferentes"""
        series_a = create_mock_series(
            series_id=1, merchant_name="STEAM", amount=100.00, installment_count=12
        )
        series_b = create_mock_series(
            series_id=2, merchant_name="NETFLIX", amount=100.00, installment_count=12
        )

        score = service._calculate_similarity_score(series_a, series_b)

        # Deve retornar 0.0 (bloqueado por nome)
        assert score == 0.0, f"Merchants diferentes devem ser bloqueados, score={score}"

    def test_allows_identical_merchants(self, service):
        """Permite merchants idênticos"""
        series_a = create_mock_series(
            series_id=1, merchant_name="CASAS BECKER", amount=47.61, installment_count=21
        )
        series_b = create_mock_series(
            series_id=2, merchant_name="CASAS BECKER", amount=47.61, installment_count=21
        )

        score = service._calculate_similarity_score(series_a, series_b)

        # Deve ter score alto (100% overlap)
        assert score > 0.5, f"Merchants idênticos devem ter score alto, score={score}"

    def test_blocks_low_name_overlap(self, service):
        """Bloqueia merchants com overlap < 80%"""
        series_a = create_mock_series(
            series_id=1, merchant_name="MERCADO LIVRE", amount=100.00, installment_count=12
        )
        series_b = create_mock_series(
            series_id=2,
            merchant_name="MERCADO PAG",  # Overlap = 50% (1 de 2 palavras)
            amount=100.00,
            installment_count=12,
        )

        score = service._calculate_similarity_score(series_a, series_b)

        # Deve retornar 0.0 (overlap 50% < 80%)
        assert score == 0.0, f"Overlap < 80% deve ser bloqueado, score={score}"


class TestHardRuleInstallmentCount:
    """Testes para HARD RULE 3: Total de parcelas deve ser igual"""

    def test_blocks_different_installment_counts(self, service):
        """Bloqueia séries com número de parcelas diferente"""
        series_a = create_mock_series(
            series_id=1, merchant_name="NETFLIX", amount=49.90, installment_count=12
        )
        series_b = create_mock_series(
            series_id=2,
            merchant_name="NETFLIX",
            amount=49.90,
            installment_count=24,  # Diferente!
        )

        score = service._calculate_similarity_score(series_a, series_b)

        # Deve retornar 0.0 (bloqueado)
        assert score == 0.0, f"Número de parcelas diferente deve ser bloqueado, score={score}"

    def test_allows_same_installment_counts(self, service):
        """Permite séries com mesmo número de parcelas"""
        series_a = create_mock_series(
            series_id=1, merchant_name="NETFLIX", amount=49.90, installment_count=12
        )
        series_b = create_mock_series(
            series_id=2, merchant_name="NETFLIX", amount=49.90, installment_count=12
        )

        score = service._calculate_similarity_score(series_a, series_b)

        # Deve ter score alto
        assert score > 0.5, f"Mesmo número de parcelas deve ter score alto, score={score}"


class TestRealWorldScenarios:
    """Testes com cenários reais reportados"""

    def test_casas_becker_false_positive(self, service):
        """
        Bug reportado: CASAS BECKER R$ 47,61 vs R$ 119,04 (diferença de 250%)
        detectado como duplicata com 70% de similaridade.
        """
        series_a = create_mock_series(
            series_id=1, merchant_name="CASAS BECKER", amount=47.61, installment_count=21
        )
        series_b = create_mock_series(
            series_id=2, merchant_name="CASAS BECKER", amount=119.04, installment_count=21
        )

        score = service._calculate_similarity_score(series_a, series_b)

        # Deve retornar 0.0 (NÃO é duplicata)
        assert score == 0.0, (
            "CASAS BECKER com valores diferentes NÃO deve ser detectado como duplicata"
        )

    def test_netflix_real_duplicate(self, service):
        """Cenário válido: Netflix com valores idênticos é duplicata real"""
        series_a = create_mock_series(
            series_id=1,
            merchant_name="NETFLIX",
            amount=49.90,
            installment_count=12,
            credit_card_id=1,
        )
        series_b = create_mock_series(
            series_id=2,
            merchant_name="NETFLIX",
            amount=49.90,
            installment_count=12,
            credit_card_id=1,
        )

        score = service._calculate_similarity_score(series_a, series_b)

        # Deve ter score muito alto (duplicata real)
        assert score >= 0.85, f"Netflix idêntico deve ter score >= 85%, score={score}"

    def test_small_rounding_allowed(self, service):
        """Pequenos arredondamentos devem ser permitidos"""
        series_a = create_mock_series(
            series_id=1, merchant_name="SPOTIFY", amount=19.90, installment_count=12
        )
        series_b = create_mock_series(
            series_id=2,
            merchant_name="SPOTIFY",
            amount=19.93,  # Diff = R$ 0,03 (dentro do limite)
            installment_count=12,
        )

        score = service._calculate_similarity_score(series_a, series_b)

        # Deve ter score alto (permitido)
        assert score > 0.5, f"Diferença de R$ 0,03 deve ser permitida, score={score}"


class TestEdgeCases:
    """Testes de casos extremos"""

    def test_handles_none_amounts(self, service):
        """Lida com valores None"""
        series_a = create_mock_series(
            series_id=1, merchant_name="TEST", amount=100.00, installment_count=12
        )
        series_b = create_mock_series(
            series_id=2, merchant_name="TEST", amount=100.00, installment_count=12
        )
        series_b.installment_amount = None

        score = service._calculate_similarity_score(series_a, series_b)

        # Deve continuar sem erro
        assert score >= 0.0, "Deve lidar com valores None sem erro"

    def test_handles_none_merchant_names(self, service):
        """Lida com nomes None"""
        series_a = create_mock_series(
            series_id=1, merchant_name="TEST", amount=100.00, installment_count=12
        )
        series_b = create_mock_series(
            series_id=2, merchant_name="TEST", amount=100.00, installment_count=12
        )
        series_b.merchant_name = None

        score = service._calculate_similarity_score(series_a, series_b)

        # Deve continuar sem erro
        assert score >= 0.0, "Deve lidar com nomes None sem erro"

    def test_zero_amounts(self, service):
        """Lida com valores zero"""
        series_a = create_mock_series(
            series_id=1, merchant_name="TEST", amount=0.00, installment_count=12
        )
        series_b = create_mock_series(
            series_id=2, merchant_name="TEST", amount=0.00, installment_count=12
        )

        score = service._calculate_similarity_score(series_a, series_b)

        # Deve continuar sem erro
        assert score >= 0.0, "Deve lidar com valores zero sem erro"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
