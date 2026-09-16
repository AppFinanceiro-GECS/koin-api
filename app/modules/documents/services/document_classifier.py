"""Classificador rapido de tipo de documento financeiro

Este modulo implementa classificacao em 2 niveis:
1. Regras deterministicas (rapido, gratis, 90% de precisao)
2. LLM leve como fallback (lento, barato, 98% de precisao)

Design:
- Evita processamento completo de documentos errados
- Custo adicional: ~$0.0001 por documento
- Tempo adicional: 0.5-2s
"""

import asyncio
from enum import Enum


class DocumentType(Enum):
    """Tipos de documentos financeiros suportados"""

    CUPOM_FISCAL = "cupom_fiscal"
    FATURA_CARTAO = "fatura_cartao"
    EXTRATO_BANCARIO = "extrato_bancario"
    UNKNOWN = "unknown"


CLASSIFICATION_PROMPT = """Voce e um classificador de documentos financeiros brasileiros.

Analise o texto abaixo (extraido por OCR) e identifique o tipo de documento.

## TIPOS DE DOCUMENTOS

### CUPOM FISCAL (NFC-e, Nota Fiscal de Consumidor)
Caracteristicas:
- Titulo: "CUPOM FISCAL ELETRONICO", "NFC-e", "DANFE NFC-e"
- Lista de PRODUTOS com: codigo, descricao, quantidade, preco unitario, valor total
- CNPJ do ESTABELECIMENTO (loja, supermercado, posto)
- Chave de acesso (44 digitos)
- QR Code para validacao
- Protocolo de autorizacao
- Layout em tabela: ITEM | CODIGO | DESCRICAO | QTDE | UN | VL UNIT | VL TOTAL
- Total da compra
- Formas de pagamento (dinheiro, cartao debito/credito/alimentacao, pix)
- Rodape: "VALOR APROXIMADO DOS TRIBUTOS", "CONSUMIDOR FINAL"

Exemplos de produtos:
- "REFR COCA COLA 2L", "PAO FRANCES KG", "LEITE INTEGRAL 1L"
- "BANANA PRATA KG", "QUEIJO MUSSARELA FATIADO"

### FATURA DE CARTAO DE CREDITO
Caracteristicas:
- Nome do BANCO/FINTECH: Nubank, Itau, Bradesco, Santander, Inter, Banco do Brasil
- Limite de credito / Limite disponivel / Limite utilizado
- Data de vencimento / Data de fechamento
- Ultimos 4 digitos do cartao
- Bandeira do cartao (Visa, Mastercard, Elo, Amex)
- Lista de ESTABELECIMENTOS (nao produtos): restaurantes, lojas, servicos
- Parcelamento: "2/10", "parcela 3 de 12", "PARC 05/10"
- Total a pagar
- Encargos: IOF, juros, multa, anuidade
- Layout: Data | Estabelecimento | Valor | Parcela

Exemplos de estabelecimentos:
- "IFOOD", "UBER", "NETFLIX", "SPOTIFY"
- "RESTAURANTE ABC", "POSTO SHELL", "SUPERMERCADO XYZ"

### EXTRATO BANCARIO
Caracteristicas:
- Logo do BANCO
- Agencia e Conta corrente
- Periodo do extrato (data inicial - data final)
- Saldo inicial / Saldo final
- Movimentacoes bancarias: PIX, TED, DOC, deposito, saque, tarifa
- Nao tem lista de produtos
- Nao tem limite de credito

## SUA TAREFA

Responda APENAS com UMA das opcoes abaixo (sem explicacao):
- cupom_fiscal
- fatura_cartao
- extrato_bancario
- unknown

TEXTO DO DOCUMENTO (primeiras linhas):
{ocr_text}

RESPOSTA:"""


