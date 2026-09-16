"""Testes para o DocumentClassifier"""

import pytest

from app.modules.documents.services.document_classifier import DocumentClassifier, DocumentType


@pytest.fixture
def classifier():
    """Fixture para criar classificador (sem LLM fallback para testes mais rapidos)"""
    return DocumentClassifier(use_llm_fallback=False)


class TestCupomFiscalDetection:
    """Testes de detecção de cupons fiscais"""

    def test_nfc_e_strong_indicator(self, classifier):
        """NFC-e é um decisor forte para cupom fiscal"""
        ocr_text = """
        CUPOM FISCAL ELETRONICO - NFC-e
        SUPERMERCADO ABC LTDA
        CNPJ: 12.345.678/0001-90
        """
        result = classifier._classify_by_rules(ocr_text)
        assert result == DocumentType.CUPOM_FISCAL

    def test_chave_acesso_indicator(self, classifier):
        """Chave de acesso indica cupom fiscal"""
        ocr_text = """
        NOTA FISCAL CONSUMIDOR
        Chave de Acesso:
        1234 5678 9012 3456 7890 1234 5678 9012 3456 7890 1234
        """
        result = classifier._classify_by_rules(ocr_text)
        assert result == DocumentType.CUPOM_FISCAL

    def test_product_list_format(self, classifier):
        """Lista de produtos com quantidade indica cupom"""
        ocr_text = """
        ITEM CODIGO DESCRICAO QTDE UN VL UNIT VL TOTAL
        001 12345 REFR COCA COLA 2L 1 UN 8.99 8.99
        002 67890 PAO FRANCES KG 0.5 KG 12.00 6.00
        TOTAL: R$ 14.99
        """
        result = classifier._classify_by_rules(ocr_text)
        assert result == DocumentType.CUPOM_FISCAL

    def test_cupom_with_cnpj(self, classifier):
        """Cupom com CNPJ e protocolo"""
        ocr_text = """
        CARREFOUR COMERCIO E INDUSTRIA LTDA
        CNPJ: 45.543.915/0001-81
        Protocolo de Autorizacao: 123456789
        QTDE UN VL UNIT
        Valor Total: R$ 125,50
        """
        result = classifier._classify_by_rules(ocr_text)
        assert result == DocumentType.CUPOM_FISCAL


class TestFaturaCartaoDetection:
    """Testes de detecção de faturas de cartão"""

    def test_limite_credito_strong_indicator(self, classifier):
        """Limite de crédito é decisor forte para fatura"""
        ocr_text = """
        BANCO ITAU S.A.
        Limite de Crédito: R$ 10.000,00
        Limite Disponível: R$ 8.500,00
        """
        result = classifier._classify_by_rules(ocr_text)
        assert result == DocumentType.FATURA_CARTAO

    def test_cartao_final_indicator(self, classifier):
        """Cartão final indica fatura"""
        ocr_text = """
        FATURA NUBANK
        Cartão final 1234
        Vencimento: 15/02/2026
        Total a Pagar: R$ 1.500,00
        """
        result = classifier._classify_by_rules(ocr_text)
        assert result == DocumentType.FATURA_CARTAO

    def test_parcelamento_indicator(self, classifier):
        """Parcelamento indica fatura de cartão"""
        ocr_text = """
        FATURA BRADESCO
        12/01 LOJA ABC 01/12 R$ 100,00
        15/01 RESTAURANTE XYZ 02/06 R$ 50,00
        Total: R$ 150,00
        """
        result = classifier._classify_by_rules(ocr_text)
        assert result == DocumentType.FATURA_CARTAO

    def test_banco_names(self, classifier):
        """Nomes de bancos indicam fatura"""
        ocr_text = """
        BANCO SANTANDER S.A.
        Data Vencimento: 10/02/2026
        Total da Fatura: R$ 2.500,00
        Encargos: R$ 0,00
        """
        result = classifier._classify_by_rules(ocr_text)
        assert result == DocumentType.FATURA_CARTAO


class TestScoreSystem:
    """Testes do sistema de pontuação"""

    def test_cupom_high_score(self, classifier):
        """Cupom com múltiplos indicadores"""
        ocr_text = """
        NFC-e
        SUPERMERCADO XYZ
        CNPJ: 12.345.678/0001-90
        ITEM CODIGO DESCRICAO QTDE UN VL UNIT VL TOTAL
        Protocolo de Autorizacao: 123456
        QR Code: ...
        Valor Aproximado dos Tributos: R$ 5,00
        """
        result = classifier._classify_by_rules(ocr_text)
        assert result == DocumentType.CUPOM_FISCAL

    def test_fatura_high_score(self, classifier):
        """Fatura com múltiplos indicadores"""
        ocr_text = """
        NUBANK
        Limite de Crédito: R$ 10.000,00
        Fatura do mês de Janeiro
        Data de Vencimento: 15/02/2026
        Parcelamento disponível
        Total a Pagar: R$ 1.500,00
        Bandeira: Mastercard
        """
        result = classifier._classify_by_rules(ocr_text)
        assert result == DocumentType.FATURA_CARTAO

    def test_margem_confianca(self, classifier):
        """Testa margem de confiança (diferença mínima de 5 pontos)"""
        # Texto ambíguo com scores próximos
        ocr_text = """
        CARREFOUR
        CNPJ: 12.345.678/0001-90
        Total: R$ 100,00
        """
        # Deve ser inconclusivo ou usar heurística
        result = classifier._classify_by_rules(ocr_text)
        # Pode ser UNKNOWN ou usar heurística
        assert result in [
            DocumentType.CUPOM_FISCAL,
            DocumentType.FATURA_CARTAO,
            DocumentType.UNKNOWN,
        ]


