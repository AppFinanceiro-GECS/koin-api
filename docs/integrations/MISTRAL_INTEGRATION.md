# Plano de Integração do Mistral OCR no Biveto App

## Resumo Executivo

Este documento descreve os passos necessários para integrar o **Mistral OCR** no biveto-app como um provider alternativo para extração de dados de faturas de cartão de crédito.

### Por que Mistral?

| Modelo | Custo/1000 páginas | Taxa de Sucesso | Observações |
|--------|-------------------|-----------------|-------------|
| **Mistral OCR** | **~$1** | **100%** | OCR especializado + LLM |
| Gemini 2.0 Flash | ~$3.68 | 92% | Provider atual |
| GPT-4o | ~$16.10 | - | Alto custo |

**Vantagens do Mistral:**
- Custo ~3.7x menor que o Gemini atual
- Processo em duas etapas (OCR + LLM) resulta em maior precisão
- OCR especializado extrai tabelas com maior fidelidade
- Taxa de sucesso de 100% em testes com faturas brasileiras

---

## Arquitetura Atual vs Proposta

### Fluxo Atual (Gemini)
```
PDF → Gemini Vision API → JSON Estruturado
      (OCR + Extração em uma chamada)
```

### Fluxo Proposto (Mistral)
```
PDF → Mistral OCR API → Texto/Markdown → Mistral LLM → JSON Estruturado
      (Passo 1: OCR)                      (Passo 2: Estruturação)
```

---

## Tarefas de Implementação

### 1. Configuração de Ambiente

#### 1.1 Adicionar dependência
```bash
# requirements.txt
mistralai>=1.0.0
```

#### 1.2 Adicionar variáveis de ambiente
```python
# app/core/config.py

class Settings(BaseSettings):
    # ... existing settings ...

    # Mistral Settings
    mistral_api_key: str | None = Field(default=None, env="MISTRAL_API_KEY")
    mistral_ocr_model: str = Field(default="mistral-ocr-latest", env="MISTRAL_OCR_MODEL")
    mistral_llm_model: str = Field(default="mistral-large-latest", env="MISTRAL_LLM_MODEL")
```

#### 1.3 Atualizar .env.example
```env
# Mistral OCR (melhor custo-benefício para OCR de faturas)
MISTRAL_API_KEY=
MISTRAL_OCR_MODEL=mistral-ocr-latest
MISTRAL_LLM_MODEL=mistral-large-latest
```

---

### 2. Criar Prompt para Mistral

Criar arquivo de prompt otimizado para o Mistral em:
```
app/modules/documents/prompts/prompt_mistral.md
```

**Estrutura do prompt:**
```markdown
# Extração de Fatura de Cartão de Crédito Brasileiro

## TAREFA
Analise o texto extraído pelo OCR de uma fatura e retorne um JSON estruturado.

## REGRAS CRÍTICAS DE VALORES
- COMPRAS = valores POSITIVOS
- PAGAMENTOS = valores NEGATIVOS
- CRÉDITOS/ESTORNOS = valores NEGATIVOS
- ENCARGOS (IOF, juros) = valores POSITIVOS

## ESTRUTURA DO JSON
{
  "document_type": "fatura_cartao",
  "card_info": { ... },
  "items": [ ... ]
}

## REGRAS POR BANCO
### SANTANDER
- Coluna "Parcela" separada da descrição
- "01/12" na coluna Parcela = parcela 1 de 12

### BRADESCO/AMEX
- Layout em tabela
- Parcela concatenada na descrição

### NUBANK
- Data no formato "DD MMM" (ex: "15 DEZ")

### ITAÚ
- IOF em linha separada após compra internacional

## EXTRAIA OS DADOS:
```

**Nota:** O prompt completo deve ser baseado em `prompts/prompt_mistral.txt` do projeto fatura-prompt-validator, adaptado para os schemas do biveto-app.

---

### 3. Implementar Provider Mistral

#### 3.1 Adicionar método no LLMOCRService

**Arquivo:** `app/modules/documents/services/llm_ocr_service.py`