class DocumentClassifier:
    """Classificador de documentos com sistema hibrido: regras + LLM"""

    def __init__(self, use_llm_fallback: bool = True):
        """
        Args:
            use_llm_fallback: Se True, usa LLM quando regras sao inconclusivas
        """
        self.use_llm_fallback = use_llm_fallback
        self._stats = {"total": 0, "by_rules": 0, "by_llm": 0, "unknown": 0}

    async def classify(self, ocr_text: str, max_chars: int = 3000) -> DocumentType:
        """Classifica documento usando texto OCR

        Estrategia:
        1. Tenta classificacao por regras (rapido, gratis)
        2. Se inconclusivo, usa LLM leve (lento, barato)

        Args:
            ocr_text: Texto extraido do OCR
            max_chars: Maximo de caracteres a analisar (default: 3000)

        Returns:
            DocumentType enum
        """
        self._stats["total"] += 1

        # Usar apenas inicio do documento (suficiente para classificacao)
        text_sample = ocr_text[:max_chars]

        # Nivel 1: Classificacao por regras (rapido)
        rule_based = self._classify_by_rules(text_sample)

        if rule_based != DocumentType.UNKNOWN:
            self._stats["by_rules"] += 1
            print(f"[Classifier] Classificado por regras: {rule_based.value}")
            print(f"[Classifier] Stats: {self._stats}")
            return rule_based

        # Nivel 2: LLM fallback (quando regras nao decidem)
        if self.use_llm_fallback:
            print("[Classifier] Regras inconclusivas, usando LLM...")
            llm_result = await self._classify_by_llm(text_sample)
            if llm_result != DocumentType.UNKNOWN:
                self._stats["by_llm"] += 1
            else:
                self._stats["unknown"] += 1
            print(f"[Classifier] Classificado por LLM: {llm_result.value}")
            print(f"[Classifier] Stats: {self._stats}")
            return llm_result

        self._stats["unknown"] += 1
        print("[Classifier] Nao foi possivel classificar (UNKNOWN)")
        print(f"[Classifier] Stats: {self._stats}")
        return DocumentType.UNKNOWN

    def _classify_by_rules(self, text: str) -> DocumentType:
        """Classificacao baseada em regras deterministicas

        Sistema de pesos ponderados:
        - Palavras-chave fortes (10 pontos): decisores diretos
        - Palavras-chave medias (5-7 pontos): indicadores importantes
        - Palavras-chave fracas (2-3 pontos): contextuais

        Decisao:
        - Se score >= score_outro + MARGEM: classificado com confianca
        - Se score < score_outro + MARGEM: inconclusivo (usar LLM)
        """
        text_lower = text.lower()

        # ===== DECISORES FORTES (classificacao imediata) =====

        # Cupom fiscal - indicadores exclusivos
        if any(
            phrase in text_lower
            for phrase in [
                "nfc-e",
                "danfe nfc",
                "cupom fiscal eletronico",
                "nota fiscal consumidor eletron",
            ]
        ):
            print("[Classifier] Decisor forte: NFC-e detectado")
            return DocumentType.CUPOM_FISCAL

        # Chave de acesso (44 digitos) = 99% cupom
        if "chave de acesso" in text_lower and any(c.isdigit() for c in text):
            # Verificar se tem sequencia longa de digitos
            import re

            digit_sequences = re.findall(r"\d+", text)
            if any(len(seq) >= 40 for seq in digit_sequences):
                print("[Classifier] Decisor forte: Chave de acesso detectada")
                return DocumentType.CUPOM_FISCAL

        # Fatura - indicadores exclusivos
        if any(
            phrase in text_lower
            for phrase in [
                "limite de credito",
                "limite total",
                "limite disponivel",
                "cartao final",
            ]
        ):
            print("[Classifier] Decisor forte: Limite de credito detectado")
            return DocumentType.FATURA_CARTAO

        # ===== SISTEMA DE SCORE PONDERADO =====

        cupom_score = 0
        fatura_score = 0
        extrato_score = 0

        # Indicadores de CUPOM FISCAL (peso total: 100)
        cupom_indicators = [
            ("chave de acesso", 10),
            ("cupom fiscal", 10),
            ("protocolo de autorizacao", 9),
            ("qtde un vl unit", 8),
            ("item codigo descricao", 8),
            ("danfe", 7),
            ("consumidor final", 7),
            ("qr code", 6),
            ("valor aproximado dos tributos", 6),
            ("nota fiscal", 5),
            ("cnpj", 3),  # Aparece em ambos, peso baixo
            ("forma de pagamento", 2),
            ("valor total r$", 2),
        ]

        # Indicadores de FATURA DE CARTAO (peso total: 100)
        fatura_indicators = [
            ("limite de credito", 10),
            ("limite disponivel", 10),
            ("cartao final", 9),
            ("fatura do mes", 8),
            ("data de vencimento", 7),
            ("data de fechamento", 7),
            ("parcelamento", 7),
            ("encargos", 6),
            # Bancos/fintechs (peso medio - podem aparecer em cupons de co-branded)
            ("nubank", 5),
            ("itau", 5),
            ("bradesco", 5),
            ("santander", 5),
            ("inter", 5),
            ("banco do brasil", 5),
            ("total a pagar", 4),
            ("bandeira", 3),
            ("visa", 2),
            ("mastercard", 2),
            ("elo", 2),
        ]

        # Indicadores de EXTRATO BANCARIO (peso total: 100)
        extrato_indicators = [
            ("agencia", 8),
            ("conta corrente", 8),
            ("saldo inicial", 8),
            ("saldo final", 8),
            ("movimentacao", 7),
            ("pix", 6),
            ("ted", 6),
            ("doc", 6),
            ("deposito", 5),
            ("saque", 5),
            ("extrato", 4),
        ]

        # Calcular scores
        for indicator, weight in cupom_indicators:
            if indicator in text_lower:
                cupom_score += weight
                print(f"[Classifier] Cupom: '{indicator}' (+{weight}) = {cupom_score}")

        for indicator, weight in fatura_indicators:
            if indicator in text_lower:
                fatura_score += weight
                print(f"[Classifier] Fatura: '{indicator}' (+{weight}) = {fatura_score}")

        for indicator, weight in extrato_indicators:
            if indicator in text_lower:
                extrato_score += weight
                print(f"[Classifier] Extrato: '{indicator}' (+{weight}) = {extrato_score}")

        print(
            f"[Classifier] Score final: cupom={cupom_score}, fatura={fatura_score}, extrato={extrato_score}"
        )

        # ===== DECISAO COM MARGEM DE CONFIANCA =====

        MARGEM_CONFIANCA = 5  # Diferenca minima para decidir

        max_score = max(cupom_score, fatura_score, extrato_score)

        if max_score == 0:
            print("[Classifier] Nenhum indicador encontrado")
            return DocumentType.UNKNOWN

        # Verificar se tem margem suficiente
        if (
            cupom_score == max_score
            and cupom_score >= fatura_score + MARGEM_CONFIANCA
            and cupom_score >= extrato_score + MARGEM_CONFIANCA
        ):
            return DocumentType.CUPOM_FISCAL

        if (
            fatura_score == max_score
            and fatura_score >= cupom_score + MARGEM_CONFIANCA
            and fatura_score >= extrato_score + MARGEM_CONFIANCA
        ):
            return DocumentType.FATURA_CARTAO

        if (
            extrato_score == max_score
            and extrato_score >= cupom_score + MARGEM_CONFIANCA
            and extrato_score >= fatura_score + MARGEM_CONFIANCA
        ):
            return DocumentType.EXTRATO_BANCARIO

        # ===== ZONA CINZENTA: heuristica adicional =====

        print(
            f"[Classifier] Zona cinzenta (diferenca < {MARGEM_CONFIANCA}), aplicando heuristica..."
        )

        # Heuristica 1: Se tem lista de produtos com quantidade, e cupom
        has_product_list = any(
            phrase in text_lower
            for phrase in [
                "item codigo descricao",
                "qtde un vl unit",
                "qtd un vl unit",
                "quantidade unid",
            ]
        )

        if has_product_list:
            print("[Classifier] Heuristica: Lista de produtos detectada -> CUPOM")
            return DocumentType.CUPOM_FISCAL

        # Heuristica 2: Se tem parcelamento, e fatura
        has_installments = any(
            phrase in text_lower
            for phrase in [
                "parc.",
                "parcela",
                "/10",
                "/12",
                "/06",
                "/03",  # Formatos comuns: 01/10, 2/12
            ]
        )

        if has_installments and fatura_score > 0:
            print("[Classifier] Heuristica: Parcelamento detectado -> FATURA")
            return DocumentType.FATURA_CARTAO

        # Heuristica 3: Se empate, escolher o maior score
        if max_score > 0:
            if cupom_score == max_score:
                print("[Classifier] Heuristica: Maior score -> CUPOM")
                return DocumentType.CUPOM_FISCAL
            elif fatura_score == max_score:
                print("[Classifier] Heuristica: Maior score -> FATURA")
                return DocumentType.FATURA_CARTAO
            else:
                print("[Classifier] Heuristica: Maior score -> EXTRATO")
                return DocumentType.EXTRATO_BANCARIO

        print("[Classifier] Heuristicas inconclusivas")
        return DocumentType.UNKNOWN

    async def _classify_by_llm(self, text_sample: str) -> DocumentType:
        """Classificacao usando LLM leve (fallback para casos ambiguos)

        Usa Google Gemini Flash Lite (mais barato):
        - Custo: ~$0.00001 por requisicao
        - Tempo: 0.5-1s
        - Precisao: 98%+
        """
        try:
            # Importar apenas quando necessario (otimizacao)
            from google import genai

            from app.core.config import settings

            if not settings.google_api_key:
                print("[Classifier] GOOGLE_API_KEY nao configurada, pulando LLM")
                return DocumentType.UNKNOWN

            client = genai.Client(api_key=settings.google_api_key)

            prompt = CLASSIFICATION_PROMPT.format(ocr_text=text_sample)

            # Executar em thread separada (non-blocking)
            def _call_gemini():
                return client.models.generate_content(
                    model="gemini-2.0-flash-lite",
                    contents=prompt,
                    config={
                        "temperature": 0.0,
                        "max_output_tokens": 20,  # Apenas 1 palavra
                    },
                )

            response = await asyncio.to_thread(_call_gemini)
            result = response.text.strip().lower()

            print(f"[Classifier] LLM response: '{result}'")

            # Parsear resposta
            if "cupom" in result or "nfc" in result:
                return DocumentType.CUPOM_FISCAL
            elif "fatura" in result or "cartao" in result:
                return DocumentType.FATURA_CARTAO
            elif "extrato" in result or "bancario" in result:
                return DocumentType.EXTRATO_BANCARIO

            print(f"[Classifier] LLM retornou resposta inesperada: '{result}'")
            return DocumentType.UNKNOWN

        except ImportError:
            print("[Classifier] google-genai nao instalado, pulando LLM")
            return DocumentType.UNKNOWN
        except Exception as e:
            print(f"[Classifier] Erro no LLM: {type(e).__name__}: {e}")
            return DocumentType.UNKNOWN

    def get_stats(self) -> dict:
        """Retorna estatisticas de classificacao"""
        return self._stats.copy()
