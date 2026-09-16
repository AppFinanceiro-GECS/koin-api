"""Validacao e limpeza de dados extraidos de faturas"""

import re

# Padroes de descricao que indicam totais/resumos (nao sao transacoes reais)
INVALID_DESCRIPTIONS = [
    "despesas do mes",
    "fatura atual",
    "total da fatura",
    "total da fatura em real",
    "total para ",
    "valor do documento",
    "pagamento minimo",
    "parcelamento fatura",
    "parcelamento total",
    "limite disponivel",
    "limite total",
    "proxima fatura",
    "proximas parcelas",
    "pagamento banco csf",
    "pag boleto bancario",
    "inclusao pgto fatura",
    "saldo anterior",
    "saldo fatura anterior",
    "parcela de anuidade",
    "anuidade parcelada",
    "total anuidade",
]

# Padroes que indicam pagamento de fatura (deve ter valor NEGATIVO)
PAYMENT_PATTERNS = [
    "pagamento em ",
    "pagamento de fatura",
    "pag fatura",
    "pgto fatura",
    "pgto cobranca",
    "pagamento efetuado",
    "pgto debito automatico",
    "pagamento recebido",
    "credito pagamento",
]

# Padroes que indicam subtotais/headers de secao (NAO sao transacoes reais)
SECTION_HEADER_PATTERNS = [
    # Nomes de empresas/titulares que aparecem como headers de secao
    r"^[A-Z\s]+LTDA$",
    r"^[A-Z\s]+S\.?A\.?$",
    r"^[A-Z\s]+EIRELI$",
    r"^[A-Z\s]+MEI$",
    r"^[A-Z\s]+ME$",
    # Headers comuns de secoes Nubank
    r"pagamentos e financiamentos",
    r"transacoes de \d+ [a-z]+ a \d+ [a-z]+",
]


