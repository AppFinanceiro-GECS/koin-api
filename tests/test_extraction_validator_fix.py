"""Testes para verificar fix de LTDA/S.A. no ExtractionValidator"""

import pytest

from app.modules.documents.services.extraction_validator import ExtractionValidator


class TestSectionHeaderFix:
    """Testes para garantir que merchants legitimos com LTDA/S.A. nao sejam removidos"""

    def setup_method(self):
        self.validator = ExtractionValidator()

    def test_barber_prime_ltda_with_date_should_be_kept(self):
        """BARBER PRIME LTDA com data deve ser mantido (caso real do bug)"""
        items = [
            {
                "description": "BARBER PRIME LTDA",
                "amount": 198.70,
                "date": "2025-12-26",
                "transaction_type": "compra",
            },
            {
                "description": "STEAM 3/12",
                "amount": 99.90,
                "date": "2025-12-15",
                "transaction_type": "compra",
            },
        ]
        card_info = {"total_amount": 6273.12}

        result = self.validator.remove_section_headers(items, card_info)

        descriptions = [item["description"] for item in result]
        assert "BARBER PRIME LTDA" in descriptions, "BARBER PRIME LTDA deveria ser mantido"
        assert len(result) == 2, "Ambos os itens devem ser mantidos"

    def test_ltda_without_date_and_equals_total_should_be_removed(self):
        """LTDA sem data e com valor igual ao total deve ser removido (header de secao)"""
        items = [
            {
                "description": "KAS S C T LTDA",
                "amount": 1500.00,
                "date": None,  # Sem data
                "transaction_type": "compra",
            },
            {
                "description": "COMPRA NORMAL",
                "amount": 500.00,
                "date": "2025-12-15",
                "transaction_type": "compra",
            },
        ]
        card_info = {"total_amount": 1500.00}  # Valor igual

        result = self.validator.remove_section_headers(items, card_info)

        descriptions = [item["description"] for item in result]
        assert "KAS S C T LTDA" not in descriptions, (
            "KAS S C T LTDA deveria ser removido (header de secao)"
        )
        assert "COMPRA NORMAL" in descriptions

    def test_sa_with_date_should_be_kept(self):
        """Empresa S.A. com data deve ser mantida (compra legitima)"""
        items = [
            {
                "description": "MAGAZINE LUIZA S.A.",
                "amount": 1299.00,
                "date": "2025-12-10",
                "transaction_type": "compra",
            }
        ]
        card_info = {"total_amount": 5000.00}

        result = self.validator.remove_section_headers(items, card_info)

        assert len(result) == 1, "MAGAZINE LUIZA S.A. com data deve ser mantido"

    def test_eireli_with_date_should_be_kept(self):
        """Empresa EIRELI com data deve ser mantida"""
        items = [
            {
                "description": "RESTAURANTE BOM GOSTO EIRELI",
                "amount": 85.50,
                "date": "2025-12-20",
                "transaction_type": "compra",
            }
        ]
        card_info = {"total_amount": 3000.00}

        result = self.validator.remove_section_headers(items, card_info)

        assert len(result) == 1, "EIRELI com data deve ser mantido"

    def test_mei_with_date_should_be_kept(self):
        """Empresa MEI com data deve ser mantida"""
        items = [
            {
                "description": "JOAO SILVA MEI",
                "amount": 50.00,
                "date": "2025-12-18",
                "transaction_type": "compra",
            }
        ]
        card_info = {"total_amount": 2000.00}

        result = self.validator.remove_section_headers(items, card_info)

        assert len(result) == 1, "MEI com data deve ser mantido"

    def test_all_caps_without_date_and_special_chars_should_be_removed(self):
        """Nome ALL CAPS sem data e sem caracteres de merchant deve ser removido"""
        items = [
            {
                "description": "EMPRESA GENÉRICA LTDA",
                "amount": 500.00,
                "date": None,  # Sem data
                "transaction_type": "compra",
            }
        ]
        card_info = {"total_amount": 1000.00}

        result = self.validator.remove_section_headers(items, card_info)

        # Este caso é ambíguo - pode ser header ou compra sem data
        # O fix atual remove se não tem data E é all caps simples
        assert len(result) == 0, "ALL CAPS sem data deve ser removido como possivel header"

    def test_merchant_with_numbers_and_ltda_should_be_kept(self):
        """Merchant com numeros/caracteres especiais + LTDA deve ser mantido"""
        items = [
            {
                "description": "LOJA 123 COMERCIO LTDA",
                "amount": 299.90,
                "date": "2025-12-22",
                "transaction_type": "compra",
            }
        ]
        card_info = {"total_amount": 4000.00}

        result = self.validator.remove_section_headers(items, card_info)

        assert len(result) == 1, "Merchant com numeros + LTDA deve ser mantido"

    def test_multiple_transactions_mixed(self):
        """Teste com multiplas transacoes - mix de headers e compras reais"""
        items = [
            # Header de secao (sem data, valor = total)
            {
                "description": "TOTAL SECAO LTDA",
                "amount": 1000.00,
                "date": None,
                "transaction_type": "compra",
            },
            # Compra real (com data)
            {
                "description": "BARBER PRIME LTDA",
                "amount": 198.70,
                "date": "2025-12-26",
                "transaction_type": "compra",
            },
            # Compra real (com data)
            {
                "description": "COMERCIAL XYZ S.A.",
                "amount": 500.00,
                "date": "2025-12-20",
                "transaction_type": "compra",
            },
            # Compra normal
            {
                "description": "STEAM 3/12",
                "amount": 99.90,
                "date": "2025-12-15",
                "transaction_type": "compra",
            },
        ]
        card_info = {"total_amount": 1000.00}  # Total igual ao header

        result = self.validator.remove_section_headers(items, card_info)

        descriptions = [item["description"] for item in result]

        # Header deve ser removido
        assert "TOTAL SECAO LTDA" not in descriptions, "Header de secao deve ser removido"

        # Compras reais devem ser mantidas
        assert "BARBER PRIME LTDA" in descriptions, "BARBER PRIME com data deve ser mantido"
        assert "COMERCIAL XYZ S.A." in descriptions, "COMERCIAL XYZ com data deve ser mantido"
        assert "STEAM 3/12" in descriptions, "Compra normal deve ser mantida"

        assert len(result) == 3, f"Esperado 3 itens, obteve {len(result)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
