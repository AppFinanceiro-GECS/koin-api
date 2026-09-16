# Onboarding — comece por aqui

Documentação de entrada para novos integrantes do time (escrita pensando em quem nunca viu o projeto). Leia na ordem:

| # | Documento | O que responde |
|---|---|---|
| 1 | [01-COMECE-AQUI.md](01-COMECE-AQUI.md) | O que é o Biveto, glossário do domínio financeiro e setup do ambiente (Windows e Linux/Mac) até o app rodando |
| 2 | [02-MAPA-DO-CODIGO.md](02-MAPA-DO-CODIGO.md) | Como o código está organizado, fluxo de uma requisição, e "quero mexer na feature X, começo por onde" |
| 3 | [03-DECISOES-E-MOTIVOS.md](03-DECISOES-E-MOTIVOS.md) | Por que o projeto é do jeito que é — as decisões de arquitetura e seus trade-offs |
| 4 | [04-SUSTENTACAO.md](04-SUSTENTACAO.md) | Runbook de sustentação: testes, troubleshooting, segurança e o backlog de dívidas técnicas conhecidas |

O processo de contribuição (branches, commits, PRs, o que o CI cobra) está no [CONTRIBUTING.md](../../CONTRIBUTING.md) na raiz.

> **Divisão de repositórios (set/2026):** o monorepo `biveto-fin` virou `biveto-api` (este) e `biveto-app` (React Native). Setup do backend agora é via Docker: veja o [README](../../README.md). Trechos sobre `frontend/` (Vite/PWA) valem como referência de regra de negócio, não de setup.

> **Estado desta documentação:** escrita em agosto/2026 a partir de uma auditoria completa do código. Os docs mais antigos em `docs/` (jan–mar/2026) têm conteúdo valioso, mas alguns caminhos de arquivo estão desatualizados — em caso de conflito, confie no que está aqui e no código.