```python
from mistralai import Mistral

async def _call_mistral_ocr(self, pdf_content: bytes, filename: str) -> dict:
    """
    Extrai dados de um PDF usando Mistral OCR + LLM (processo em 2 etapas)

    Passo 1: Mistral OCR extrai texto/tabelas do PDF
    Passo 2: Mistral LLM estrutura os dados em JSON
    """
    api_key = settings.mistral_api_key
    if not api_key:
        return {
            'items': [],
            'card_info': None,
            'document_type': None,
            'error': 'MISTRAL_API_KEY not configured'
        }

    try:
        client = Mistral(api_key=api_key)

        # Passo 1: Upload do PDF
        print(f"[MISTRAL] Passo 1: Fazendo upload do PDF...")
        uploaded_file = client.files.upload(
            file={
                "file_name": filename,
                "content": pdf_content,
            },
            purpose="ocr"
        )
        print(f"[MISTRAL] Upload concluído: {uploaded_file.id}")

        # Passo 2: OCR do PDF
        print("[MISTRAL] Passo 2: Executando OCR...")
        ocr_response = client.ocr.process(
            model=settings.mistral_ocr_model,
            document={
                "type": "file",
                "file_id": uploaded_file.id,
            },
            include_image_base64=False
        )

        # Extrair texto do OCR
        ocr_text = ""
        if hasattr(ocr_response, 'pages'):
            for page in ocr_response.pages:
                if hasattr(page, 'markdown'):
                    ocr_text += page.markdown + "\n\n"
        elif hasattr(ocr_response, 'text'):
            ocr_text = ocr_response.text

        print(f"[MISTRAL] OCR extraiu {len(ocr_text)} caracteres")

        if not ocr_text.strip():
            return {
                'items': [],
                'card_info': None,
                'document_type': None,
                'error': 'OCR não extraiu texto do PDF'
            }

        # Passo 3: Estruturar com LLM
        print("[MISTRAL] Passo 3: Estruturando com LLM...")

        prompt = self._get_mistral_prompt()
        full_prompt = f"{prompt}\n\n## Texto extraído do PDF pelo OCR:\n\n{ocr_text}"

        chat_response = client.chat.complete(
            model=settings.mistral_llm_model,
            messages=[
                {
                    "role": "user",
                    "content": full_prompt
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.1
        )

        response_text = chat_response.choices[0].message.content
        print(f"[MISTRAL] LLM retornou {len(response_text)} caracteres")

        # Parse JSON
        result = json.loads(response_text)

        # Converter para formato interno do biveto-app
        return self._convert_mistral_response(result)

    except Exception as e:
        print(f"[MISTRAL] Erro: {str(e)}")
        return {
            'items': [],
            'card_info': None,
            'document_type': None,
            'error': f'Mistral error: {str(e)}'
        }

def _get_mistral_prompt(self) -> str:
    """Carrega o prompt otimizado para Mistral"""
    prompt_path = Path(__file__).parent.parent / "prompts" / "prompt_mistral.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")

    # Fallback: usar prompt embutido
    return MISTRAL_EXTRACTION_PROMPT  # constante definida no arquivo

def _convert_mistral_response(self, mistral_result: dict) -> dict:
    """Converte resposta do Mistral para formato interno do biveto-app"""
    items = []

    for item in mistral_result.get('items', []):
        items.append({
            'description': item.get('description', ''),
            'amount': float(item.get('amount', 0)),
            'date': item.get('date'),
            'category': item.get('category', 'outros'),
            'transaction_type': item.get('transaction_type', 'compra'),
            'is_installment': item.get('is_installment', False),
            'installment_current': item.get('installment_current'),
            'installment_total': item.get('installment_total'),
            'future_installments': [],  # Calcular se necessário
        })

    card_info = mistral_result.get('card_info', {})

    return {
        'items': items,
        'card_info': {
            'card_issuer': card_info.get('card_issuer'),
            'card_bank': card_info.get('card_bank'),
            'card_brand': card_info.get('card_brand'),
            'card_last_digits': card_info.get('card_last_digits'),
            'card_name': card_info.get('card_name'),
            'invoice_month': card_info.get('invoice_month'),
            'invoice_year': card_info.get('invoice_year'),
            'closing_date': card_info.get('closing_date'),
            'due_date': card_info.get('due_date'),
            'total_amount': card_info.get('total_amount'),
            'credit_limit': card_info.get('credit_limit'),
        },
        'document_type': mistral_result.get('document_type', 'fatura_cartao'),
        'error': None
    }
```

#### 3.2 Integrar no fluxo principal

No método `extract_from_image()`, adicionar suporte ao provider Mistral:

```python
async def extract_from_image(self, image_content: bytes, mime_type: str, filename: str = "document") -> dict:
    """Extrai dados de um documento usando LLM Vision ou OCR"""

    # Se for PDF e provider é Mistral, usar OCR especializado
    if mime_type == 'application/pdf' and self.provider == 'mistral':
        result = await self._call_mistral_ocr(image_content, filename)

        # Aplicar filtros de pós-processamento (mesmos do Gemini)
        if result.get('items'):
            result['items'] = self._fix_payment_amounts(result['items'])
            result['items'] = self._fix_bradesco_installments(result['items'])
            result['items'] = self._remove_cancelled_purchases(result['items'])
            result['items'] = self._remove_total_items(result['items'])

        return result

    # ... resto do código existente para outros providers ...
```

---

### 4. Adicionar Seleção de Provider

