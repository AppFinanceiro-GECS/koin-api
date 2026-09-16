"""Servico de extracao de dados de arquivos CSV e Excel
Suporta formatos de bancos brasileiros: Nubank, Inter, Itau, Bradesco, Santander, BB, etc.

IMPORTANTE: Operacoes de parsing pesado (Excel, CSV grandes) sao executadas
em threads separadas via asyncio.to_thread para nao bloquear o event loop.
"""

import asyncio
import csv
import io
import re
from datetime import datetime


class SpreadsheetParserService:
    """Extrai transacoes de arquivos CSV e Excel de bancos brasileiros"""

    # Mapeamento de colunas por banco/padrao
    COLUMN_MAPPINGS = {
        # Nubank - Fatura cartao
        "nubank_card": {
            "date_cols": ["date", "data"],
            "amount_cols": ["amount", "valor"],
            "desc_cols": ["title", "titulo", "descricao", "descricao"],
            "category_cols": ["category", "categoria"],
        },
        # Nubank - Conta
        "nubank_account": {
            "date_cols": ["data", "date", "data da transacao", "data transacao"],
            "amount_cols": ["valor", "amount", "quantia"],
            "desc_cols": ["descricao", "descricao", "title", "titulo", "nome"],
        },
        # Inter
        "inter": {
            "date_cols": ["data lancamento", "data lancamento", "data"],
            "amount_cols": ["valor", "amount"],
            "desc_cols": ["descricao", "descricao", "historico", "historico"],
        },
        # Itau
        "itau": {
            "date_cols": ["data", "data lancamento"],
            "amount_cols": ["valor", "lancamento"],
            "desc_cols": ["lancamento", "lancamento", "descricao"],
        },
        # Bradesco
        "bradesco": {
            "date_cols": ["data", "data mov.", "data mov"],
            "amount_cols": ["valor", "vlr. r$", "vlr r$"],
            "desc_cols": ["historico", "historico", "descricao"],
        },
        # Santander
        "santander": {
            "date_cols": ["data", "data transacao"],
            "amount_cols": ["valor", "valor (r$)"],
            "desc_cols": ["descricao", "descricao", "historico"],
        },
        # Banco do Brasil
        "bb": {
            "date_cols": ["data", "data balancete"],
            "amount_cols": ["valor", "valor (r$)"],
            "desc_cols": ["historico", "historico", "descricao"],
        },
        # C6 Bank
        "c6": {
            "date_cols": ["data", "data transacao"],
            "amount_cols": ["valor", "amount"],
            "desc_cols": ["descricao", "descricao", "merchant"],
        },
        # OFX converted / Generic
        "generic": {
            "date_cols": [
                "data",
                "date",
                "data lancamento",
                "data_transacao",
                "dt_transacao",
                "posted_date",
            ],
            "amount_cols": ["valor", "amount", "value", "vlr", "quantia", "trnamt"],
            "desc_cols": [
                "descricao",
                "descricao",
                "description",
                "desc",
                "historico",
                "historico",
                "lancamento",
                "lancamento",
                "memo",
                "name",
                "merchant",
                "title",
                "titulo",
                "estabelecimento",
                "nome",
            ],
            "category_cols": ["categoria", "category", "type", "tipo"],
        },
    }

    # Padroes de parcelas para busca em descricoes
    INSTALLMENT_PATTERNS = [
        r"\(Parcela\s+(\d{1,2})\s+de\s+(\d{1,2})\)",  # (Parcela XX de YY)
        r"Parcela\s+(\d{1,2})\s+de\s+(\d{1,2})",  # Parcela X de Y
        r"Parcela\s+(\d{1,2})/(\d{1,2})",  # Parcela X/Y
        r"(\d{1,2})/(\d{1,2})\s*parcelas?",  # X/Y parcelas
        r"\s(\d{2})/(\d{2})(?:\s|$)",  # XX/YY no final
        r"LT(\d{2})/(\d{2})",  # LT02/12
        r"\*\w+(\d{2})/(\d{2})",  # *codigo02/12
        r"Parc\.?\s*(\d{1,2})/(\d{1,2})",  # Parc X/Y ou Parc. X/Y
        r"(\d{1,2})x\s+de\s+(\d{1,2})",  # Xx de Y
    ]

    # Categorias por palavras-chave
    CATEGORY_KEYWORDS = {
        "alimentacao": [
            "restaurante",
            "pizzaria",
            "lanche",
            "delivery",
            "ifood",
            "mc donald",
            "burger",
            "gruta",
            "padaria",
            "cafe",
            "acougue",
            "carne",
            "churrascaria",
            "sushi",
            "japones",
            "comida",
            "almoco",
            "jantar",
            "cozinha",
            "food",
            "rappi",
            "uber eats",
            "ze delivery",
            "aiqfome",
        ],
        "transporte": [
            "posto",
            "uber",
            "99",
            "estacionamento",
            "shellbox",
            "pedagio",
            "combustivel",
            "gasolina",
            "ipiranga",
            "br distribuidora",
            "shell",
            "petrobras",
            "ale",
            "ticket car",
            "sem parar",
            "conectcar",
            "movida",
            "localiza",
            "unidas",
            "metro",
            "onibus",
            "bilhete",
            "vlt",
            "trem",
        ],
        "moradia": [
            "luz",
            "agua",
            "gas",
            "aluguel",
            "condominio",
            "energia",
            "enel",
            "sabesp",
            "neoenergia",
            "cemig",
            "copel",
            "light",
            "celpe",
            "coelba",
            "iptu",
            "taxas",
            "seguro residencial",
            "comgas",
            "naturgy",
        ],
        "saude": [
            "farmacia",
            "hospital",
            "medico",
            "drogaria",
            "droga raia",
            "ultrafarma",
            "panvel",
            "drogasil",
            "pague menos",
            "clinica",
            "laboratorio",
            "exame",
            "consulta",
            "dentista",
            "psic",
            "fisio",
            "unimed",
            "hapvida",
            "sulamerica",
            "bradesco saude",
            "amil",
            "notredame",
        ],
        "lazer": [
            "cinema",
            "teatro",
            "show",
            "ingresso",
            "bar",
            "balada",
            "parque",
            "viagem",
            "hotel",
            "airbnb",
            "booking",
            "decolar",
            "latam",
            "gol",
            "azul",
            "cvc",
            "entretenimento",
            "diversao",
            "passeio",
            "turismo",
        ],
        "streaming": [
            "spotify",
            "netflix",
            "amazon prime",
            "disney",
            "hbomax",
            "max.com",
            "globoplay",
            "paramount",
            "apple tv",
            "youtube premium",
            "deezer",
            "crunchyroll",
            "star+",
            "telecine",
            "discovery",
        ],
        "eletronicos": [
            "magazine",
            "americanas",
            "casas bahia",
            "kabum",
            "pichau",
            "amazon",
            "mercado livre",
            "ml ",
            "aliexpress",
            "shopee",
            "shein",
            "wish",
            "terabyte",
            "ponto frio",
            "submarino",
            "fast shop",
        ],
        "roupas": [
            "renner",
            "c&a",
            "riachuelo",
            "zara",
            "hering",
            "marisa",
            "cea",
            "centauro",
            "netshoes",
            "dafiti",
            "nike",
            "adidas",
            "loja",
            "roupa",
        ],
        "mercado": [
            "supermercado",
            "mercado",
            "atacado",
            "pao de acucar",
            "carrefour",
            "extra",
            "assai",
            "dia",
            "big",
            "walmart",
            "sam's",
            "costco",
            "natural da terra",
            "hortifruti",
            "verdemar",
            "oba",
            "minuto pao",
        ],
        "assinaturas": [
            "assinatura",
            "mensal",
            "anual",
            "subscription",
            "gympass",
            "wellhub",
            "total pass",
            "smart fit",
            "academia",
            "icloud",
            "google one",
            "dropbox",
            "office 365",
            "adobe",
            "canva",
            "notion",
            "linkedin",
        ],
        "educacao": [
            "curso",
            "academy",
            "udemy",
            "coursera",
            "hotmart",
            "escola",
            "faculdade",
            "universidade",
            "livro",
            "livraria",
            "apostila",
            "alura",
            "rocketseat",
            "origamid",
            "descomplica",
        ],
        "servicos": [
            "eletrica",
            "hidraulica",
            "manutencao",
            "instalacao",
            "conserto",
            "limpeza",
            "diarista",
            "pet",
            "veterinario",
            "banho tosa",
            "barbearia",
            "salao",
            "cabeleireiro",
            "estetica",
            "lavanderia",
            "costura",
        ],
        "financeiro": [
            "anuidade",
            "taxa",
            "iof",
            "seguro",
            "tarifa",
            "juros",
            "multa",
            "investimento",
            "aplicacao",
            "resgate",
            "ted",
            "doc",
            "pix",
        ],
    }

    async def parse_file(self, content: bytes, filename: str, mime_type: str) -> dict:
        """Parse arquivo CSV ou Excel e extrai transacoes"""
        try:
            if mime_type in ["text/csv", "application/csv"] or filename.lower().endswith(".csv"):
                return await self._parse_csv(content, filename)
            elif mime_type in [
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.ms-excel",
            ] or filename.lower().endswith((".xlsx", ".xls")):
                return await self._parse_excel(content, filename)
            else:
                return {"items": [], "error": f"Formato nao suportado: {mime_type}"}
        except Exception as e:
            return {"items": [], "error": str(e)}

    def _parse_csv_sync(self, content: bytes, filename: str = "") -> dict:
        """Parse arquivo CSV com deteccao automatica de formato - SINCRONO"""
        # Tentar diferentes encodings
        text = None
        for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]:
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if text is None:
            return {"items": [], "error": "Nao foi possivel decodificar o arquivo CSV"}

        # Remover BOM se existir
        if text.startswith("\ufeff"):
            text = text[1:]

        # Detectar delimitador
        sample = text[:3000]
        delimiter = self._detect_delimiter(sample)

        # Tentar ler CSV
        try:
            # Primeiro tenta com DictReader
            reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
            rows = list(reader)

            if not rows:
                return {"items": [], "error": "Arquivo CSV vazio ou sem dados validos"}

            # Detectar mapeamento de colunas
            headers = list(rows[0].keys()) if rows else []
            column_mapping = self._detect_column_mapping(headers)

            if not column_mapping:
                # Tentar detectar pelo nome do arquivo
                column_mapping = self._detect_bank_from_filename(filename, headers)

            if not column_mapping:
                return {
                    "items": [],
                    "error": f"Nao foi possivel identificar as colunas. Colunas encontradas: {', '.join(headers[:10])}",
                }

            # Extrair transacoes
            items = []
            for row in rows:
                item = self._extract_transaction(row, column_mapping)
                if item:
                    items.append(item)

            if not items:
                return {
                    "items": [],
                    "error": "Nenhuma transacao valida encontrada. Verifique se o arquivo contem dados de transacoes.",
                }

            return {
                "items": items,
                "document_type": "extrato",
            }

        except csv.Error as e:
            return {"items": [], "error": f"Erro ao processar CSV: {str(e)}"}

    async def _parse_csv(self, content: bytes, filename: str = "") -> dict:
        """Parse arquivo CSV - executa em thread separada para nao bloquear"""
        return await asyncio.to_thread(self._parse_csv_sync, content, filename)

    def _parse_excel_sync(self, content: bytes, filename: str) -> dict:
        """Parse arquivo Excel - SINCRONO"""
        try:
            import openpyxl
        except ImportError:
            return {"items": [], "error": "Biblioteca openpyxl nao instalada"}

        try:
            workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
            sheet = workbook.active

            # Extrair headers
            headers = []
            for cell in sheet[1]:
                val = str(cell.value).lower().strip() if cell.value else ""
                headers.append(val)

            # Detectar mapeamento
            column_mapping = self._detect_column_mapping(headers)
            if not column_mapping:
                column_mapping = self._detect_bank_from_filename(filename, headers)

            if not column_mapping:
                return {"items": [], "error": f"Nao foi possivel identificar as colunas: {headers}"}

            items = []
            for row in sheet.iter_rows(min_row=2, values_only=True):
                row_dict = {}
                for i, val in enumerate(row):
                    if i < len(headers):
                        row_dict[headers[i]] = val
                item = self._extract_transaction(row_dict, column_mapping)
                if item:
                    items.append(item)

            return {
                "items": items,
                "document_type": "extrato",
            }
        except Exception as e:
            return {"items": [], "error": f"Erro ao processar Excel: {str(e)}"}

    async def _parse_excel(self, content: bytes, filename: str) -> dict:
        """Parse arquivo Excel - executa em thread separada para nao bloquear"""
        return await asyncio.to_thread(self._parse_excel_sync, content, filename)

    def _detect_delimiter(self, sample: str) -> str:
        """Detecta o delimitador do CSV"""
        # Conta ocorrencias de delimitadores comuns
        delimiters = {",": 0, ";": 0, "\t": 0, "|": 0}

        for line in sample.split("\n")[:5]:
            for d in delimiters:
                delimiters[d] += line.count(d)

        # Retorna o mais comum
        return max(delimiters, key=delimiters.get) if max(delimiters.values()) > 0 else ","

    def _detect_column_mapping(self, headers: list) -> dict | None:
        """Detecta automaticamente o mapeamento de colunas baseado nos headers"""
        headers_lower = [h.lower().strip() if h else "" for h in headers]

        # Tenta cada padrao de banco
        for bank_name, mapping in self.COLUMN_MAPPINGS.items():
            date_col = None
            amount_col = None
            desc_col = None
            category_col = None

            # Encontrar coluna de data
            for col in mapping.get("date_cols", []):
                if col in headers_lower:
                    date_col = headers[headers_lower.index(col)]
                    break

            # Encontrar coluna de valor
            for col in mapping.get("amount_cols", []):
                if col in headers_lower:
                    amount_col = headers[headers_lower.index(col)]
                    break

            # Encontrar coluna de descricao
            for col in mapping.get("desc_cols", []):
                if col in headers_lower:
                    desc_col = headers[headers_lower.index(col)]
                    break

            # Encontrar coluna de categoria (opcional)
            for col in mapping.get("category_cols", []):
                if col in headers_lower:
                    category_col = headers[headers_lower.index(col)]
                    break

            # Se encontrou os campos obrigatorios
            if date_col and amount_col and desc_col:
                return {
                    "date": date_col,
                    "amount": amount_col,
                    "description": desc_col,
                    "category": category_col,
                    "bank": bank_name,
                }

        return None

    def _detect_bank_from_filename(self, filename: str, headers: list) -> dict | None:
        """Tenta detectar o banco pelo nome do arquivo"""
        filename_lower = filename.lower()

        bank_keywords = {
            "nubank": ["nubank", "nu_"],
            "inter": ["inter", "banco inter"],
            "itau": ["itau", "itau"],
            "bradesco": ["bradesco"],
            "santander": ["santander"],
            "bb": ["bb_", "banco do brasil", "bancodobrasil"],
            "c6": ["c6", "c6bank"],
        }

        for bank, keywords in bank_keywords.items():
            for keyword in keywords:
                if keyword in filename_lower:
                    # Usa o mapeamento generico como fallback
                    return self._detect_column_mapping(headers)

        # Se nao identificou, tenta o mapeamento generico
        return self._detect_column_mapping(headers)

    def _extract_transaction(self, row: dict, mapping: dict) -> dict | None:
        """Extrai transacao de uma linha usando o mapeamento detectado"""
        try:
            # Normalizar keys
            row_normalized = {k.lower().strip() if k else "": v for k, v in row.items()}

            # Obter valores
            date_key = mapping["date"].lower() if mapping.get("date") else None
            amount_key = mapping["amount"].lower() if mapping.get("amount") else None
            desc_key = mapping["description"].lower() if mapping.get("description") else None
            cat_key = mapping.get("category", "").lower() if mapping.get("category") else None

            date_val = row_normalized.get(date_key) if date_key else None
            amount_val = row_normalized.get(amount_key) if amount_key else None
            desc_val = row_normalized.get(desc_key) if desc_key else None
            cat_val = row_normalized.get(cat_key) if cat_key else None

            # Parse valores
            date = self._parse_date(date_val)
            amount = self._parse_amount(amount_val)
            description = str(desc_val).strip() if desc_val else None

            # Validar campos obrigatorios
            if not description or amount is None or amount == 0:
                return None

            # Detectar parcelas
            is_installment, inst_current, inst_total = self._detect_installment(description)

            # Limpar descricao
            clean_desc = self._clean_description(description)

            # Detectar categoria
            category = str(cat_val).strip().lower() if cat_val else None
            if not category or category in ["", "none", "nan", "-"]:
                category = self._detect_category(clean_desc)

            return {
                "description": clean_desc[:200],
                "amount": abs(amount),  # Sempre positivo, despesa e inferida pelo contexto
                "date": date,
                "category": category,
                "confidence": 0.85,
                "is_installment": is_installment,
                "installment_current": inst_current,
                "installment_total": inst_total,
            }
        except Exception:
            return None

    def _parse_amount(self, value) -> float | None:
        """Converte valor para float com suporte a formatos brasileiros"""
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            clean = value.strip()

            # Remove simbolos de moeda
            clean = re.sub(r"[R$\s]", "", clean)

            # Detecta negativo
            is_negative = "-" in clean or clean.startswith("(") or clean.endswith(")")
            clean = clean.replace("-", "").replace("(", "").replace(")", "").strip()

            if not clean:
                return None

            # Formato brasileiro: 1.234,56
            if "," in clean and "." in clean:
                if clean.rfind(",") > clean.rfind("."):
                    clean = clean.replace(".", "").replace(",", ".")
                else:
                    clean = clean.replace(",", "")
            elif "," in clean:
                # Apenas virgula: pode ser decimal ou milhar
                parts = clean.split(",")
                if len(parts) == 2 and len(parts[1]) <= 2:
                    clean = clean.replace(",", ".")
                else:
                    clean = clean.replace(",", "")

            try:
                amount = float(clean)
                return -amount if is_negative else amount
            except ValueError:
                return None

        return None

    def _parse_date(self, value) -> str | None:
        """Converte data para formato YYYY-MM-DD"""
        if value is None:
            return None

        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")

        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")

        if isinstance(value, str):
            value = value.strip()

            formats = [
                "%d/%m/%Y",
                "%d-%m-%Y",
                "%Y-%m-%d",
                "%d/%m/%y",
                "%d-%m-%y",
                "%Y/%m/%d",
                "%m/%d/%Y",
                "%d %b %Y",
                "%d %B %Y",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ",
            ]

            for fmt in formats:
                try:
                    dt = datetime.strptime(value[: len(fmt) + 5], fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue

            # Regex fallback
            match = re.search(r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})", value)
            if match:
                d, m, y = match.groups()
                if len(y) == 2:
                    y = "20" + y if int(y) < 50 else "19" + y
                try:
                    return f"{y}-{m.zfill(2)}-{d.zfill(2)}"
                except Exception:
                    pass

        return None

    def _detect_installment(self, description: str) -> tuple:
        """Detecta informacoes de parcela na descricao"""
        for pattern in self.INSTALLMENT_PATTERNS:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                try:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    if 1 <= current <= total <= 99:
                        return (True, current, total)
                except (ValueError, IndexError):
                    continue
        return (False, None, None)

    def _clean_description(self, description: str) -> str:
        """Remove codigos e padroes da descricao"""
        clean = description

        # Remove padroes de parcela
        patterns = [
            r"\(Parcela\s+\d{1,2}\s+de\s+\d{1,2}\)",
            r"Parcela\s+\d{1,2}\s+de\s+\d{1,2}",
            r"Parcela\s+\d{1,2}/\d{1,2}",
            r"\s\d{2}/\d{2}(?:\s|$)",
            r"LT\d{2}/\d{2}",
            r"\*\w+\d{2}/\d{2}",
            r"Parc\.?\s*\d{1,2}/\d{1,2}",
        ]

        for pattern in patterns:
            clean = re.sub(pattern, " ", clean, flags=re.IGNORECASE)

        # Remove codigos comuns
        clean = re.sub(r"\*\w{3,}", "", clean)
        clean = re.sub(r"DM\s*\*", "", clean)
        clean = re.sub(r"PG\s*\*", "", clean)
        clean = re.sub(r"PAG\s*\*", "", clean)
        clean = re.sub(r"\s{2,}", " ", clean)

        return clean.strip() or description[:100]

    def _detect_category(self, description: str) -> str:
        """Detecta categoria baseado em palavras-chave"""
        desc_lower = description.lower()

        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in desc_lower:
                    return category

        return "outros"
