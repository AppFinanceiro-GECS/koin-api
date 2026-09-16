"""Testes para fuzzy matching de series de parcelas"""

import re
import unicodedata

import pytest


def normalize_merchant_name(name: str) -> str:
    """
    Replica a logica de _normalize_merchant_name para testes unitarios.
    """
    if not name:
        return ""

    # Remove acentos
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")

    # Lowercase
    name = name.lower()

    # Remove padroes de parcela: "3/12", "PARC.3/12", "PARC 3/12", "(Parcela 3 de 12)"
    # IMPORTANTE: Padroes mais especificos devem vir ANTES dos genericos
    parcela_patterns = [
        r"\s*\(parcela\s*\d+\s*de\s*\d+\)",  # "(Parcela 3 de 12)"
        r"\s*parc\.?\s*\d+/\d+",  # "PARC.3/12" ou "PARC 3/12"
        r"\s*\d+/\d+\s*$",  # "3/12" no final (mais generico)
    ]
    for pattern in parcela_patterns:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE)

    # Remove sufixos de empresa
    company_suffixes = [
        r"\s+ltda\.?$",
        r"\s+s\.?a\.?$",
        r"\s+eireli$",
        r"\s+mei$",
        r"\s+me$",
    ]
    for pattern in company_suffixes:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE)

    # Remove caracteres especiais
    name = re.sub(r"[\*\-_\.]", " ", name)

    # Remove espacos extras
    name = " ".join(name.split())

    return name.strip()


class TestNormalizeMerchantName:
    """Testes para normalizacao de nomes de merchants"""

    def test_remove_company_suffixes(self):
        """Remove sufixos de empresa (LTDA, S.A., etc)"""
        assert normalize_merchant_name("BARBER PRIME LTDA") == "barber prime"
        assert normalize_merchant_name("MAGAZINE LUIZA S.A.") == "magazine luiza"
        assert normalize_merchant_name("RESTAURANTE BOM GOSTO EIRELI") == "restaurante bom gosto"
        assert normalize_merchant_name("JOAO SILVA MEI") == "joao silva"
        assert normalize_merchant_name("EMPRESA TESTE ME") == "empresa teste"

    def test_remove_installment_patterns(self):
        """Remove padroes de parcela"""
        assert normalize_merchant_name("STEAM 3/12") == "steam"
        assert normalize_merchant_name("LOJA ABC PARC.5/10") == "loja abc"
        assert normalize_merchant_name("MERCADO PARC 8/12") == "mercado"
        assert normalize_merchant_name("INSIDE GAMES 2/6") == "inside games"

    def test_remove_accents(self):
        """Remove acentos"""
        assert normalize_merchant_name("RESTAURANTE AÇAÍ") == "restaurante acai"
        assert normalize_merchant_name("LOJA MÓVEIS") == "loja moveis"

    def test_remove_special_chars(self):
        """Remove caracteres especiais"""
        assert normalize_merchant_name("LOJA *123") == "loja 123"
        assert normalize_merchant_name("MERCADO - ABC") == "mercado abc"

    def test_multiple_spaces(self):
        """Remove espacos multiplos"""
        assert normalize_merchant_name("LOJA   TESTE   ABC") == "loja teste abc"

    def test_complex_normalization(self):
        """Teste com multiplas transformacoes"""
        assert normalize_merchant_name("BARBER PRIME LTDA 3/12") == "barber prime"
        assert normalize_merchant_name("STEAM* PARC.3/12") == "steam"
        assert normalize_merchant_name("INSIDE GAMES S.A. 2/6") == "inside games"


