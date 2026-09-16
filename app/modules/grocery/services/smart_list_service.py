"""
Smart List Service - LLM-powered intelligent shopping list generation
"""

import json
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.grocery import (
    GroceryCategory,
    GroceryPurchase,
    NecessityType,
    ShoppingList,
    ShoppingListItem,
    ShoppingListSource,
    ShoppingListStatus,
)
from app.models.user import User
from app.modules.grocery.prompts import SMART_LIST_PROMPT, SMART_LIST_RESPONSE_SCHEMA
from app.modules.grocery.schemas.smart_list import (
    ExcludedItem,
    OriginalProductDetail,
    SmartListFullResponse,
    SmartListGenerateRequest,
    SmartListItemResponse,
)
from app.modules.household.utils import get_household_user_ids


class SmartListService:
    """Service for generating smart shopping lists using LLM"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._gemini_client = None
        self._mistral_client = None

    def _get_gemini_client(self):
        """Get Google Genai client (lazy initialization)"""
        if self._gemini_client is None:
            try:
                from google import genai

                api_key = settings.google_api_key
                if not api_key:
                    raise ValueError("GOOGLE_API_KEY nao configurada")
                self._gemini_client = genai.Client(api_key=api_key)
            except ImportError:
                raise ImportError("google-genai nao instalado. Execute: pip install google-genai")
        return self._gemini_client

    def _get_mistral_client(self):
        """Get Mistral client (lazy initialization)"""
        if self._mistral_client is None:
            try:
                from mistralai import Mistral

                api_key = settings.mistral_api_key
                if not api_key:
                    raise ValueError("MISTRAL_API_KEY nao configurada")
                self._mistral_client = Mistral(api_key=api_key)
            except ImportError:
                raise ImportError("mistralai nao instalado. Execute: pip install mistralai")
        return self._mistral_client

    async def generate_smart_list(
        self, user: User, request: SmartListGenerateRequest
    ) -> SmartListFullResponse:
        """Generate a smart shopping list using LLM analysis"""
        print("[SmartListService] === INICIANDO GERACAO DE LISTA INTELIGENTE ===")
        print(f"[SmartListService] User ID: {user.id}, License ID: {user.license_id}")
        print(
            f"[SmartListService] Request: period_days={request.period_days}, include_non_essential={request.include_non_essential}"
        )

        # 1. Fetch purchase history
        purchases = await self._fetch_purchases(user, request)

        print(f"[SmartListService] Compras encontradas: {len(purchases)}")

        if not purchases:
            # Return empty list if no purchases found
            print("[SmartListService] MOTIVO DA LISTA VAZIA: Nenhuma compra encontrada no periodo")
            return await self._create_empty_list(user, request)

        # 2. Prepare data for LLM
        purchases_data = self._prepare_for_llm(purchases)

        # 3. Call LLM
        llm_response = await self._call_llm(purchases_data, request)

        # 4. Enrich LLM response with original product details
        llm_items = llm_response.get("shopping_list", [])
        print(f"[SmartListService] Itens do LLM para enriquecer: {len(llm_items)}")

        enriched_items = self._enrich_with_original_products(llm_items, purchases)
        print(f"[SmartListService] Itens enriquecidos: {len(enriched_items)}")

        # 5. Create shopping list in database
        shopping_list = await self._create_shopping_list(user, request, enriched_items)
        print(f"[SmartListService] Lista criada no banco: ID={shopping_list.id}")

        # 6. Build full response
        response = self._build_response(
            shopping_list,
            enriched_items,
            llm_response.get("excluded", []),
            llm_response.get("insights", []),
            user,
        )

        print("[SmartListService] === GERACAO CONCLUIDA ===")
        print(f"[SmartListService] Total de itens na lista: {response.total_items}")
        print(f"[SmartListService] Total estimado: R$ {response.estimated_total}")

        return response

    async def _fetch_purchases(
        self, user: User, request: SmartListGenerateRequest
    ) -> list[GroceryPurchase]:
        """Fetch purchase history for the specified period"""
        household_user_ids = await get_household_user_ids(self.db, user)
        start_date = date.today() - timedelta(days=request.period_days)

        print(f"[SmartListService] _fetch_purchases: start_date={start_date}, today={date.today()}")
        print(f"[SmartListService] _fetch_purchases: household_user_ids={household_user_ids}")

        query = (
            select(GroceryPurchase)
            .where(GroceryPurchase.purchase_date >= start_date)
            .options(selectinload(GroceryPurchase.merchant))
        )

        if household_user_ids:
            query = query.where(GroceryPurchase.user_id.in_(household_user_ids))
            print("[SmartListService] _fetch_purchases: Filtrando por household_user_ids")
        else:
            query = query.where(GroceryPurchase.user_id == user.id)
            print(f"[SmartListService] _fetch_purchases: Filtrando por user_id={user.id}")

        if not request.include_non_essential:
            query = query.where(GroceryPurchase.necessity_type == NecessityType.ESSENTIAL.value)
            print("[SmartListService] _fetch_purchases: Filtrando apenas ESSENTIAL")
        else:
            print("[SmartListService] _fetch_purchases: Incluindo todos os tipos de necessidade")

        # Limit to avoid token overflow (max 100 items - reduced for faster response)
        query = query.order_by(GroceryPurchase.purchase_date.desc()).limit(100)

        result = await self.db.execute(query)
        purchases = list(result.scalars().all())

        if purchases:
            print(
                f"[SmartListService] _fetch_purchases: Primeira compra: {purchases[0].product_name} em {purchases[0].purchase_date}"
            )
            print(
                f"[SmartListService] _fetch_purchases: Ultima compra: {purchases[-1].product_name} em {purchases[-1].purchase_date}"
            )
        else:
            # Debug: verificar se existem compras sem filtro de data
            from sqlalchemy import func

            count_query = select(func.count(GroceryPurchase.id)).where(
                GroceryPurchase.user_id == user.id
            )
            total_result = await self.db.execute(count_query)
            total_count = total_result.scalar()
            print("[SmartListService] _fetch_purchases: NENHUMA compra no periodo!")
            print(
                f"[SmartListService] _fetch_purchases: Total de compras do usuario (sem filtro de data): {total_count}"
            )

        return purchases

    def _prepare_for_llm(self, purchases: list[GroceryPurchase]) -> str:
        """Prepare purchase data as compact JSON for LLM"""
        items = []
        for p in purchases:
            item = {
                "name": p.product_name,
                "category": p.category,
                "qty": float(p.quantity),
                "price": float(p.unit_price),
                "date": p.purchase_date.isoformat(),
                "unit": p.unit,
            }
            if p.merchant:
                item["merchant"] = p.merchant.name
            items.append(item)

        return json.dumps(items, ensure_ascii=False)

    async def _call_llm(self, purchases_json: str, request: SmartListGenerateRequest) -> dict:
        """
        Call LLM to analyze purchases and generate list.
        Strategy: Mistral (primary) -> Gemini (fallback)
        """
        prompt = SMART_LIST_PROMPT.format(
            current_date=date.today().isoformat(),
            period_days=request.period_days,
            purchases_json=purchases_json,
        )

        print(f"[SmartListService] Chamando LLM com {len(purchases_json)} chars de dados...")
        print(f"[SmartListService] Prompt total: {len(prompt)} chars")

        # 1. Tentar Mistral primeiro (mais barato e confiavel)
        if settings.mistral_api_key:
            result = await self._call_mistral(prompt)
            if result and result.get("shopping_list"):
                return result
            print("[SmartListService] Mistral falhou ou retornou lista vazia, tentando Gemini...")

        # 2. Fallback para Gemini
        if settings.google_api_key:
            result = await self._call_gemini(prompt)
            if result and result.get("shopping_list"):
                return result

        # 3. Todos os providers falharam
        print("[SmartListService] Todos os providers falharam!")
        return self._fallback_response()

    def _mistral_chat_sync(self, client, model: str, prompt: str):
        """Chamada sincrona ao Mistral (executada em thread separada)"""
        return client.chat.complete(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=32000,  # Aumentado para listas grandes
        )

    async def _call_mistral(self, prompt: str) -> dict | None:
        """Call Mistral API to generate shopping list (non-blocking)"""
        import asyncio

        try:
            client = self._get_mistral_client()
        except Exception as e:
            print(f"[SmartListService] ERRO ao criar cliente Mistral: {type(e).__name__}: {e}")
            return None

        model = settings.mistral_llm_model or "mistral-small-latest"
        last_error = None

        for attempt in range(3):
            try:
                print(f"[SmartListService] Tentativa {attempt + 1}/3 com Mistral ({model})")

                # Executa em thread separada para nao bloquear o event loop
                response = await asyncio.to_thread(self._mistral_chat_sync, client, model, prompt)

                response_text = response.choices[0].message.content if response.choices else ""
                print(f"[SmartListService] Mistral respondeu: {len(response_text)} chars")

                if not response_text:
                    print("[SmartListService] ERRO: Resposta vazia do Mistral!")
                    continue

                return self._parse_llm_response(response_text)

            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                print(
                    f"[SmartListService] ERRO Mistral tentativa {attempt + 1}: {type(e).__name__}: {e}"
                )

                # Se for erro de rate limit ou overloaded, esperar e tentar novamente
                if "429" in str(e) or "rate" in error_str or "overload" in error_str:
                    wait_time = (attempt + 1) * 2  # 2s, 4s, 6s
                    print(f"[SmartListService] Mistral rate limited, aguardando {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    # Erro diferente, parar tentativas
                    break

        if last_error:
            print(f"[SmartListService] Mistral falhou apos 3 tentativas: {last_error}")
        return None

    def _gemini_generate_sync(self, client, model: str, prompt: str, config):
        """Chamada sincrona ao Gemini (executada em thread separada)"""
        return client.models.generate_content(
            model=model,
            contents=[prompt],
            config=config,
        )

    async def _call_gemini(self, prompt: str) -> dict | None:
        """Call Google Gemini API as fallback (non-blocking)"""
        import asyncio

        try:
            from google.genai import types
        except ImportError:
            print("[SmartListService] ERRO: google.genai not available")
            return None

        try:
            client = self._get_gemini_client()
        except Exception as e:
            print(f"[SmartListService] ERRO ao criar cliente Gemini: {type(e).__name__}: {e}")
            return None

        # Modelos Gemini atualizados (removendo modelos obsoletos)
        models_to_try = ["gemini-2.5-flash-preview-05-20", "gemini-2.0-flash"]
        last_error = None

        config = types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=16000,
            response_mime_type="application/json",
            response_schema=SMART_LIST_RESPONSE_SCHEMA,
        )

        for model in models_to_try:
            for attempt in range(3):
                try:
                    print(f"[SmartListService] Tentativa {attempt + 1}/3 com Gemini ({model})")

                    # Executa em thread separada para nao bloquear o event loop
                    response = await asyncio.to_thread(
                        self._gemini_generate_sync, client, model, prompt, config
                    )

                    response_text = response.text if response else ""
                    print(f"[SmartListService] Gemini respondeu: {len(response_text)} chars")

                    if not response_text:
                        print("[SmartListService] ERRO: Resposta vazia do Gemini!")
                        if response and hasattr(response, "candidates") and response.candidates:
                            if response.candidates[0].finish_reason:
                                print(
                                    f"[SmartListService] Finish reason: {response.candidates[0].finish_reason}"
                                )
                        continue

                    return self._parse_llm_response(response_text)

                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    print(
                        f"[SmartListService] ERRO Gemini tentativa {attempt + 1}: {type(e).__name__}: {e}"
                    )

                    if (
                        "503" in str(e)
                        or "overloaded" in error_str
                        or "429" in str(e)
                        or "rate" in error_str
                    ):
                        wait_time = (attempt + 1) * 2
                        print(
                            f"[SmartListService] Gemini sobrecarregado, aguardando {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        break

            print(f"[SmartListService] Modelo {model} falhou, tentando proximo...")

        if last_error:
            import traceback

            print(f"[SmartListService] Gemini falhou: {type(last_error).__name__}: {last_error}")
            print(f"[SmartListService] Traceback: {traceback.format_exc()}")
        return None

    def _parse_llm_response(self, response_text: str) -> dict:
        """Parse and validate LLM JSON response"""
        if not response_text:
            print("[SmartListService] _parse_llm_response: Texto vazio, retornando fallback")
            return self._fallback_response()

        try:
            data = json.loads(response_text)
            print("[SmartListService] _parse_llm_response: JSON parseado com sucesso")

            # Validate required fields
            if "shopping_list" not in data:
                data["shopping_list"] = []
                print(
                    "[SmartListService] _parse_llm_response: Campo 'shopping_list' ausente, usando lista vazia"
                )
            if "excluded" not in data:
                data["excluded"] = []
            if "insights" not in data:
                data["insights"] = []

            print(
                f"[SmartListService] _parse_llm_response: shopping_list={len(data['shopping_list'])} itens"
            )
            print(f"[SmartListService] _parse_llm_response: excluded={len(data['excluded'])} itens")
            print(f"[SmartListService] _parse_llm_response: insights={len(data['insights'])} itens")

            if data["shopping_list"]:
                print(
                    f"[SmartListService] _parse_llm_response: Primeiro item: {data['shopping_list'][0].get('product_type', 'N/A')}"
                )
            else:
                print("[SmartListService] _parse_llm_response: LISTA VAZIA retornada pelo LLM!")
                print(
                    f"[SmartListService] _parse_llm_response: Resposta completa (primeiros 500 chars): {response_text[:500]}"
                )

            return data

        except json.JSONDecodeError as e:
            print(f"[SmartListService] _parse_llm_response: ERRO de parse JSON: {e}")
            print("[SmartListService] _parse_llm_response: Tentando reparar JSON truncado...")

            # Tentar reparar JSON truncado - extrair itens válidos da shopping_list
            repaired_data = self._try_repair_truncated_json(response_text)
            if repaired_data and repaired_data.get("shopping_list"):
                print(
                    f"[SmartListService] _parse_llm_response: JSON reparado com {len(repaired_data['shopping_list'])} itens"
                )
                return repaired_data

            print("[SmartListService] _parse_llm_response: Nao foi possivel reparar o JSON")
            return self._fallback_response()

    def _try_repair_truncated_json(self, response_text: str) -> dict | None:
        """Tenta reparar JSON truncado extraindo itens válidos"""
        try:
            # Encontrar o array shopping_list
            start_marker = '"shopping_list": ['
            start_idx = response_text.find(start_marker)
            if start_idx == -1:
                return None

            array_start = start_idx + len(start_marker)

            # Extrair itens válidos um por um
            valid_items = []
            depth = 0
            item_start = None

            for i, char in enumerate(response_text[array_start:], start=array_start):
                if char == "{":
                    if depth == 0:
                        item_start = i
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0 and item_start is not None:
                        # Tentar parsear este item
                        item_str = response_text[item_start : i + 1]
                        try:
                            item = json.loads(item_str)
                            # Validar campos obrigatórios
                            if all(k in item for k in ["product_type", "display_name", "category"]):
                                valid_items.append(item)
                        except json.JSONDecodeError:
                            pass
                        item_start = None
                elif char == "]" and depth == 0:
                    break

            if valid_items:
                return {
                    "shopping_list": valid_items,
                    "excluded": [],
                    "insights": ["Lista parcialmente recuperada de resposta truncada."],
                }

            return None

        except Exception as e:
            print(f"[SmartListService] _try_repair_truncated_json: Erro: {e}")
            return None

    def _fallback_response(self) -> dict:
        """Return empty response when LLM fails"""
        print(
            "[SmartListService] _fallback_response: Retornando resposta de fallback (lista vazia)"
        )
        return {
            "shopping_list": [],
            "excluded": [],
            "insights": ["Nao foi possivel analisar o historico. Tente novamente."],
        }

    def _enrich_with_original_products(
        self, llm_items: list[dict], purchases: list[GroceryPurchase]
    ) -> list[SmartListItemResponse]:
        """Enrich LLM response with original product details"""
        # Create lookup by normalized product name
        purchases_by_name: dict[str, list[GroceryPurchase]] = defaultdict(list)
        for p in purchases:
            name_lower = p.product_name.lower().strip()
            purchases_by_name[name_lower].append(p)

        enriched_items = []
        seen_product_types = set()  # Avoid duplicates

        for item in llm_items:
            product_type = item.get("product_type", "Produto")

            # Skip duplicates
            if product_type.lower() in seen_product_types:
                continue
            seen_product_types.add(product_type.lower())

            # Try to match by product_type name
            original_products = []
            product_type_parts = product_type.lower().split()

            for name_key, p_list in purchases_by_name.items():
                # Match if any significant word from product_type is in the purchase name
                if any(part in name_key for part in product_type_parts if len(part) > 3):
                    for p in p_list:
                        if not any(
                            op.product_name == p.product_name
                            and op.purchase_date == p.purchase_date
                            for op in original_products
                        ):
                            original_products.append(
                                OriginalProductDetail(
                                    product_name=p.product_name,
                                    purchase_date=p.purchase_date,
                                    unit_price=float(p.unit_price),
                                    quantity=float(p.quantity),
                                    merchant_name=p.merchant.name if p.merchant else None,
                                )
                            )

            # Validate and normalize category
            try:
                category = GroceryCategory(item.get("category", "other"))
            except ValueError:
                category = GroceryCategory.OTHER

            # Validate necessity type
            try:
                necessity_type = NecessityType(item.get("necessity_type", "essential"))
            except ValueError:
                necessity_type = NecessityType.ESSENTIAL

            enriched_items.append(
                SmartListItemResponse(
                    product_type=product_type,
                    display_name=item.get("display_name", product_type),
                    category=category,
                    necessity_type=necessity_type,
                    suggested_quantity=item.get("suggested_quantity", 1),
                    unit=item.get("unit", "un"),
                    estimated_price=item.get("estimated_price"),
                    urgency=item.get("urgency", "medium"),
                    reasoning="",  # Not in simplified response
                    original_products=original_products,
                    purchase_count=item.get("purchase_count", len(original_products)),
                    days_since_last_purchase=item.get("days_since_last_purchase", 0),
                    avg_cycle_days=None,  # Not in simplified response
                )
            )

        return enriched_items

    async def _create_shopping_list(
        self, user: User, request: SmartListGenerateRequest, items: list[SmartListItemResponse]
    ) -> ShoppingList:
        """Create shopping list with items in database"""
        today = date.today()
        list_name = request.name or f"Lista Inteligente - {today.strftime('%d/%m/%Y')}"

        shopping_list = ShoppingList(
            user_id=user.id,
            license_id=user.license_id,
            name=list_name,
            status=ShoppingListStatus.DRAFT.value,
            source=ShoppingListSource.AI_GENERATED.value,
            ownership_type="household",
            notes=f"Gerada por IA com base nos ultimos {request.period_days} dias. "
            f"Total: {len(items)} tipos de produtos.",
        )
        self.db.add(shopping_list)
        await self.db.flush()

        # Add items with priority based on urgency
        for item in items:
            priority = 0
            if item.urgency == "high":
                priority = 3
            elif item.urgency == "medium":
                priority = 2
            elif item.necessity_type == NecessityType.ESSENTIAL:
                priority = 1

            db_item = ShoppingListItem(
                list_id=shopping_list.id,
                product_name=item.product_type,
                quantity=item.suggested_quantity,
                unit=item.unit,
                estimated_price=item.estimated_price,
                category=item.category.value,
                necessity_type=item.necessity_type.value,
                priority=priority,
                notes=item.reasoning[:200] if item.reasoning else None,
            )
            self.db.add(db_item)

        await self.db.flush()
        await self.db.refresh(shopping_list)
        return shopping_list

    async def _create_empty_list(
        self, user: User, request: SmartListGenerateRequest
    ) -> SmartListFullResponse:
        """Create an empty response when no purchases found"""
        today = date.today()
        list_name = request.name or f"Lista Inteligente - {today.strftime('%d/%m/%Y')}"

        shopping_list = ShoppingList(
            user_id=user.id,
            license_id=user.license_id,
            name=list_name,
            status=ShoppingListStatus.DRAFT.value,
            source=ShoppingListSource.AI_GENERATED.value,
            ownership_type="household",
            notes=f"Nenhuma compra encontrada nos ultimos {request.period_days} dias.",
        )
        self.db.add(shopping_list)
        await self.db.flush()
        await self.db.refresh(shopping_list)

        return SmartListFullResponse(
            id=shopping_list.id,
            user_id=shopping_list.user_id,
            license_id=shopping_list.license_id,
            name=shopping_list.name,
            notes=shopping_list.notes,
            status=ShoppingListStatus(shopping_list.status),
            source=ShoppingListSource(shopping_list.source),
            ownership_type=shopping_list.ownership_type,
            created_at=shopping_list.created_at,
            updated_at=shopping_list.updated_at,
            items=[],
            excluded=[],
            insights=[
                "Nenhuma compra encontrada no periodo especificado. "
                "Adicione itens manualmente ou importe cupons fiscais."
            ],
            total_items=0,
            estimated_total=0,
            creator_name=user.name,
        )

    def _build_response(
        self,
        shopping_list: ShoppingList,
        items: list[SmartListItemResponse],
        excluded: list[dict],
        insights: list[str],
        user: User,
    ) -> SmartListFullResponse:
        """Build the full response object"""
        # Sort items: high urgency first, then essential, then by name
        items.sort(
            key=lambda x: (
                {"high": 0, "medium": 1, "low": 2}.get(x.urgency, 2),
                x.necessity_type != NecessityType.ESSENTIAL,
                x.display_name.lower(),
            )
        )

        # Calculate totals
        total_items = len(items)
        estimated_total = sum(
            (item.estimated_price or 0) * item.suggested_quantity for item in items
        )

        # Parse excluded items
        excluded_items = [
            ExcludedItem(name=e.get("name", ""), reason=e.get("reason", "")) for e in excluded
        ]

        return SmartListFullResponse(
            id=shopping_list.id,
            user_id=shopping_list.user_id,
            license_id=shopping_list.license_id,
            name=shopping_list.name,
            notes=shopping_list.notes,
            status=ShoppingListStatus(shopping_list.status),
            source=ShoppingListSource(shopping_list.source),
            ownership_type=shopping_list.ownership_type,
            created_at=shopping_list.created_at,
            updated_at=shopping_list.updated_at,
            items=items,
            excluded=excluded_items,
            insights=insights[:5],  # Max 5 insights
            total_items=total_items,
            estimated_total=round(estimated_total, 2),
            creator_name=user.name,
        )
