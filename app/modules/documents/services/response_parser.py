"""Parser de respostas JSON das LLMs"""

import json
import re
from datetime import datetime

from .extraction_validator import ExtractionValidator


class ResponseParser:
    """Parseia e normaliza respostas JSON das LLMs"""

    def __init__(self):
        self.validator = ExtractionValidator()

    # Mapeamento de palavras-chave para categorias automaticas
    CATEGORY_KEYWORDS = {
        "alimentacao": [
            "restaurante",
            "lanchonete",
            "padaria",
            "pizzaria",
            "burger",
            "mcdonald",
            "subway",
            "habib",
            "giraffas",
            "outback",
            "madero",
            "ifood",
            "rappi",
            "uber eats",
            "delivery",
            "sushi",
            "churrascaria",
            "cafe",
            "cafeteria",
            "doceria",
            "sorvete",
            "acai",
        ],
        "mercado": [
            "supermercado",
            "atacadao",
            "atacado",
            "assai",
            "carrefour",
            "extra",
            "pao de acucar",
            "dia",
            "big",
            "walmart",
            "supermarket",
            "hortifruti",
            "sacolao",
            "feira",
        ],
        "transporte": [
            "uber",
            "99",
            "cabify",
            "lyft",
            "taxi",
            "posto",
            "combustivel",
            "gasolina",
            "etanol",
            "shell",
            "ipiranga",
            "br distribuidora",
            "petrobras",
            "estacionamento",
            "parking",
            "pedagio",
            "sem parar",
            "conectcar",
            "auto posto",
            "abastecimento",
        ],
        "saude": [
            "farmacia",
            "drogasil",
            "drogaria",
            "pacheco",
            "raia",
            "droga",
            "hospital",
            "clinica",
            "laboratorio",
            "medico",
            "dentista",
            "otica",
            "oculos",
            "unimed",
            "amil",
            "sulamerica",
            "bradesco saude",
        ],
        "lazer": [
            "cinema",
            "cinemark",
            "cinepolis",
            "uci",
            "kinoplex",
            "teatro",
            "show",
            "ingresso",
            "evento",
            "parque",
            "zoo",
            "museu",
            "netflix",
            "spotify",
            "amazon prime",
            "disney",
            "hbo",
            "youtube",
            "twitch",
            "steam",
            "playstation",
            "xbox",
            "jogos",
            "games",
            "nintendo",
        ],
        "compras": [
            "shopee",
            "mercadolivre",
            "mercado livre",
            "amazon",
            "aliexpress",
            "magalu",
            "magazine luiza",
            "americanas",
            "submarino",
            "casas bahia",
            "renner",
            "riachuelo",
            "c&a",
            "zara",
            "hm",
            "forever",
            "adidas",
            "nike",
            "fila",
            "puma",
            "centauro",
            "netshoes",
            "shein",
            "wish",
            "ebay",
        ],
        "servicos": [
            "internet",
            "starlink",
            "vivo",
            "claro",
            "tim",
            "oi",
            "telefone",
            "celular",
            "telecom",
            "net",
            "sky",
            "luz",
            "energia",
            "enel",
            "cpfl",
            "cemig",
            "agua",
            "saneamento",
            "sabesp",
            "caesb",
            "gas",
            "comgas",
            "naturgy",
        ],
        "educacao": [
            "escola",
            "faculdade",
            "universidade",
            "curso",
            "aula",
            "udemy",
            "coursera",
            "alura",
            "duolingo",
            "livro",
            "livraria",
            "saraiva",
            "cultura",
            "amazon kindle",
        ],
        "financeiro": [
            "pagseguro",
            "mercadopago",
            "picpay",
            "ame",
            "paypal",
            "stone",
            "cielo",
            "rede",
            "getnet",
            "pag seguro",
            "emprestimo",
            "financiamento",
            "seguro",
            "investimento",
        ],
    }

    # Valores placeholder que indicam que o LLM não conseguiu extrair dados reais
    PLACEHOLDER_VALUES = [
        "NOME DO ESTABELECIMENTO",
        "YYYY-MM-DD",
        "Nome do Banco",
        "codigo_banco",
        "Nome Completo do Cartão",
        "visa|mastercard|elo|amex|hipercard",
    ]

    def _is_placeholder_response(self, data: dict) -> bool:
        """Detecta se a resposta contém valores placeholder do prompt"""
        # Verificar card_info
        card_info = data.get("card_info", {})
        if card_info:
            for field in [
                "card_issuer",
                "card_bank",
                "card_name",
                "card_brand",
                "due_date",
                "closing_date",
            ]:
                value = card_info.get(field)
                if value and any(ph in str(value) for ph in self.PLACEHOLDER_VALUES):
                    print(f"[Parser] AVISO: Detectado placeholder em card_info.{field}: {value}")
                    return True

        # Verificar items
        items = data.get("items", [])
        for item in items:
            desc = item.get("description", "")
            if any(ph in str(desc) for ph in self.PLACEHOLDER_VALUES):
                print(f"[Parser] AVISO: Detectado placeholder em item.description: {desc}")
                return True
            # Data placeholder é aceita - será tratada como None no _normalize_item

        return False

    def parse(self, content: str) -> dict:
        """Parseia a resposta JSON da LLM"""
        try:
            content = content.strip()
            if "```" in content:
                match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
                if match:
                    content = match.group(1)

            data = json.loads(content)

            # Se o LLM retornou um array ao invés de objeto, converter
            if isinstance(data, list):
                print("[Parser] LLM retornou array ao invés de objeto, convertendo...")
                # Assumir que é uma lista de transações
                data = {"document_type": "fatura_cartao", "items": data, "card_info": None}

            # Verificar se é resposta placeholder
            if self._is_placeholder_response(data):
                return {
                    "items": [],
                    "error": "LLM não conseguiu extrair dados do documento. O documento pode estar ilegível ou em formato não suportado.",
                }

            items = []
            for item in data.get("items", []):
                normalized = self._normalize_item(item)
                if normalized and normalized["amount"] != 0:
                    items.append(normalized)

            # DEBUG: Log para verificar o que veio do LLM
            import json as json_debug

            print("[Parser] DEBUG: FULL JSON from LLM:")
            print(json_debug.dumps(data, indent=2, ensure_ascii=False, default=str)[:2000])

            # Extrair total_amount de varios lugares possiveis
            total_amount = data.get("total_amount")
            if not total_amount and "payment_info" in data:
                payment_info = data.get("payment_info", {})
                if isinstance(payment_info, dict):
                    total_amount = (
                        payment_info.get("total_amount")
                        or payment_info.get("total")
                        or payment_info.get("valor_total")
                    )
                    print(f"[Parser] DEBUG: total_amount from payment_info={total_amount}")

            result = {
                "items": items,
                "document_type": data.get("document_type"),
                "total_amount": total_amount,
            }

            card_info = data.get("card_info")
            if card_info and isinstance(card_info, dict):
                result["card_info"] = self._normalize_card_info(card_info)

                # Corrigir datas de parcelas usando o mês/ano da fatura
                if result["card_info"].get("invoice_month") and result["card_info"].get(
                    "invoice_year"
                ):
                    result["items"] = self._fix_installment_dates(
                        result["items"],
                        result["card_info"]["invoice_month"],
                        result["card_info"]["invoice_year"],
                    )

            # Parse merchant_info for cupom fiscal (needed for payment_info)
            merchant_info = data.get("merchant_info")
            if merchant_info and isinstance(merchant_info, dict):
                result["merchant_info"] = merchant_info

            # Parse payment_info for cupom fiscal (pass merchant_info for store_name extraction)
            payment_info = data.get("payment_info")
            if payment_info and isinstance(payment_info, dict):
                result["payment_info"] = self._normalize_payment_info(payment_info, merchant_info)

            return result

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            return {
                "items": [],
                "error": f"Erro ao processar resposta: {str(e)}",
                "raw": content[:500] if content else "",
            }

    def _normalize_item(self, item: dict) -> dict | None:
        """Normaliza um item extraido"""
        amount = item.get("amount", 0)
        if isinstance(amount, str):
            amount = float(amount.replace(".", "").replace(",", ".").replace("R$", "").strip())

        is_installment = item.get("is_installment", False)
        installment_current = None
        installment_total = None

        if is_installment:
            installment_current = item.get("installment_current")
            installment_total = item.get("installment_total")

            if installment_current and installment_total:
                try:
                    installment_current = int(installment_current)
                    installment_total = int(installment_total)
                    if installment_current < 1 or installment_current > installment_total:
                        is_installment = False
                        installment_current = None
                        installment_total = None
                except (ValueError, TypeError):
                    is_installment = False
                    installment_current = None
                    installment_total = None
            else:
                is_installment = False

        description = str(item.get("description", "Item"))[:200]

        if self.validator.is_invalid_description(description):
            return None

        transaction_type = item.get("transaction_type", "compra")
        category = item.get("category", "outros")

        # Auto-categorizar se a categoria for generica
        if category in ["outros", "other", None, ""]:
            auto_category = self._auto_categorize(description)
            if auto_category:
                category = auto_category

        if transaction_type == "compra":
            if category in ["pagamento"]:
                transaction_type = "pagamento"
            elif category in ["estorno"]:
                transaction_type = "estorno"
            elif category in ["credito"]:
                transaction_type = "credito"
            elif category in ["saldo_anterior"]:
                transaction_type = "saldo_anterior"
            elif "anuidade" in description.lower():
                transaction_type = "anuidade"

        valid_types = [
            "compra",
            "anuidade",
            "encargo",
            "estorno",
            "credito",
            "pagamento",
            "saldo_anterior",
        ]
        if transaction_type not in valid_types:
            transaction_type = "compra"

        # Limpa data se for placeholder (YYYY-MM-DD ou similar)
        item_date = item.get("date")
        if item_date and "YYYY" in str(item_date):
            print(f"[Parser] Data placeholder detectada '{item_date}', usando None")
            item_date = None
        elif item_date:
            # Normalizar data para formato ISO (YYYY-MM-DD)
            item_date = self._parse_date(item_date)
            if not item_date:
                print(f"[Parser] AVISO: Data inválida '{item.get('date')}', usando None")

        normalized = {
            "description": description,
            "amount": float(amount) if amount else 0,
            "date": item_date,
            "category": category,
            "transaction_type": transaction_type,
            "confidence": 0.9,
            "is_installment": is_installment,
            "installment_current": installment_current,
            "installment_total": installment_total,
        }

        future_installments = item.get("future_installments")
        if future_installments and isinstance(future_installments, list):
            normalized["future_installments"] = future_installments

        # card_last_digits - últimos 4 dígitos do cartão (para faturas multi-cartão)
        card_digits = item.get("card_last_digits")
        if card_digits:
            normalized["card_last_digits"] = str(card_digits)[-4:]

        # Campos específicos de cupom fiscal (grocery tracking)
        if item.get("quantity") is not None:
            normalized["quantity"] = float(item["quantity"])
        if item.get("unit"):
            normalized["unit"] = item["unit"]
        if item.get("unit_price") is not None:
            normalized["unit_price"] = float(item["unit_price"])

        # grocery_category - usar do LLM ou inferir default 'other'
        grocery_category = item.get("grocery_category")
        if grocery_category:
            normalized["grocery_category"] = grocery_category
        elif item.get("quantity") is not None or item.get("unit"):
            # Se tem quantity/unit, é item de cupom fiscal - inferir categoria
            normalized["grocery_category"] = "other"

        # necessity_type - usar do LLM ou inferir default 'essential'
        necessity_type = item.get("necessity_type")
        if necessity_type:
            normalized["necessity_type"] = necessity_type
        elif normalized.get("grocery_category"):
            # Se tem grocery_category, é cupom fiscal - inferir necessidade
            normalized["necessity_type"] = "essential"

        return normalized

    def _parse_date(self, value) -> str | None:
        """Converte data para formato YYYY-MM-DD (ISO 8601)"""
        if value is None:
            return None

        # Se já é datetime, converte
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")

        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")

        if isinstance(value, str):
            value = value.strip()

            # Tenta vários formatos comuns
            formats = [
                "%Y-%m-%d",  # ISO 8601 (já correto)
                "%d/%m/%Y",  # Brasileiro: 03/01/2026
                "%d-%m-%Y",  # Brasileiro com traço
                "%Y/%m/%d",  # Ano primeiro com barra
                "%d/%m/%y",  # Ano curto: 03/01/26
                "%d-%m-%y",  # Ano curto com traço
                "%m/%d/%Y",  # Americano
                "%d %b %Y",  # 15 Jan 2026
                "%d %B %Y",  # 15 Janeiro 2026
                "%Y-%m-%dT%H:%M:%S",  # ISO com hora
                "%Y-%m-%dT%H:%M:%SZ",  # ISO com hora e Z
            ]

            for fmt in formats:
                try:
                    dt = datetime.strptime(value[: len(fmt) + 5], fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue

            # Regex fallback para DD/MM/YYYY ou DD-MM-YYYY
            import re

            match = re.search(r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})", value)
            if match:
                d, m, y = match.groups()
                # Se ano tem 2 dígitos, assumir 20xx se < 50, senão 19xx
                if len(y) == 2:
                    y = "20" + y if int(y) < 50 else "19" + y
                try:
                    # Assumir formato brasileiro DD/MM/YYYY
                    dt = datetime(int(y), int(m), int(d))
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

        print(f"[Parser] AVISO: Não foi possível parsear data '{value}'")
        return None

    def _auto_categorize(self, description: str) -> str | None:
        """
        Categoriza automaticamente uma transacao baseado em palavras-chave na descricao.
        Retorna a categoria ou None se nao encontrar match.
        """
        if not description:
            return None

        desc_lower = description.lower()

        # Remove acentos para facilitar match
        import unicodedata

        desc_normalized = unicodedata.normalize("NFD", desc_lower)
        desc_normalized = desc_normalized.encode("ascii", "ignore").decode("utf-8")

        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                # Normalizar keyword tambem
                kw_normalized = unicodedata.normalize("NFD", keyword.lower())
                kw_normalized = kw_normalized.encode("ascii", "ignore").decode("utf-8")

                if kw_normalized in desc_normalized:
                    return category

        return None

    def _fix_installment_dates(
        self, items: list[dict], invoice_month: int, invoice_year: int
    ) -> list[dict]:
        """
        Corrige datas de transações parceladas para usar o mês da fatura.

        Problema: O LLM extrai a data do código da parcela (ex: "AM07/10" = julho)
        ao invés da data da linha na fatura (janeiro).

        Solução: Para parcelas, usar o mês/ano da fatura como referência.
        """
        from datetime import date

        fixed_items = []
        for item in items:
            if item.get("is_installment") and item.get("date"):
                try:
                    # Parse data atual
                    item_date = datetime.strptime(item["date"], "%Y-%m-%d")

                    # Se a data está muito fora do mês da fatura (diferença > 2 meses),
                    # provavelmente é a data original da compra, não a data da fatura
                    month_diff = abs(
                        (invoice_year * 12 + invoice_month)
                        - (item_date.year * 12 + item_date.month)
                    )

                    if month_diff > 2:
                        # Usar mês/ano da fatura, mantendo o dia (ou 1 se inválido)
                        try:
                            corrected_date = date(invoice_year, invoice_month, item_date.day)
                        except ValueError:
                            # Dia inválido para o mês (ex: 31 em fev) - usar dia 1
                            corrected_date = date(invoice_year, invoice_month, 1)

                        print(
                            f"[Parser] Corrigindo data de parcela: {item['date']} -> {corrected_date.strftime('%Y-%m-%d')} "
                            f"({item.get('description', 'N/A')[:50]})"
                        )
                        item["date"] = corrected_date.strftime("%Y-%m-%d")
                except (ValueError, TypeError) as e:
                    print(f"[Parser] Erro ao corrigir data de parcela: {e}")

            fixed_items.append(item)

        return fixed_items

    def _normalize_card_info(self, card_info: dict) -> dict:
        """Normaliza informacoes do cartao"""
        # Valida card_name para evitar nomes de pessoas
        card_name = card_info.get("card_name")
        if card_name:
            card_name = self._validate_card_name(card_name, card_info)

        # Normalizar datas de fechamento e vencimento
        closing_date = card_info.get("closing_date")
        if closing_date and "YYYY" not in str(closing_date):
            closing_date = self._parse_date(closing_date)
        elif closing_date and "YYYY" in str(closing_date):
            closing_date = None

        due_date = card_info.get("due_date")
        if due_date and "YYYY" not in str(due_date):
            due_date = self._parse_date(due_date)
        elif due_date and "YYYY" in str(due_date):
            due_date = None

        result = {
            "card_issuer": card_info.get("card_issuer"),
            "card_last_digits": str(card_info.get("card_last_digits", ""))[-4:]
            if card_info.get("card_last_digits")
            else None,
            "card_name": card_name,
            "card_bank": card_info.get("card_bank"),
            "card_brand": card_info.get("card_brand"),
            "card_partner": card_info.get("card_partner"),
            "invoice_month": card_info.get("invoice_month"),
            "invoice_year": card_info.get("invoice_year"),
            "closing_date": closing_date,
            "due_date": due_date,
            "total_amount": float(card_info.get("total_amount", 0))
            if card_info.get("total_amount")
            else None,
            "credit_limit": card_info.get("credit_limit"),
            "credit_used": card_info.get("credit_used"),
            "credit_available": card_info.get("credit_available"),
        }

        if result.get("closing_date"):
            try:
                closing = datetime.strptime(result["closing_date"], "%Y-%m-%d")
                result["closing_day"] = closing.day
            except ValueError:
                pass

        if result.get("due_date"):
            try:
                due = datetime.strptime(result["due_date"], "%Y-%m-%d")
                result["due_day"] = due.day
            except ValueError as e:
                print(f"[Parser] Erro ao extrair due_day: {e}")

        return {k: v for k, v in result.items() if v is not None}

    def _validate_card_name(self, card_name: str, card_info: dict) -> str | None:
        """
        Valida se o card_name e realmente um nome de cartao e nao o nome do titular.
        Retorna None se parecer ser nome de pessoa/empresa, ou gera um nome correto.
        """
        if not card_name:
            return None

        card_name_upper = card_name.upper().strip()

        # Sufixos que indicam que e nome de EMPRESA (titular), NAO cartao
        company_suffixes = [
            "LTDA",
            "S.A.",
            "S/A",
            " SA",
            "EIRELI",
            " MEI",
            " ME",
            "CONSULTORIA",
            "SERVICOS",
            "COMERCIO",
            "INFORMATICA",
            "TECNOLOGIA",
            "SISTEMAS",
            "SOLUCOES",
        ]

        # Se contem sufixo de empresa, e nome do titular, nao do cartao
        has_company_suffix = any(suffix in card_name_upper for suffix in company_suffixes)
        if has_company_suffix:
            print(
                f"[Parser] card_name '{card_name}' parece ser nome de empresa/titular, gerando nome do cartao..."
            )
            return self._generate_card_name(card_info)

        # Palavras que indicam que e um nome de cartao valido
        valid_card_keywords = [
            "VISA",
            "MASTERCARD",
            "ELO",
            "HIPERCARD",
            "AMEX",
            "DINERS",
            "GOLD",
            "PLATINUM",
            "BLACK",
            "INFINITE",
            "SIGNATURE",
            "NUBANK",
            "ITAU",
            "BRADESCO",
            "SANTANDER",
            "INTER",
            "C6",
            "AMAZON",
            "SMILES",
            "LATAM",
            "RAPPI",
            "IFOOD",
            "CARTAO",
            "CREDITO",
            "DEBITO",
            "CARD",
        ]

        # Se contem alguma palavra-chave de cartao, provavelmente e valido
        has_card_keyword = any(kw in card_name_upper for kw in valid_card_keywords)
        if has_card_keyword:
            return card_name

        # Verifica se parece ser nome de pessoa (apenas palavras sem numeros/simbolos)
        # Nomes de pessoas geralmente sao 2-4 palavras, todas alfabeticas
        words = card_name_upper.split()
        if len(words) >= 2 and len(words) <= 4:
            # Todas as palavras sao apenas letras (nome de pessoa)
            all_alpha = all(word.replace(" ", "").isalpha() for word in words)
            if all_alpha:
                # Parece ser nome de pessoa - gerar nome do cartao a partir de outros campos
                print(
                    f"[Parser] card_name '{card_name}' parece ser nome de pessoa, gerando nome do cartao..."
                )
                return self._generate_card_name(card_info)

        return card_name

    def _generate_card_name(self, card_info: dict) -> str | None:
        """Gera um nome de cartao a partir dos outros campos disponiveis"""
        parts = []

        # Banco
        issuer = card_info.get("card_issuer") or card_info.get("card_bank")
        if issuer:
            issuer_names = {
                "nubank": "Nubank",
                "itau": "Itaú",
                "bradesco": "Bradesco",
                "santander": "Santander",
                "inter": "Inter",
                "bb": "Banco do Brasil",
                "caixa": "Caixa",
                "c6": "C6 Bank",
                "bradescard": "Bradescard",
            }
            parts.append(issuer_names.get(issuer.lower(), issuer.title()))

        # Parceiro (Amazon, Smiles, etc)
        partner = card_info.get("card_partner")
        if partner:
            parts.append(partner.title())

        # Bandeira
        brand = card_info.get("card_brand")
        if brand:
            parts.append(brand.upper())

        if parts:
            return " ".join(parts)

        return None

    # Mapeamento de labels de pagamento do OCR para PaymentMethod
    PAYMENT_METHOD_MAP = {
        # Vale Alimentação
        "cartao alimentacao": "voucher_va",
        "vale alimentacao": "voucher_va",
        "alimentacao": "voucher_va",
        "alelo alimentacao": "voucher_va",
        "sodexo alimentacao": "voucher_va",
        "ticket alimentacao": "voucher_va",
        "va": "voucher_va",
        # Vale Refeição
        "cartao refeicao": "voucher_vr",
        "vale refeicao": "voucher_vr",
        "refeicao": "voucher_vr",
        "alelo refeicao": "voucher_vr",
        "sodexo refeicao": "voucher_vr",
        "ticket refeicao": "voucher_vr",
        "vr": "voucher_vr",
        # Flex
        "flex": "voucher_flex",
        "cartao flex": "voucher_flex",
        "caju": "voucher_flex",
        "flash": "voucher_flex",
        "ifood beneficios": "voucher_flex",
        "swile": "voucher_flex",
        # Vale Transporte
        "vale transporte": "voucher_vt",
        "vt": "voucher_vt",
        # Outros benefícios
        "alelo": "voucher_other",
        "sodexo": "voucher_other",
        "ticket": "voucher_other",
        "voucher": "voucher_other",
        "vale": "voucher_other",
        "beneficio": "voucher_other",
        # Débito
        "debito": "debit_card",
        "cartao debito": "debit_card",
        "debit": "debit_card",
        "debito a vista": "debit_card",
        # Crédito
        "credito": "credit_card",
        "cartao credito": "credit_card",
        "cartao de credito": "credit_card",
        "credit": "credit_card",
        "credito a vista": "credit_card",
        "credito parcelado": "credit_card",
        # Dinheiro
        "dinheiro": "cash",
        "especie": "cash",
        "cash": "cash",
        # PIX
        "pix": "pix",
        # Transferência
        "transferencia": "bank_transfer",
        "ted": "bank_transfer",
        "doc": "bank_transfer",
    }

    def _normalize_payment_info(self, payment_info: dict, merchant_info: dict = None) -> dict:
        """Normaliza informacoes de pagamento do cupom fiscal"""
        result = {
            "total": None,
            "subtotal": None,
            "discount": None,
            "payments": [],
            "store_name": None,
            "store_cnpj": None,
        }

        # Valores totais
        total = payment_info.get("total") or payment_info.get("total_amount")
        if total:
            result["total"] = float(total)

        subtotal = payment_info.get("subtotal")
        if subtotal:
            result["subtotal"] = float(subtotal)

        discount = payment_info.get("discount") or payment_info.get("desconto")
        if discount:
            result["discount"] = float(discount)

        # Extrair store_name do merchant_info ou payment_info
        if merchant_info:
            result["store_name"] = (
                merchant_info.get("estabelecimento")
                or merchant_info.get("store_name")
                or merchant_info.get("name")
            )
            result["store_cnpj"] = merchant_info.get("cnpj") or merchant_info.get("store_cnpj")

        # Fallback do próprio payment_info
        if not result["store_name"]:
            result["store_name"] = payment_info.get("estabelecimento") or payment_info.get(
                "store_name"
            )
        if not result["store_cnpj"]:
            result["store_cnpj"] = payment_info.get("cnpj") or payment_info.get("store_cnpj")

        # Parse pagamentos
        payments = payment_info.get("payments", [])
        if payments and isinstance(payments, list):
            for i, payment in enumerate(payments):
                if not isinstance(payment, dict):
                    continue

                method_label = payment.get("method", "").lower().strip()
                amount = payment.get("amount", 0)

                if not method_label or not amount:
                    continue

                # Mapear para PaymentMethod enum
                payment_method = self._map_payment_method(method_label)

                result["payments"].append(
                    {
                        "method": payment_method,
                        "amount": float(amount),
                        "label": payment.get("method", ""),  # Label original
                        "sequence": i + 1,
                    }
                )

        print(f"[Parser] DEBUG: payment_info normalized: {result}")
        return result

    def _map_payment_method(self, label: str) -> str:
        """Mapeia label de pagamento do OCR para PaymentMethod enum value"""
        label_lower = label.lower().strip()

        # Remove acentos para facilitar match
        import unicodedata

        label_normalized = unicodedata.normalize("NFD", label_lower)
        label_normalized = label_normalized.encode("ascii", "ignore").decode("utf-8")

        # Busca match direto
        if label_normalized in self.PAYMENT_METHOD_MAP:
            return self.PAYMENT_METHOD_MAP[label_normalized]

        # Busca match parcial
        for key, value in self.PAYMENT_METHOD_MAP.items():
            if key in label_normalized or label_normalized in key:
                return value

        # Default para débito se não reconhecido
        print(f"[Parser] AVISO: Método de pagamento não reconhecido: '{label}', usando debit_card")
        return "debit_card"