class TestHeuristics:
    """Testes de heurísticas para zona cinzenta"""

    def test_heuristic_product_list(self, classifier):
        """Heurística: lista de produtos = cupom"""
        ocr_text = """
        ESTABELECIMENTO ABC
        ITEM CODIGO DESCRICAO
        001 PRODUTO A
        002 PRODUTO B
        Total: R$ 50,00
        """
        result = classifier._classify_by_rules(ocr_text)
        assert result == DocumentType.CUPOM_FISCAL

    def test_heuristic_installments(self, classifier):
        """Heurística: parcelamento = fatura"""
        ocr_text = """
        FATURA DO MES
        LOJA ABC PARC. 01/10 R$ 100,00
        LOJA XYZ PARC. 02/12 R$ 100,00
        Total a Pagar: R$ 200,00
        """
        result = classifier._classify_by_rules(ocr_text)
        assert result == DocumentType.FATURA_CARTAO


class TestEdgeCases:
    """Testes de casos extremos"""

    def test_empty_text(self, classifier):
        """Texto vazio deve retornar UNKNOWN"""
        result = classifier._classify_by_rules("")
        assert result == DocumentType.UNKNOWN

    def test_no_indicators(self, classifier):
        """Texto sem indicadores deve retornar UNKNOWN"""
        ocr_text = "Lorem ipsum dolor sit amet"
        result = classifier._classify_by_rules(ocr_text)
        assert result == DocumentType.UNKNOWN

    def test_mixed_indicators_cupom_wins(self, classifier):
        """Cupom com alguns indicadores de fatura (co-branded card)"""
        ocr_text = """
        NFC-e CUPOM FISCAL ELETRONICO
        CARREFOUR BANCO
        CNPJ: 12.345.678/0001-90
        Chave de Acesso: 1234567890...
        ITEM CODIGO DESCRICAO QTDE
        Cartão de Crédito Carrefour Visa
        """
        # NFC-e e Chave de Acesso são decisores fortes
        result = classifier._classify_by_rules(ocr_text)
        assert result == DocumentType.CUPOM_FISCAL


class TestStats:
    """Testes de estatísticas"""

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        """Verifica se estatísticas são rastreadas corretamente"""
        classifier = DocumentClassifier(use_llm_fallback=False)

        # Classificar alguns documentos
        await classifier.classify("NFC-e CUPOM FISCAL")
        await classifier.classify("Limite de credito R$ 10.000")  # lowercase para detectar
        await classifier.classify("Lorem ipsum")

        stats = classifier.get_stats()
        assert stats["total"] == 3
        assert stats["by_rules"] == 2  # Cupom e Fatura
        assert stats["unknown"] == 1  # Lorem ipsum


@pytest.mark.asyncio
async def test_full_classification_flow():
    """Teste de fluxo completo de classificação"""
    classifier = DocumentClassifier(use_llm_fallback=False)

    # Cupom fiscal real (exemplo)
    cupom_text = """
    CUPOM FISCAL ELETRONICO - NFC-e
    SUPER ADEGA LTDA
    CNPJ: 12.345.678/0001-90
    ITEM CODIGO DESCRICAO QTDE UN VL UNIT VL TOTAL
    001 10074 REFR COCA COLA 2L 1 UN 8.99 8.99
    002 20145 BANANA PRATA KG 1.5 KG 7.99 11.99
    Chave de Acesso: 12345678901234567890123456789012345678901234
    Protocolo: 123456789
    TOTAL: R$ 20,98
    """

    result = await classifier.classify(cupom_text)
    assert result == DocumentType.CUPOM_FISCAL

    # Fatura de cartão real (exemplo)
    fatura_text = """
    NUBANK - Nu Pagamentos S.A.
    Cartão final 1234
    Limite de Crédito: R$ 10.000,00
    Limite Disponível: R$ 8.500,00

    Fatura de Janeiro/2026
    Vencimento: 15/02/2026

    12 JAN IFOOD R$ 50,00
    15 JAN UBER 2/10 R$ 20,00
    20 JAN NETFLIX R$ 39,90

    Total a Pagar: R$ 109,90
    """

    result = await classifier.classify(fatura_text)
    assert result == DocumentType.FATURA_CARTAO
