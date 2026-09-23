# Guia de contribuição

Bem-vindo(a)! Este guia define **como o time trabalha** neste repositório. Se é sua primeira vez aqui, antes leia o onboarding em [`docs/onboarding/`](docs/onboarding/README.md) — ele cobre o setup do ambiente e o mapa do código.

## Fluxo de trabalho

1. **Pegue uma tarefa** — trabalhe sempre a partir de uma issue do GitHub. Se a tarefa não existe como issue, crie uma primeiro (título claro + o que define "pronto"). Não comece trabalho grande sem alinhar com o mantenedor.
2. **Crie uma branch a partir da `main`** (a `main` é a base de todo desenvolvimento; a `prod` só recebe promoções, veja [Branches](#branches-main-e-prod)):
   ```
   git checkout main && git pull
   git checkout -b feat/nome-curto-da-tarefa
   ```
   Prefixos: `feat/`, `fix/`, `chore/`, `docs/`, `refactor/`, `test/`.
3. **Commits pequenos, no padrão [Conventional Commits](https://www.conventionalcommits.org/pt-br/)**:
   ```
   feat(invoices): recalcular total ao excluir transação da fatura
   fix(upload): aceitar HEIC do iPhone
   docs: corrigir porta do Postgres no onboarding
   ```
   Escreva a mensagem explicando **o quê e por quê**, não "ajustes".
4. **Antes de abrir o PR**, rode localmente o que o CI vai cobrar: `make lint test`. Se mexeu em `Dockerfile`, `docker-compose*.yml` ou dependências, rode também `make up` e confira `curl localhost:8000/health`.
5. **Abra o PR contra a `main`** preenchendo o template. PRs pequenos (até ~300 linhas de diff) são revisados rápido; PRs gigantes ficam parados — se a tarefa é grande, fatie em PRs sequenciais.
6. **Revisão**: todo PR precisa de **1 aprovação** de outra pessoa do time (o mantenedor pode revisar qualquer um; entre alunos, revisem-se mutuamente — revisar é parte do aprendizado). Responda os comentários com novos commits; não faça force-push depois que a revisão começou.
7. **Merge**: *squash merge* pela interface do GitHub (mantém a `main` com um commit por PR). Quem mergeia apaga a branch.

## Branches: `main` e `prod`

| Branch | Papel | Como recebe código | Imagem publicada |
|---|---|---|---|
| `main` | Integração / homologação. Pode estar instável. | PR de `feat/`, `fix/` etc., *squash merge* | `main`, `sha-xxxxxxx` |
| `prod` | O que está (ou vai estar) em produção. | Só PR `main` → `prod`, *merge commit* | `prod`, `latest`, `sha-xxxxxxx` |

- **Promover para produção:** abra um PR de `main` para `prod` (título `release: <resumo>`), com o CI verde nos dois lados. Use *merge commit*, não squash, para a `prod` continuar sendo ancestral da `main` e as promoções seguintes não gerarem conflito.
- **Hotfix:** branch `fix/...` a partir da `prod`, PR para a `prod` e depois PR da `prod` de volta para a `main` (ou cherry-pick) para a correção não se perder.
- Ninguém commita direto na `prod`. Enquanto não há versão estável, a `prod` serve para testar o fluxo de promoção e o CD.

## Definition of Done

Um PR está pronto quando:

- [ ] O CI está verde (gitleaks CLI + ruff + pytest + build/smoke test da imagem Docker).
- [ ] Mudou regra de negócio? Tem **ao menos um teste** cobrindo a mudança.
- [ ] Mudou modelo de dados? Tem migração Alembic (revisada à mão, não só o autogenerate) e ela roda em banco limpo (`alembic upgrade head` do zero).
- [ ] Você testou manualmente o endpoint afetado (Swagger em `/docs` ou pelo koin-app).
- [ ] Nenhum segredo, dado real ou arquivo gerado foi commitado (leia as [regras de segurança](docs/onboarding/04-SUSTENTACAO.md#segurança--regras-não-negociáveis) — este repo já teve um incidente e as regras são inegociáveis).
- [ ] Se o comportamento visível mudou, a documentação afetada foi atualizada.

## Convenções de código

O detalhe está em [`docs/development/CONVENTIONS.md`](docs/development/CONVENTIONS.md). O essencial:

- Router fino / service gordo; models centralizados em `app/models/`; schemas Pydantic v2 para toda entrada/saída; `async` em todo o caminho de request; siga o `ruff` (line-length 100).
- Mudou contrato de endpoint (request/response)? Avise o time do [koin-app](https://github.com/AppFinanceiro-GECS/koin-app) no PR: os tipos do app espelham os schemas daqui.
- Infra: nada de segredo em `docker-compose*.yml`/`Caddyfile`; tudo que varia por ambiente vai no `.env` e é documentado no `.env.example`.
- Textos de UI em **português (pt-BR)**; código e identificadores em **inglês**.

## O que o CI faz hoje

Em todo push/PR para `main` ou `prod` (`.github/workflows/ci.yml`):

- **Segurança:** gitleaks escaneia os commits em busca de segredos (chaves, tokens, senhas) — qualquer vazamento **bloqueia o merge** (config/allowlist em `.gitleaks.toml`)
- **Lint + testes:** `ruff check .` + `ruff format --check .` + `pytest` (SQLite)
- **Docker:** build da imagem + `docker compose up --wait` + `curl /health` (pega Dockerfile quebrado e migração que não roda em Postgres limpo)
- **Publish (push em `main` ou `prod`):** imagem multi-arch (amd64 + arm64) em `ghcr.io/appfinanceiro-gecs/koin-api`; `main` gera `main` + `sha-xxxxxxx`, `prod` gera `prod` + `latest` + `sha-xxxxxxx`
- **Deploy:** `main` vai para homologação (https://hml.144-22-232-63.sslip.io) e `prod` para produção (https://api.144-22-232-63.sslip.io), com rollback automático se a API não subir. Detalhes em [docs/infra/DEPLOY.md](docs/infra/DEPLOY.md)

Dependências desatualizadas chegam como PRs semanais do **Dependabot** — revisar e mergear esses PRs é tarefa de sustentação como qualquer outra.

## Pre-commit hooks (recomendado — configure no primeiro dia)

Os mesmos checks rodam na sua máquina antes de cada commit, o que evita descobrir o problema só no CI:

```bash
pip install pre-commit     # com o venv ativo
pre-commit install         # na raiz do repo
```

A partir daí, todo `git commit` roda automaticamente: gitleaks (segredos), ruff (lint+format) e checagens de higiene (arquivos grandes, marcadores de merge). Para rodar manualmente em tudo: `pre-commit run --all-files`.

## Dúvidas

- "Onde fica o código de X?" → [`docs/onboarding/02-MAPA-DO-CODIGO.md`](docs/onboarding/02-MAPA-DO-CODIGO.md)
- "Por que isso é assim?" → [`docs/onboarding/03-DECISOES-E-MOTIVOS.md`](docs/onboarding/03-DECISOES-E-MOTIVOS.md)
- Não achou? Abra uma issue com a etiqueta `question` — a resposta pode virar documentação.