class ExtractionValidator:
    """Valida e corrige dados extraidos de faturas"""

    def validate_and_clean(
        self,
        items: list,
        card_info: dict | None,
        document_type: str | None = None,
        total_amount: float | None = None,
        ocr_text: str | None = None,
    ) -> list:
        """Aplica todas as validacoes e limpezas nos itens extraidos

        Args:
            items: Lista de itens extraidos
            card_info: Informacoes do cartao/documento
            document_type: Tipo do documento ('fatura_cartao' ou 'cupom_fiscal')
            total_amount: Total do cupom fiscal (para diluicao de desconto)
        """
        if not items:
            return items

        is_cupom_fiscal = document_type == "cupom_fiscal"

        # Pipeline de validacao - primeiro remove itens invalidos
        items = self.remove_section_headers(items, card_info)
        items = self.remove_addresses_and_boleto_data(items)
        items = self.fix_payment_amounts(items)

        if not is_cupom_fiscal:
            # Filtrar pagamentos de fatura anterior (apenas para faturas de cartao)
            items = self.filter_previous_invoice_payments(items, card_info)

        if is_cupom_fiscal:
            # Remover duplicatas de overlap usando total como validação
            # NÃO usar deduplicação consecutiva pois remove compras reais
            # (ex: cliente comprou 2 do mesmo produto um após o outro)
            items = self.deduplicate_by_total(items, total_amount)
            # Diluir desconto em cupons fiscais
            items = self.dilute_discount_to_items(items, total_amount)
        else:
            # Validacoes especificas de faturas de cartao
            items = self.fix_inverted_sign_convention(items, card_info)
            items = self.fix_iof_sign(items)
            items = self.fix_bradesco_installments(items, card_info)
            items = self.filter_duplicate_installments(items)
            items = self.filter_consecutive_installments(items)
            items = self.remove_cancelled_purchases(items, card_info)
            items = self.fix_hidden_credits(items, card_info)

        items = self.remove_total_items(items, card_info)
        items = self.fix_suspicious_installments(items)

        total_for_filter = card_info.get("total_amount") if card_info else total_amount
        items = self.filter_summary_items(items, total_for_filter)

        # Corrigir datas usando texto OCR (pós todas as outras validações)
        if not is_cupom_fiscal and ocr_text:
            items = self.fix_dates_from_ocr_text(items, card_info, ocr_text)
            items = self.fix_nubank_dates(items, card_info, ocr_text)

        return items

    def deduplicate_consecutive_items(self, items: list) -> list:
        """
        Remove itens consecutivos idênticos (causados por overlap na divisão de páginas longas).
        Mantém duplicatas não consecutivas (compras reais do mesmo produto).
        """
        if not items or len(items) < 2:
            return items

        result = [items[0]]

        for i in range(1, len(items)):
            current = items[i]
            previous = items[i - 1]

            # Verificar se é duplicata consecutiva (mesma descrição, valor e data)
            is_duplicate = (
                current.get("description") == previous.get("description")
                and current.get("amount") == previous.get("amount")
                and current.get("date") == previous.get("date")
            )

            if is_duplicate:
                print(
                    f"[Validator] Removendo item duplicado consecutivo: {current.get('description', '')[:30]}"
                )
            else:
                result.append(current)

        if len(result) < len(items):
            print(f"[Validator] Deduplicação consecutiva: {len(items)} -> {len(result)} itens")

        return result

    def deduplicate_by_total(self, items: list, total_amount: float | None) -> list:
        """
        Remove duplicatas de overlap usando o total como validação.

        Algoritmo:
        1. Calcular soma atual dos itens
        2. Se soma > total (com tolerância), há duplicatas de overlap
        3. Agrupar itens por (descrição, valor, data)
        4. Para grupos com >1 item, remover extras até soma ≈ total
        """
        if not items or len(items) < 2 or not total_amount:
            return items

        soma_atual = sum(item.get("amount", 0) for item in items)
        diferenca = soma_atual - total_amount

        # Se soma está próxima do total (±1%), não há duplicatas significativas
        if abs(diferenca) <= total_amount * 0.01:
            print(
                f"[Validator] Soma ({soma_atual:.2f}) próxima do total ({total_amount:.2f}), sem dedup necessária"
            )
            return items

        # Se soma < total, não há duplicatas (pode haver itens faltando)
        if diferenca < 0:
            print(
                f"[Validator] Soma ({soma_atual:.2f}) menor que total ({total_amount:.2f}), itens podem estar faltando"
            )
            return items

        print(
            f"[Validator] Possíveis duplicatas: soma={soma_atual:.2f}, total={total_amount:.2f}, excesso={diferenca:.2f}"
        )

        # Agrupar itens por (descrição, valor, data)
        from collections import defaultdict

        groups = defaultdict(list)
        for idx, item in enumerate(items):
            key = (item.get("description", ""), item.get("amount", 0), item.get("date", ""))
            groups[key].append(idx)

        # Identificar grupos com duplicatas (>1 item)
        duplicates_candidates = []
        for key, indices in groups.items():
            if len(indices) > 1:
                # Adicionar índices extras (exceto o primeiro)
                for idx in indices[1:]:
                    duplicates_candidates.append((idx, items[idx].get("amount", 0)))

        if not duplicates_candidates:
            return items

        # Ordenar por valor (remover duplicatas maiores primeiro para aproximar do total mais rápido)
        duplicates_candidates.sort(key=lambda x: -x[1])

        # Remover duplicatas até soma ≈ total
        indices_to_remove = set()
        soma_removida = 0

        for idx, amount in duplicates_candidates:
            if soma_atual - soma_removida - amount >= total_amount - (total_amount * 0.01):
                indices_to_remove.add(idx)
                soma_removida += amount
                print(
                    f"[Validator] Removendo duplicata: {items[idx].get('description', '')[:40]} R${amount:.2f}"
                )

            # Parar se já removemos o suficiente
            if abs((soma_atual - soma_removida) - total_amount) <= total_amount * 0.01:
                break

        if indices_to_remove:
            result = [item for idx, item in enumerate(items) if idx not in indices_to_remove]
            nova_soma = sum(item.get("amount", 0) for item in result)
            print(
                f"[Validator] Deduplicação por total: {len(items)} -> {len(result)} itens (soma: {soma_atual:.2f} -> {nova_soma:.2f})"
            )
            return result

        return items

    def dilute_discount_to_items(self, items: list, total_amount: float | None) -> list:
        """Dilui desconto proporcionalmente entre itens de cupom fiscal."""
        if not total_amount or total_amount <= 0:
            return items

        # Filtrar itens de compra (positivos)
        compra_items = [i for i in items if i.get("amount", 0) > 0]
        if not compra_items:
            return items

        soma_items = sum(i.get("amount", 0) for i in compra_items)
        diferenca = soma_items - total_amount

        # Se diferenca <= 0.01, nao ha desconto
        if diferenca <= 0.01:
            return items

        print(
            f"[Validator] Desconto detectado: soma={soma_items:.2f}, total={total_amount:.2f}, desconto={diferenca:.2f}"
        )

        # Distribuir proporcionalmente
        for item in compra_items:
            amount = item.get("amount", 0)
            if amount > 0 and soma_items > 0:
                proporcao = amount / soma_items
                desconto_item = round(diferenca * proporcao, 2)

                # Garantir amount >= 0.01
                novo_amount = max(0.01, round(amount - desconto_item, 2))
                desconto_real = round(amount - novo_amount, 2)

                item["original_amount"] = amount
                item["discount_amount"] = desconto_real
                item["amount"] = novo_amount

                print(
                    f"[Validator] {item['description'][:30]}: {amount:.2f} -> {novo_amount:.2f} (desc: {desconto_real:.2f})"
                )

        return items

    def is_invalid_description(self, description: str) -> bool:
        """Verifica se a descricao e um total/resumo ao inves de uma transacao real"""
        desc_lower = description.lower().strip()

        for invalid in INVALID_DESCRIPTIONS:
            if invalid in desc_lower or desc_lower in invalid:
                return True

        if re.match(r"^total\s+(para\s+)?[a-z\s]+$", desc_lower):
            return True

        if "total" in desc_lower and ("fatura" in desc_lower or "real" in desc_lower):
            return True

        return False

    def remove_section_headers(self, items: list, card_info: dict | None) -> list:
        """Remove itens que sao headers de secao ou subtotais (nao transacoes reais).

        Exemplos de headers que devem ser removidos:
        - "KAS S C T LTDA" R$ 679,49 (subtotal de secao no Nubank)
        - Nomes de empresas/titulares que aparecem como headers
        """
        if not items:
            return items

        result = []
        total_amount = card_info.get("total_amount") if card_info else None

        for item in items:
            desc = item.get("description", "").strip()
            desc_upper = desc.upper()
            amount = item.get("amount", 0)
            has_date = item.get("date") is not None

            is_section_header = False

            # Detectar nomes de empresa com sufixos (LTDA, S.A., EIRELI, MEI, ME)
            company_suffix_pattern = r"\s+(LTDA|S\.?A\.?|EIRELI|MEI|ME)$"
            has_company_suffix = bool(re.search(company_suffix_pattern, desc_upper))

            # REGRA PRINCIPAL: Se tem sufixo de empresa E tem data, e uma compra legitima
            # NAO deve ser removido como header, independente de outros padroes
            if has_company_suffix and has_date:
                # Transacao legitima com data - manter
                result.append(item)
                continue

            # Verificar padroes de headers de secao (apenas para itens SEM data)
            for pattern in SECTION_HEADER_PATTERNS:
                if re.match(pattern, desc_upper) or re.match(pattern, desc.lower()):
                    is_section_header = True
                    break

            # Para itens com sufixo de empresa SEM data, aplicar regras adicionais
            if has_company_suffix and amount > 0 and not has_date:
                has_merchant_chars = bool(
                    re.search(r"[\d\*\-]", desc)
                )  # Merchants tem numeros, *, -
                is_all_caps_simple = desc == desc.upper() and not has_merchant_chars
                is_total_value = total_amount and abs(amount - total_amount) < 1.0

                # Marcar como header se:
                # - Valor igual ao total (e um subtotal de secao)
                # - OU e all caps simples sem caracteres de merchant
                if is_total_value:
                    is_section_header = True
                elif is_all_caps_simple:
                    is_section_header = True

            if is_section_header:
                print(f"[Validator] Removendo header de secao: '{desc}' R${amount:.2f}")
            else:
                result.append(item)

        if len(result) < len(items):
            print(f"[Validator] Removidos {len(items) - len(result)} headers de secao")

        return result

    def filter_previous_invoice_payments(self, items: list, card_info: dict | None) -> list:
        """Remove pagamentos que sao da fatura anterior (nao da atual).

        Na fatura Nubank, o "Pagamento em XX DEZ" que aparece no resumo
        e o pagamento da fatura ANTERIOR, nao deve ser contabilizado
        como transacao da fatura atual.

        Logica: Se remover um pagamento de fatura e a soma das compras
        restantes ficar proxima do total_amount, esse pagamento e da fatura anterior.
        """
        if not items or not card_info:
            return items

        total_amount = card_info.get("total_amount")
        if not total_amount:
            return items

        # Identificar pagamentos de fatura (com descricoes tipicas)
        pagamentos_fatura = []
        outros_items = []

        for item in items:
            desc_lower = item.get("description", "").lower()
            is_invoice_payment = item.get("transaction_type") == "pagamento" and any(
                p in desc_lower
                for p in [
                    "pagamento em",
                    "pagamento recebido",
                    "pgto fatura",
                    "pagamento de fatura",
                    "credito pagamento",
                    "pag fatura",
                ]
            )

            if is_invoice_payment:
                pagamentos_fatura.append(item)
            else:
                outros_items.append(item)

        if not pagamentos_fatura:
            return items

        # Calcular soma das compras (tudo exceto pagamentos de fatura)
        soma_compras = sum(i.get("amount", 0) for i in outros_items)

        # Se a soma das compras ja esta proxima do total, remover pagamentos de fatura anterior
        if abs(soma_compras - total_amount) < 50:
            # Os pagamentos de fatura sao da fatura anterior - remover
            for pag in pagamentos_fatura:
                print(
                    f"[Validator] Removendo pagamento de fatura anterior: '{pag['description']}' R${pag['amount']:.2f}"
                )
            print(
                f"[Validator] Soma das compras: R${soma_compras:.2f} ≈ total fatura: R${total_amount:.2f}"
            )
            return outros_items

        # Se nao, verificar se algum pagamento especifico pode ser da fatura anterior
        items_to_keep = []
        removed_any = False

        for pag in pagamentos_fatura:
            # Se remover este pagamento, a soma fica proxima do total?
            soma_sem_este = soma_compras
            if abs(soma_sem_este - total_amount) < 50:
                print(
                    f"[Validator] Removendo pagamento de fatura anterior: '{pag['description']}' R${pag['amount']:.2f}"
                )
                removed_any = True
            else:
                items_to_keep.append(pag)

        if removed_any:
            return outros_items + items_to_keep

        return items

    def fix_payment_amounts(self, items: list) -> list:
        """Corrige pagamentos que vieram com valor positivo."""
        for item in items:
            desc_lower = item.get("description", "").lower()
            amount = item.get("amount", 0)

            is_payment_pattern = any(pattern in desc_lower for pattern in PAYMENT_PATTERNS)
            is_payment_type = item.get("transaction_type") == "pagamento"

            if (is_payment_pattern or is_payment_type) and amount > 0:
                is_likely_merchant = any(
                    word in desc_lower
                    for word in [
                        "prime",
                        "global",
                        "servicos",
                        "comercio",
                        "ltda",
                        "eireli",
                        "me ",
                        " sa",
                    ]
                )

                if not is_likely_merchant:
                    print(
                        f"[Validator] Fixing payment amount: '{item['description']}' {amount} -> {-amount}"
                    )
                    item["amount"] = -amount
                    item["transaction_type"] = "pagamento"
                    item["category"] = "pagamento"

        return items

    def fix_iof_sign(self, items: list) -> list:
        """Corrige IOF extraido com valor negativo — IOF é sempre encargo POSITIVO."""
        if not items:
            return items

        for item in items:
            desc = (item.get("description") or "").lower()
            if "iof" in desc:
                amount = item.get("amount", 0)
                if amount < 0:
                    print(
                        f"[Validator] IOF com valor negativo corrigido: '{item.get('description', '')[:40]}' {amount} -> {-amount}"
                    )
                    item["amount"] = -amount
                if item.get("transaction_type") not in ("encargo",):
                    item["transaction_type"] = "encargo"
                item["is_installment"] = False

        return items

    def fix_inverted_sign_convention(self, items: list, card_info: dict | None) -> list:
        """Corrige emissores que usam convencao invertida de sinais."""
        if not items:
            return items

        INVERTED_ISSUERS = ["leroymerlin", "celebre", "pefisa"]
        card_issuer = (card_info.get("card_issuer") or "").lower() if card_info else ""

        compras = [
            i for i in items if i.get("transaction_type") in ("compra", "anuidade", "encargo")
        ]

        compras_negativas = sum(1 for c in compras if c.get("amount", 0) < 0)

        is_known_inverted = any(issuer in card_issuer for issuer in INVERTED_ISSUERS)

        auto_detect_inverted = len(compras) > 0 and compras_negativas / len(compras) > 0.7

        if auto_detect_inverted:
            reason = (
                f"emissor conhecido ({card_issuer})" if is_known_inverted else "deteccao automatica"
            )
            print(f"[Validator] Convencao de sinais invertida detectada ({reason}). Corrigindo...")

            for item in items:
                amount = item.get("amount", 0)
                if amount != 0:
                    item["amount"] = -amount
                    print(
                        f"[Validator] Invertendo: '{item.get('description', '')[:30]}' {amount} -> {-amount}"
                    )

        return items

    def fix_bradesco_installments(self, items: list, card_info: dict | None) -> list:
        """Corrige parcelamentos em faturas Bradesco/AMEX onde a informacao esta concatenada."""
        if not items:
            return items

        card_issuer = (card_info.get("card_issuer") or "").lower() if card_info else ""
        card_name = (card_info.get("card_name") or "").lower() if card_info else ""
        card_bank = (card_info.get("card_bank") or "").lower() if card_info else ""

        is_bradesco = (
            "bradesco" in card_issuer
            or "bradesco" in card_name
            or "bradesco" in card_bank
            or "bradescard" in card_issuer
            or "bradescard" in card_name
        )

        if not is_bradesco:
            return items

        print("[Validator] Detectado Bradesco, verificando parcelamentos concatenados...")

        pattern = re.compile(r"(\d{1,2})/(\d{1,2})$")

        fixed_count = 0
        for item in items:
            if (
                item.get("is_installment")
                and item.get("installment_current")
                and item.get("installment_total")
            ):
                if item.get("installment_total", 0) > 1:
                    continue

            if item.get("transaction_type") not in ["compra", None]:
                continue

            description = item.get("description", "")
            match = pattern.search(description)

            if match:
                current = int(match.group(1))
                total = int(match.group(2))

                if 1 <= current <= total <= 48:
                    clean_desc = description[: match.start()]

                    clean_desc_strip = clean_desc.rstrip()
                    letter_suffix = re.search(r" ([A-Z]{1,3})$", clean_desc_strip)
                    if letter_suffix:
                        clean_desc = clean_desc_strip[: letter_suffix.start()]

                    clean_desc = clean_desc.rstrip("*- ")

                    if len(clean_desc.strip()) < 3:
                        clean_desc = description[: match.start()].rstrip("*- ")

                    print(
                        f"[Validator] Parcelamento extraido: '{description}' -> '{clean_desc.strip()}' ({current}/{total})"
                    )

                    item["description"] = clean_desc.strip() if clean_desc.strip() else description
                    item["is_installment"] = True
                    item["installment_current"] = current
                    item["installment_total"] = total
                    fixed_count += 1

        if fixed_count > 0:
            print(f"[Validator] Total de {fixed_count} parcelamentos corrigidos (Bradesco/AMEX)")

        return items

    def fix_hidden_credits(self, items: list, card_info: dict | None) -> list:
        """Detecta itens que deveriam ser créditos/estornos mas estão com valor positivo.

        Quando a soma dos itens é MAIOR que o total_amount, verifica se inverter o sinal
        de algum item faz a soma bater. Isso acontece em faturas Bradesco onde o OCR
        não captura o '-' após o valor de créditos.
        """
        if not items or not card_info:
            return items

        total_amount = card_info.get("total_amount")
        if not total_amount or total_amount <= 0:
            return items

        # Calcular soma atual (apenas positivos)
        items_sum = sum(item.get("amount", 0) for item in items if item.get("amount", 0) > 0)

        diff = items_sum - total_amount

        # Se soma está acima do total por mais de R$10
        if diff < 10:
            return items

        # Verificar se inverter o sinal de um item fecha a conta
        # Quando +X vira -X, a soma muda em 2*X
        target_amount = diff / 2.0

        best_match = None
        best_diff = float("inf")

        for item in items:
            amount = item.get("amount", 0)
            if amount <= 0:
                continue
            # Não inverter parcelas (são compras reais)
            if item.get("is_installment"):
                continue

            item_diff = abs(amount - target_amount)
            if item_diff < best_diff and item_diff < 1.0:  # tolerância de R$1
                best_diff = item_diff
                best_match = item

        if best_match:
            old_amount = best_match["amount"]
            best_match["amount"] = -old_amount
            best_match["transaction_type"] = "credito"

            new_sum = items_sum - 2 * old_amount
            print(
                f"[Validator] Crédito oculto detectado: '{best_match.get('description', '')[:40]}' "
                f"R${old_amount:.2f} -> R${-old_amount:.2f} "
                f"(soma: {items_sum:.2f} -> {new_sum:.2f}, total: {total_amount:.2f})"
            )

        return items

    def _normalize_description(self, desc: str) -> str:
        """Normaliza descricao para comparacao"""
        desc = desc.lower()
        prefixes = [
            "mercadolivre*",
            "mercadolivre ",
            "mercadolivre",
            "mercado*",
            "mercado ",
            "mercado",
            "pag*",
            "pag ",
            "mp*",
            "mp ",
            "dl*",
            "dl ",
            "cp*",
            "cp ",
            "pg*",
            "pg ",
        ]
        for prefix in prefixes:
            if desc.startswith(prefix):
                desc = desc[len(prefix) :]
                break
        desc = re.sub(r"[^a-z]", "", desc)
        return desc

    def filter_duplicate_installments(self, items: list) -> list:
        """Remove parcelas duplicadas, mantendo apenas a de menor numero"""
        seen_exact = set()
        unique_items = []
        for item in items:
            # Incluir data na chave para nao remover compras diferentes no mesmo valor/parcela
            exact_key = (
                self._normalize_description(item["description"]),
                item["amount"],
                item.get("installment_current"),
                item.get("installment_total"),
                item.get("date"),  # Importante: compras em datas diferentes sao distintas
            )
            if exact_key not in seen_exact:
                seen_exact.add(exact_key)
                unique_items.append(item)

        # Agrupar por (desc, amount, date, installment) para manter compras diferentes em datas diferentes
        # CRITICAL: Incluir número da parcela na chave para não remover parcelas consecutivas!
        # Ex: "MOTOCHEFE 07/12" e "MOTOCHEFE 08/12" são diferentes!
        groups = {}
        for item in unique_items:
            desc_normalized = self._normalize_description(item["description"])
            # IMPORTANTE: Incluir número e total da parcela na chave
            # Isso evita remover parcelas consecutivas que aparecem na mesma fatura
            key = (
                desc_normalized,
                item["amount"],
                item.get("date"),
                item.get("installment_current"),  # ✅ ADICIONADO
                item.get("installment_total"),  # ✅ ADICIONADO
            )
            if key not in groups:
                groups[key] = []
            groups[key].append(item)

        filtered = []
        for key, group in groups.items():
            if len(group) == 1:
                filtered.append(group[0])
            else:
                # Multiplas parcelas da mesma compra (mesmo desc, amount, date)
                # Manter apenas a de menor numero
                installment_items = [i for i in group if i.get("is_installment")]
                non_installment_items = [i for i in group if not i.get("is_installment")]

                if installment_items:
                    installment_items.sort(key=lambda x: x.get("installment_current", 999))
                    filtered.append(installment_items[0])
                elif non_installment_items:
                    filtered.append(non_installment_items[0])

        # Nota: A logica de remover creditos/estornos que tem parcelas relacionadas foi removida
        # pois era muito agressiva e removia creditos legitimos (ex: cashback, devolucoes parciais).
        # A funcao remove_cancelled_purchases ja faz a remocao de estornos de forma mais inteligente,
        # verificando se o valor do estorno corresponde ao total das parcelas.
        return filtered

    def filter_summary_items(self, items: list, total_amount: float | None) -> list:
        """Remove itens que sao resumos/totais da fatura"""
        if not total_amount or total_amount <= 0:
            return items

        filtered = []
        for item in items:
            if abs(item["amount"] - total_amount) < 0.01:
                desc_lower = item["description"].lower()
                if any(word in desc_lower for word in ["anuidade", "total", "fatura", "valor"]):
                    continue

            desc_lower = item["description"].lower().strip()
            if desc_lower in ["anuidade", "parcela anuidade", "parcela de anuidade"]:
                if item["amount"] > 50:
                    continue

            filtered.append(item)

        return filtered

    def fix_suspicious_installments(self, items: list) -> list:
        """Corrige parcelas suspeitas onde installment_total=1"""
        suspicious = [
            item
            for item in items
            if item.get("is_installment")
            and item.get("installment_current") == 1
            and item.get("installment_total") == 1
        ]

        if suspicious:
            for item in suspicious:
                print(
                    f"[Validator] WARNING: Suspicious 1/1 installment: {item.get('description')} R${item.get('amount')}"
                )

        return items

    def filter_consecutive_installments(self, items: list) -> list:
        """Agrupa parcelas consecutivas do mesmo estabelecimento em um unico item."""
        if not items:
            return items

        non_installment_items = [i for i in items if not i.get("is_installment")]
        installment_items = [i for i in items if i.get("is_installment")]

        if not installment_items:
            return items

        groups = {}
        for item in installment_items:
            desc_norm = self._normalize_description(item.get("description", ""))
            item_date = item.get("date", "")
            # CRITICAL: Incluir número da parcela e total para evitar agrupar parcelas diferentes
            # Ex: "MOTOCHEFE 07/12" e "MOTOCHEFE 08/12" são diferentes!
            installment_current = item.get("installment_current", 0)
            installment_total = item.get("installment_total", 0)
            key = (desc_norm, item_date, installment_total, installment_current)

            if key not in groups:
                groups[key] = []
            groups[key].append(item)

        result_items = list(non_installment_items)

        for key, group in groups.items():
            # Como cada parcela agora tem chave única (desc, date, total, current),
            # nunca haverá mais de 1 item por grupo
            if len(group) == 1:
                result_items.append(group[0])
                continue

            # Se por algum motivo houver >1 item com mesma chave exata, aplicar lógica antiga
            desc_norm = key[0]

            sorted_group = sorted(group, key=lambda x: x.get("installment_current", 0))

            parcelas = [g.get("installment_current", 0) for g in sorted_group]
            totais = [g.get("installment_total", 0) for g in sorted_group]
            valores = [g.get("amount", 0) for g in sorted_group]

            starts_at_1 = parcelas[0] == 1
            is_sequential = all(parcelas[i] == parcelas[i - 1] + 1 for i in range(1, len(parcelas)))
            same_total = len(set(totais)) == 1
            first_val = valores[0]
            similar_values = all(
                abs(v - first_val) / first_val < 0.05 if first_val > 0 else True for v in valores
            )

            if starts_at_1 and is_sequential and same_total and similar_values and len(group) >= 3:
                first_item = sorted_group[0].copy()
                print(
                    f"[Validator] Agrupando {len(group)} parcelas consecutivas de '{desc_norm}' em 1 item (parcela 1/{totais[0]})"
                )
                result_items.append(first_item)
            else:
                result_items.extend(group)

        return result_items

    def remove_cancelled_purchases(self, items: list, card_info: dict | None) -> list:
        """Remove compras que foram canceladas (tem estorno correspondente)."""
        if not items:
            return items

        items_to_remove = set()

        # Detectar estornos/creditos que podem ter sido classificados incorretamente
        # Inclui: transaction_type estorno/credito OU valores negativos grandes (< -100)
        # que nao sao pagamentos de fatura (esses tem descricoes especificas)
        payment_keywords = [
            "pagamento de fatura",
            "pag fatura",
            "pgto fatura",
            "pagamento efetuado",
            "pagamento recebido",
            "pagamento-internet",
            "pag boleto",
        ]

        estornos = []
        for i, item in enumerate(items):
            amount = item.get("amount", 0)
            if amount >= -100:
                continue

            # Sempre incluir se for estorno/credito
            if item.get("transaction_type") in ["estorno", "credito"]:
                estornos.append((i, item))
                continue

            # Verificar se e um pagamento de fatura real (nao deve ser tratado como estorno)
            desc_lower = item.get("description", "").lower()
            is_real_payment = any(kw in desc_lower for kw in payment_keywords)
            if is_real_payment:
                continue

            # Valores negativos grandes que nao sao pagamentos de fatura sao provaveis estornos
            estornos.append((i, item))

        if not estornos:
            return items

        parcela_groups = {}
        for i, item in enumerate(items):
            if not item.get("is_installment") or item.get("transaction_type") != "compra":
                continue

            desc_norm = self._normalize_description(item["description"])
            if desc_norm not in parcela_groups:
                parcela_groups[desc_norm] = []
            parcela_groups[desc_norm].append((i, item))

        for desc_norm, grupo in parcela_groups.items():
            grupo_ordenado = sorted(grupo, key=lambda x: x[1].get("installment_current", 0))

            # Calcular valor total da compra parcelada
            first_item = grupo_ordenado[0][1]
            installment_total = first_item.get("installment_total", 1)

            if len(grupo) == 1:
                # Uma parcela: estima o total multiplicando pelo numero de parcelas
                valor_total_grupo = first_item["amount"] * installment_total
            else:
                # Multiplas parcelas: verifica se sao consecutivas comecando em 1
                parcelas = [g[1].get("installment_current", 0) for g in grupo_ordenado]
                starts_at_1 = parcelas[0] == 1
                is_sequential = all(
                    parcelas[i] == parcelas[i - 1] + 1 for i in range(1, len(parcelas))
                )

                if starts_at_1 and is_sequential and installment_total > len(grupo):
                    # Parcelas consecutivas do inicio: calcula valor total estimado
                    # usando o valor medio das parcelas extraidas
                    avg_value = sum(g[1].get("amount", 0) for g in grupo) / len(grupo)
                    valor_total_grupo = avg_value * installment_total
                else:
                    # Parcelas esparsas ou todas presentes: soma os valores
                    valor_total_grupo = sum(g[1].get("amount", 0) for g in grupo)

            for e_idx, estorno in estornos:
                if e_idx in items_to_remove:
                    continue

                estorno_valor = abs(estorno.get("amount", 0))
                tolerancia = max(valor_total_grupo * 0.02, 10)

                if abs(estorno_valor - valor_total_grupo) <= tolerancia:
                    estorno_nome = estorno["description"].upper()
                    is_generic_estorno = estorno_nome in [
                        "ESTORNO",
                        "CREDITO",
                        "DEVOLUCAO",
                        "CANCELAMENTO",
                    ]

                    desc_compra = grupo[0][1]["description"].upper()
                    compra_parts = set(desc_compra.replace("*", " ").split())
                    estorno_parts = set(estorno_nome.replace("*", " ").split())
                    has_name_overlap = bool(compra_parts & estorno_parts)

                    if is_generic_estorno or has_name_overlap:
                        print(
                            f"[Validator] Removendo compra cancelada: {desc_norm} ({len(grupo)} item(s), total R${valor_total_grupo:.2f}) + estorno R${estorno_valor:.2f}"
                        )

                        for idx, _ in grupo:
                            items_to_remove.add(idx)
                        items_to_remove.add(e_idx)
                        break

        for i, item in enumerate(items):
            if i in items_to_remove:
                continue
            if item.get("is_installment") or item.get("transaction_type") != "compra":
                continue

            valor = item.get("amount", 0)
            if valor <= 0:
                continue

            for e_idx, estorno in estornos:
                if e_idx in items_to_remove:
                    continue

                estorno_valor = abs(estorno.get("amount", 0))
                tolerancia = max(valor * 0.05, 5)

                if abs(estorno_valor - valor) <= tolerancia:
                    estorno_nome = estorno["description"].upper()
                    compra_nome = item["description"].upper()
                    compra_parts = set(compra_nome.replace("*", " ").split())
                    estorno_parts = set(estorno_nome.replace("*", " ").split())

                    if bool(compra_parts & estorno_parts):
                        print(
                            f"[Validator] Removendo compra simples cancelada: {item['description']} R${valor:.2f}"
                        )
                        items_to_remove.add(i)
                        items_to_remove.add(e_idx)
                        break

        if items_to_remove:
            print(f"[Validator] Total: {len(items_to_remove)} itens removidos por cancelamento")
            return [item for i, item in enumerate(items) if i not in items_to_remove]

        return items

    def remove_total_items(self, items: list, card_info: dict | None) -> list:
        """Remove itens que sao totais/resumos da fatura."""
        if not items:
            return items

        total_amount = card_info.get("total_amount") if card_info else None

        removed = []
        result = []

        for item in items:
            desc = item.get("description", "").lower().strip()
            amount = item.get("amount", 0)

            is_total_desc = (
                desc.startswith("total ")
                or desc.startswith("total para ")
                or "total da fatura" in desc
                or "total fatura" in desc
            )

            is_total_value = total_amount and abs(amount - total_amount) < 0.01 and amount > 100

            if is_total_desc or is_total_value:
                removed.append(f"'{item.get('description')}' R${amount:.2f}")
            else:
                result.append(item)

        if removed:
            print(f"[Validator] Removidos itens de total/resumo: {', '.join(removed)}")

        return result

    def validate_extraction(self, items: list, card_info: dict | None) -> dict:
        """Valida a extracao comparando soma dos itens com total_amount."""
        if not card_info or not card_info.get("total_amount"):
            return {"is_valid": True, "difference": 0}

        total_amount = card_info["total_amount"]

        soma_debitos = sum(
            item.get("amount", 0)
            for item in items
            if item.get("transaction_type") in ["compra", "anuidade", "encargo"]
        )

        soma_creditos = sum(
            item.get("amount", 0)
            for item in items
            if item.get("transaction_type") in ["credito", "estorno"]
        )

        diff_sem_creditos = soma_debitos - total_amount
        diff_com_creditos = (soma_debitos + soma_creditos) - total_amount

        if abs(diff_com_creditos) < abs(diff_sem_creditos):
            difference = diff_com_creditos
            soma_final = soma_debitos + soma_creditos
        else:
            difference = diff_sem_creditos
            soma_final = soma_debitos

        is_valid = abs(difference) <= 50.0

        return {
            "is_valid": is_valid,
            "difference": difference,
            "total_amount": total_amount,
            "soma_debitos": soma_final,
            "num_items": len(items),
        }

    def validate_extraction_completeness(
        self, items: list, card_info: dict | None, ocr_text: str | None = None
    ) -> dict:
        """
        Valida se a extracao esta completa comparando quantidade de itens
        com padroes detectados no texto OCR.

        Args:
            items: Lista de itens extraidos
            card_info: Informacoes do cartao
            ocr_text: Texto bruto do OCR (se disponivel)

        Returns:
            dict com is_complete, warnings e estimated_count
        """
        result = {
            "is_complete": True,
            "warnings": [],
            "estimated_transaction_count": None,
            "extracted_count": len(items) if items else 0,
        }

        if not ocr_text:
            return result

        # Contar padroes de data no texto OCR
        # Formatos: DD/MM, DD/MM/AAAA, DD MMM, DD de MMM
        date_patterns = [
            r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b",  # DD/MM ou DD/MM/AAAA
            r"\b\d{1,2}\s+(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\b",  # DD MMM
            r"\b\d{1,2}\s+de\s+(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\b",  # DD de MMM
        ]

        all_dates = []
        for pattern in date_patterns:
            matches = re.findall(pattern, ocr_text.lower())
            all_dates.extend(matches)

        # Remover duplicatas (mesma data pode aparecer mais de uma vez)
        unique_dates = len(set(all_dates))

        # Estimar quantidade de transacoes (cada data unica pode ser uma transacao)
        # Reduzir por ~20% para compensar datas de headers, resumos, etc.
        estimated_count = max(1, int(unique_dates * 0.8))
        result["estimated_transaction_count"] = estimated_count

        extracted_count = len(items) if items else 0

        # Se extraimos menos de 70% do estimado, pode haver problema
        if extracted_count > 0 and estimated_count > 0:
            ratio = extracted_count / estimated_count

            if ratio < 0.7:
                result["is_complete"] = False
                result["warnings"].append(
                    f"Possivel extracao incompleta: {extracted_count} itens extraidos, "
                    f"mas ~{estimated_count} transacoes detectadas no texto OCR. "
                    f"Verifique se todos os itens foram capturados."
                )
                print(
                    f"[Validator] WARNING: Extracao possivelmente incompleta "
                    f"({extracted_count}/{estimated_count} = {ratio:.0%})"
                )

        return result

    def remove_addresses_and_boleto_data(self, items: list) -> list:
        """Remove endereços e dados de boleto que foram extraídos incorretamente como transações

        Args:
            items: Lista de itens extraídos

        Returns:
            Lista filtrada sem endereços/boleto
        """
        if not items:
            return items

        result = []

        # Padrões que indicam dados de boleto/endereço (não são transações)
        ADDRESS_PATTERNS = [
            r"\b\d{5}-\d{3}\b",  # CEP com hífen (30190-131) — exige hífen para evitar falsos positivos com códigos
            r"\b[A-Z]{2}\s*/\s*[A-Z]{2}\b",  # Estado (MG / MG, SP / SP) - word boundaries to avoid .COM/BILL
            r"AUTENTICACAO MECANICA",
            r"NOSSO NUMERO",
            r"CODIGO DE BARRAS",
            r"LOCAL DE PAGAMENTO",
            r"AGENCIA\s*/\s*CEDENTE",
            r"BENEFICIARIO",
            r"\d{5}\.\d{5}\s+\d{5}\.\d{6}",  # Código de barras numérico
            r"AV\s+[A-Z\s]+\d+",  # Avenida com número (AV BARBACENA 1219)
            r"RUA\s+[A-Z\s]+\d+",  # Rua com número
        ]

        CITY_NAMES = [
            "BELO HORIZONTE",
            "SAO PAULO",
            "RIO DE JANEIRO",
            "BRASILIA",
            "CURITIBA",
            "PORTO ALEGRE",
            "SALVADOR",
            "FORTALEZA",
            "RECIFE",
            "GOIANIA",
            "MANAUS",
            "BELEM",
            "CAMPINAS",
            "SANTOS",
        ]

        for item in items:
            desc = item.get("description", "").upper()

            # Verificar se é endereço/boleto
            is_address = False

            # 1. Contém padrões de boleto
            for pattern in ADDRESS_PATTERNS:
                if re.search(pattern, desc):
                    is_address = True
                    break

            # 2. Contém nome de cidade E parece ser endereço (não apenas transação com nome de cidade)
            if not is_address:
                for city in CITY_NAMES:
                    if city in desc:
                        # Verificar se tem indicadores de endereço real
                        has_address_indicator = bool(
                            re.search(
                                r"(RUA|AV\b|AVENIDA|PRACA|PCA|QD|QUADRA|LOTE|BLOCO|CONJ|CJ|BAIRRO|CEP|\d{5}[-]?\d{3})",
                                desc,
                            )
                        )
                        if has_address_indicator:
                            is_address = True
                            break
                        # Se não tem indicador de endereço, provavelmente é uma transação
                        # com nome de cidade (ex: "MOTOCHEFE BRASILIA08/12")
                        continue

            # 3. Descrição muito longa com múltiplos números (provável endereço completo)
            if not is_address and len(desc) > 50:
                # Contar números na descrição
                numbers = re.findall(r"\d+", desc)
                if len(numbers) >= 3:  # Endereço tem: número, CEP, etc.
                    is_address = True

            if is_address:
                print(
                    f"[Validator] Removendo endereço/boleto: '{desc[:60]}...' R${item.get('amount', 0):.2f}"
                )
            else:
                result.append(item)

        if len(result) < len(items):
            print(f"[Validator] Filtro de endereços: {len(items)} -> {len(result)} itens")

        return result

    def fix_dates_from_ocr_text(self, items: list, card_info: dict | None, ocr_text: str) -> list:
        """Corrige datas extraídas usando o texto OCR original.

        O LLM frequentemente ignora o mês (MM) do formato DD/MM e usa o mês da fatura.
        Este método cruza os itens com o texto OCR para recuperar a data DD/MM real.
        """
        if not items or not ocr_text or not card_info:
            return items

        invoice_month = card_info.get("invoice_month")
        invoice_year = card_info.get("invoice_year")
        if not invoice_month or not invoice_year:
            return items

        # Extrair seção relevante do OCR (antes de "próximas faturas")
        ocr_relevant = ocr_text
        for marker in ["próximas faturas", "proximas faturas", "Compras parceladas -"]:
            idx = ocr_text.lower().find(marker.lower())
            if idx > 0:
                ocr_relevant = ocr_text[:idx]
                break

        # Parsear linhas do OCR com padrão DD/MM + descrição + valor
        # Formatos: "09/07 MOTOCHEFE BRASILIA08/12 574,13"
        # Ou markdown table: "| 09/07 | MOTOCHEFE ... | 574,13 |"
        ocr_transactions = []
        for line in ocr_relevant.split("\n"):
            line = line.strip().strip("|").strip()
            if not line:
                continue

            # Padrão: DD/MM no início da linha (com possível pipe de tabela)
            match = re.match(r"\|?\s*(\d{1,2})/(\d{2})\s+(.+?)\s+([\d.]+,\d{2})\s*\|?\s*$", line)
            if not match:
                # Tentar formato com pipes separados: | DD/MM | desc | valor |
                match = re.match(r"\|?\s*(\d{1,2})/(\d{2})\s*\|(.+?)\|([\d.]+,\d{2})\s*\|?", line)
            if match:
                day_str, month_str, desc_part, value_str = match.groups()
                try:
                    day = int(day_str)
                    month = int(month_str)
                    value = float(value_str.replace(".", "").replace(",", "."))
                    if 1 <= day <= 31 and 1 <= month <= 12:
                        ocr_transactions.append(
                            {
                                "day": day,
                                "month": month,
                                "desc": desc_part.strip(),
                                "amount": value,
                            }
                        )
                except (ValueError, IndexError):
                    continue

        if not ocr_transactions:
            return items

        print(
            f"[Validator] OCR date fix: encontradas {len(ocr_transactions)} transações no texto OCR"
        )

        # Rastrear quais linhas OCR já foram usadas (evitar match duplo)
        used_ocr_indices = set()
        fixed_count = 0

        for item in items:
            item_amount = item.get("amount", 0)
            item_date = item.get("date", "")
            item_desc = item.get("description", "")

            if not item_date or item_amount <= 0:
                continue

            # Procurar match no OCR por valor + descrição
            best_idx = None
            best_score = 0

            desc_norm = re.sub(r"[^a-z0-9]", "", item_desc.lower())

            for i, ocr_tx in enumerate(ocr_transactions):
                if i in used_ocr_indices:
                    continue

                # Match por valor (tolerância de 0.01)
                if abs(ocr_tx["amount"] - item_amount) > 0.01:
                    continue

                # Match por descrição (substring dos primeiros chars)
                ocr_desc_norm = re.sub(r"[^a-z0-9]", "", ocr_tx["desc"].lower())
                # Verificar se compartilham prefixo significativo
                min_len = min(len(desc_norm), len(ocr_desc_norm), 8)
                if min_len < 3:
                    continue

                if desc_norm[:min_len] == ocr_desc_norm[:min_len]:
                    score = min_len + 10  # Boost para match de prefixo
                elif desc_norm[:5] in ocr_desc_norm or ocr_desc_norm[:5] in desc_norm:
                    score = 5
                else:
                    continue

                if score > best_score:
                    best_score = score
                    best_idx = i

            if best_idx is not None:
                ocr_tx = ocr_transactions[best_idx]
                used_ocr_indices.add(best_idx)

                ocr_month = ocr_tx["month"]
                ocr_day = ocr_tx["day"]

                # Determinar o ano correto
                if ocr_month > invoice_month:
                    year = invoice_year - 1
                else:
                    year = invoice_year

                correct_date = f"{year}-{ocr_month:02d}-{ocr_day:02d}"

                if correct_date != item_date:
                    print(f"[Validator] Date fix: '{item_desc[:30]}' {item_date} -> {correct_date}")
                    item["date"] = correct_date
                    fixed_count += 1

        if fixed_count > 0:
            print(f"[Validator] OCR date fix: {fixed_count} datas corrigidas")

        return items

    def fix_nubank_dates(self, items: list, card_info: dict | None, ocr_text: str) -> list:
        """Corrige anos errados em faturas Nubank usando o texto OCR.

        O Nubank usa formato "DD MMM" sem ano. O LLM frequentemente usa o ano errado.
        Este método:
        1. Detecta se é Nubank pelo OCR text
        2. Parseia as datas "DD MMM" do OCR
        3. Cruza com os itens e corrige o ano usando a regra invoice_month/invoice_year
        """
        if not items or not ocr_text or not card_info:
            return items

        # Verificar se é Nubank
        card_issuer = (card_info.get("card_issuer") or "").lower()
        if (
            "nubank" not in card_issuer
            and "nubank" not in ocr_text.lower()
            and "nu pagamentos" not in ocr_text.lower()
        ):
            return items

        invoice_month = card_info.get("invoice_month")
        invoice_year = card_info.get("invoice_year")
        if not invoice_month or not invoice_year:
            return items

        MONTH_MAP = {
            "jan": 1,
            "fev": 2,
            "mar": 3,
            "abr": 4,
            "mai": 5,
            "jun": 6,
            "jul": 7,
            "ago": 8,
            "set": 9,
            "out": 10,
            "nov": 11,
            "dez": 12,
        }

        # Parsear transações do OCR no formato "DD MMM  Descrição  R$ XX,XX"
        ocr_transactions = []
        for line in ocr_text.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Padrão: "DD MMM  descrição  R$ XX,XX" ou "DD MMM  descrição  XX,XX"
            match = re.match(
                r"(\d{1,2})\s+(JAN|FEV|MAR|ABR|MAI|JUN|JUL|AGO|SET|OUT|NOV|DEZ)\s+(.+?)\s+R?\$?\s*([\d.]+,\d{2})\s*$",
                line,
                re.IGNORECASE,
            )
            if match:
                day_str, month_str, desc_part, value_str = match.groups()
                try:
                    day = int(day_str)
                    month = MONTH_MAP.get(month_str.lower())
                    value = float(value_str.replace(".", "").replace(",", "."))
                    if month and 1 <= day <= 31:
                        ocr_transactions.append(
                            {
                                "day": day,
                                "month": month,
                                "desc": desc_part.strip(),
                                "amount": value,
                            }
                        )
                except (ValueError, IndexError):
                    continue

        if not ocr_transactions:
            return items

        print(f"[Validator] Nubank date fix: encontradas {len(ocr_transactions)} transações no OCR")

        used_ocr_indices = set()
        fixed_count = 0

        for item in items:
            item_amount = abs(item.get("amount", 0))
            item_date = item.get("date", "")
            item_desc = item.get("description", "")

            if not item_date or item_amount == 0:
                continue

            # Procurar match no OCR
            best_idx = None
            best_score = 0
            desc_norm = re.sub(r"[^a-z0-9]", "", item_desc.lower())

            for i, ocr_tx in enumerate(ocr_transactions):
                if i in used_ocr_indices:
                    continue

                if abs(ocr_tx["amount"] - item_amount) > 0.02:
                    continue

                ocr_desc_norm = re.sub(r"[^a-z0-9]", "", ocr_tx["desc"].lower())
                min_len = min(len(desc_norm), len(ocr_desc_norm), 8)
                if min_len < 3:
                    continue

                if desc_norm[:min_len] == ocr_desc_norm[:min_len]:
                    score = min_len + 10
                elif desc_norm[:5] in ocr_desc_norm or ocr_desc_norm[:5] in desc_norm:
                    score = 5
                else:
                    continue

                if score > best_score:
                    best_score = score
                    best_idx = i

            if best_idx is not None:
                ocr_tx = ocr_transactions[best_idx]
                used_ocr_indices.add(best_idx)

                ocr_month = ocr_tx["month"]
                ocr_day = ocr_tx["day"]

                # Determinar o ano correto
                if ocr_month > invoice_month:
                    year = invoice_year - 1
                else:
                    year = invoice_year

                correct_date = f"{year}-{ocr_month:02d}-{ocr_day:02d}"

                if correct_date != item_date:
                    print(
                        f"[Validator] Nubank date fix: '{item_desc[:30]}' {item_date} -> {correct_date}"
                    )
                    item["date"] = correct_date
                    fixed_count += 1

        if fixed_count > 0:
            print(f"[Validator] Nubank date fix: {fixed_count} datas corrigidas")

        return items
