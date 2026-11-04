# Contrato da API

Vale para quem consome a API do Koin (app, outros grupos, integrações).

## Versão

- A versão está no `pyproject.toml` (`[project] version`), em versionamento semântico.
- Ela aparece em três lugares: `GET /health` (`version` e `commit`), no `info.version` do `/openapi.json` e no header `X-API-Version` de toda resposta.
- Quando a `prod` recebe uma versão nova, o CI cria a tag `vX.Y.Z` e a release no GitHub, com as notas geradas a partir dos PRs. Para gerar uma release, suba a versão no `pyproject.toml` no PR de promoção.

## Compatibilidade

- **Nada quebra dentro de `/api/v1`.** Remover ou renomear campo, mudar tipo ou tornar obrigatório o que era opcional só pode acontecer numa `/api/v2`.
- **Campo novo é sempre opcional** na requisição. Na resposta, o cliente deve ignorar campos que não conhece.
- **Depreciação:** a rota que vai sair passa a responder com o header `Deprecation: true` e um `Sunset` com a data, por pelo menos uma sprint antes de sair.

## Formato de erro

Todo erro responde `application/problem+json` ([RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)):

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Documento não encontrado",
  "code": "not_found",
  "request_id": "3f9c2b7a51e04c8d9a1f0e6b2c4d8a90"
}
```

| Campo | Para que serve |
|---|---|
| `code` | **O app decide por ele**, porque é estável. O texto do `detail` pode mudar |
| `detail` | Mensagem para a pessoa. Por compatibilidade, mantém o formato de antes: texto, objeto (`{"message", "errors"}`) ou, no 422, a lista do Pydantic |
| `errors` | Só no 422: `[{"field": "body.email", "message": "...", "type": "..."}]` |
| `request_id` | O mesmo do header `X-Request-ID`. Peça esse código a quem relatar um erro e procure no log |

Códigos padrão por status: `bad_request` (400), `not_authenticated` (401), `forbidden` (403), `not_found` (404), `conflict` (409), `payload_too_large` (413), `unsupported_media_type` (415), `validation_error` (422), `rate_limited` (429), `internal_error` (500), `service_unavailable` (503). Uma rota pode trocar o código por um mais específico (ex.: `plan_limit_reached`), mandando `code` ou `error` no `detail`.

O erro 500 nunca expõe a exceção: a resposta traz só o `request_id`, e o detalhe técnico fica no log.

## Autenticação

- Sem token, ou com token inválido ou expirado: **401**. O app renova a sessão com `POST /auth/refresh` e repete a requisição.
- Usuário inativo: 403.

## Rastreio

- Mande `X-Request-ID` (até 64 caracteres, só `A-Z a-z 0-9 . _ -`) para correlacionar com o log do app. Sem ele, a API gera um id.
- `GET /health` confere o banco e responde 503 se ele cair. `GET /health/live` só confirma que o processo responde e é o que o Docker usa.