#### 4.1 Via configuração global

```python
# app/core/config.py
vision_provider: str = Field(default="google", env="VISION_PROVIDER")
# Valores aceitos: "google", "openai", "anthropic", "mistral"
```

#### 4.2 Via parâmetro na API (opcional)

```python
# app/modules/documents/routers/documents.py
@router.post("/")
async def upload_document(
    file: UploadFile,
    provider: str = Query(default=None, description="LLM provider: google, mistral"),
    current_user: User = Depends(get_current_user),
):
    # Usar provider específico se informado
    llm_service = LLMOCRService(provider=provider or settings.vision_provider)
```

---

### 5. Implementar Fallback Inteligente

Para maior resiliência, implementar fallback entre providers:

```python
async def extract_with_fallback(self, pdf_content: bytes, filename: str) -> dict:
    """Tenta múltiplos providers em ordem de preferência"""

    providers = ['mistral', 'google', 'openai']  # Ordem de preferência

    for provider in providers:
        self.provider = provider

        if provider == 'mistral' and not settings.mistral_api_key:
            continue
        if provider == 'google' and not settings.google_api_key:
            continue
        if provider == 'openai' and not settings.openai_api_key:
            continue

        try:
            if provider == 'mistral':
                result = await self._call_mistral_ocr(pdf_content, filename)
            else:
                result = await self._process_pdf_with_provider(pdf_content, provider)

            if result.get('items') and not result.get('error'):
                print(f"[OCR] Sucesso com provider: {provider}")
                return result

        except Exception as e:
            print(f"[OCR] Falha com {provider}: {e}")
            continue

    return {
        'items': [],
        'error': 'Todos os providers falharam'
    }
```

---

### 6. Testes

#### 6.1 Criar script de teste

```python
# scripts/test_mistral_integration.py
import asyncio
from pathlib import Path
from app.modules.documents.services.llm_ocr_service import LLMOCRService

async def test_mistral():
    pdf_path = Path("test_fatura_santander.pdf")

    service = LLMOCRService(provider="mistral")

    with open(pdf_path, "rb") as f:
        result = await service._call_mistral_ocr(f.read(), pdf_path.name)

    print(f"Items extraídos: {len(result.get('items', []))}")
    print(f"Card issuer: {result.get('card_info', {}).get('card_issuer')}")

    for item in result.get('items', [])[:5]:
        print(f"  - {item['description']}: R$ {item['amount']}")

if __name__ == "__main__":
    asyncio.run(test_mistral())
```

#### 6.2 Comparar resultados

Criar teste de comparação entre providers:
```bash
# Testar com Gemini
VISION_PROVIDER=google python scripts/test_extraction.py fatura.pdf

# Testar com Mistral
VISION_PROVIDER=mistral python scripts/test_extraction.py fatura.pdf
```

---

## Checklist de Implementação

### Fase 1: Configuração
- [ ] Adicionar `mistralai` ao `requirements.txt`
- [ ] Adicionar variáveis de ambiente no `config.py`
- [ ] Atualizar `.env.example`
- [ ] Obter API key em https://console.mistral.ai/

### Fase 2: Implementação Core
- [ ] Criar prompt `prompt_mistral.md`
- [ ] Implementar método `_call_mistral_ocr()`
- [ ] Implementar método `_convert_mistral_response()`
- [ ] Integrar no `extract_from_image()`

### Fase 3: Integração
- [ ] Adicionar seleção de provider na API (opcional)
- [ ] Implementar fallback entre providers
- [ ] Aplicar filtros de pós-processamento existentes

### Fase 4: Testes
- [ ] Testar com fatura Santander (`test_fatura_santander.pdf`)
- [ ] Testar com faturas de outros bancos
- [ ] Comparar resultados Mistral vs Gemini
- [ ] Validar soma de itens vs total_amount

### Fase 5: Deploy
- [ ] Adicionar `MISTRAL_API_KEY` nas variáveis de produção
- [ ] Monitorar custos e performance
- [ ] Documentar uso no README

---

## Estimativa de Custos

### Mistral OCR
- OCR: $1/1000 páginas
- LLM (mistral-large): $2/1M input tokens, $6/1M output tokens

### Comparação mensal (1000 faturas/mês)
| Provider | Custo Estimado |
|----------|---------------|
| Gemini 2.0 Flash | ~$3.68 |
| Mistral OCR + LLM | ~$1.50 |
| **Economia** | **~60%** |

---

## Referências

- [Mistral AI Documentation](https://docs.mistral.ai/)
- [Mistral OCR API](https://docs.mistral.ai/capabilities/document/)
- [Mistral Python SDK](https://github.com/mistralai/client-python)
- [Projeto de Referência](file:///Users/kalebeandrade/Dev/geral/fatura-prompt-validator/)