class TestWordOverlapCalculation:
    """Testes para calculo de overlap de palavras"""

    def test_identical_names(self):
        """Nomes identicos devem ter 100% overlap"""
        norm1 = normalize_merchant_name("STEAM")
        norm2 = normalize_merchant_name("STEAM")
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        intersection = words1 & words2
        overlap = len(intersection) / max(len(words1), len(words2))
        assert overlap == 1.0

    def test_similar_names(self):
        """Nomes similares devem ter alto overlap"""
        norm1 = normalize_merchant_name("INSIDE GAMES")
        norm2 = normalize_merchant_name("INSIDE GAMES 2/6")
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        intersection = words1 & words2
        overlap = len(intersection) / max(len(words1), len(words2))
        assert overlap >= 0.5, f"Overlap deve ser >= 0.5, obteve {overlap}"

    def test_different_names(self):
        """Nomes diferentes devem ter baixo overlap"""
        norm1 = normalize_merchant_name("STEAM")
        norm2 = normalize_merchant_name("INSIDE GAMES")
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        intersection = words1 & words2
        overlap = (
            len(intersection) / max(len(words1), len(words2))
            if max(len(words1), len(words2)) > 0
            else 0
        )
        assert overlap < 0.5, f"Overlap deve ser < 0.5, obteve {overlap}"

    def test_partial_match(self):
        """Nomes com match parcial"""
        norm1 = normalize_merchant_name("MERCADO LIVRE")
        norm2 = normalize_merchant_name("MERCADO PAG")
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        intersection = words1 & words2
        overlap = len(intersection) / max(len(words1), len(words2))
        assert overlap == 0.5, f"Overlap deve ser 0.5 (1 de 2 palavras), obteve {overlap}"


class TestAmountTolerance:
    """Testes para tolerancia de valor"""

    def test_exact_match(self):
        """Valores identicos devem ser aceitos"""
        base = 99.90
        candidate = 99.90
        tolerance = 0.05  # 5%
        ratio = abs(base - candidate) / base if base else 0
        assert ratio <= tolerance

    def test_within_tolerance(self):
        """Valores dentro da tolerancia devem ser aceitos"""
        base = 100.00
        candidate = 103.00  # 3% diferenca
        tolerance = 0.05  # 5%
        ratio = abs(base - candidate) / base if base else 0
        assert ratio <= tolerance

    def test_outside_tolerance(self):
        """Valores fora da tolerancia devem ser rejeitados"""
        base = 100.00
        candidate = 110.00  # 10% diferenca
        tolerance = 0.05  # 5%
        ratio = abs(base - candidate) / base if base else 0
        assert ratio > tolerance


class TestFuzzyMatchScenarios:
    """Testes de cenarios reais de fuzzy matching"""

    def test_steam_series_match(self):
        """STEAM 3/12 deve fazer match com serie STEAM existente"""
        existing_merchant = "STEAM"
        incoming_merchant = "STEAM 3/12"

        norm_existing = normalize_merchant_name(existing_merchant)
        norm_incoming = normalize_merchant_name(incoming_merchant)

        words_existing = set(norm_existing.split())
        words_incoming = set(norm_incoming.split())

        intersection = words_existing & words_incoming
        overlap = (
            len(intersection) / max(len(words_existing), len(words_incoming))
            if max(len(words_existing), len(words_incoming)) > 0
            else 0
        )

        assert overlap >= 0.5, (
            f"Deveria fazer match: {norm_existing} vs {norm_incoming}, overlap={overlap}"
        )

    def test_inside_games_match(self):
        """INSIDE GAMES 2/6 deve fazer match com INSIDE GAMES existente"""
        existing_merchant = "INSIDE GAMES"
        incoming_merchant = "INSIDE GAMES 2/6"

        norm_existing = normalize_merchant_name(existing_merchant)
        norm_incoming = normalize_merchant_name(incoming_merchant)

        assert norm_existing == norm_incoming == "inside games"

    def test_barber_prime_ltda_match(self):
        """BARBER PRIME LTDA deve fazer match com BARBER PRIME existente"""
        existing_merchant = "BARBER PRIME"
        incoming_merchant = "BARBER PRIME LTDA"

        norm_existing = normalize_merchant_name(existing_merchant)
        norm_incoming = normalize_merchant_name(incoming_merchant)

        assert norm_existing == norm_incoming == "barber prime"

    def test_no_false_positive_match(self):
        """Merchants diferentes nao devem fazer match"""
        merchant1 = "STEAM"
        merchant2 = "NETFLIX"

        norm1 = normalize_merchant_name(merchant1)
        norm2 = normalize_merchant_name(merchant2)

        words1 = set(norm1.split())
        words2 = set(norm2.split())

        intersection = words1 & words2
        overlap = (
            len(intersection) / max(len(words1), len(words2))
            if max(len(words1), len(words2)) > 0
            else 0
        )

        assert overlap < 0.5, f"Nao deveria fazer match: {norm1} vs {norm2}, overlap={overlap}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
