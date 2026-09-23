# Documentação do koin-api

> Este repositório nasceu da divisão do antigo monorepo `biveto-fin` em **koin-api** (este: backend + infra) e **koin-app** (mobile React Native). As docs abaixo vieram do monorepo; onde falarem de `frontend/`, Vite ou PWA, o equivalente atual é o [koin-app](https://github.com/AppFinanceiro-GECS/koin-app). Para subir o ambiente, siga o [README](../README.md) (Docker).
>
> Em set/2026 o produto passou de **Biveto** para **Koin** e os repos viraram `koin-api`/`koin-app`. Referências a "Biveto" que sobraram são históricas (o monorepo `biveto-fin`, a migração de gamificação, `web-legado/`) ou domínios `biveto.com` ainda sem substituto.

## Infra

- [infra/DEPLOY.md](infra/DEPLOY.md): VPS, HTTPS, atualização, rollback e backup

## Onboarding

- [onboarding/](onboarding/README.md): domínio, mapa do código, decisões e sustentação

## Arquitetura

- [architecture/OVERVIEW.md](architecture/OVERVIEW.md)
- [architecture/DATABASE_SCHEMA.md](architecture/DATABASE_SCHEMA.md)

## Backend

- [backend/README.md](backend/README.md)
- [backend/MODULES.md](backend/MODULES.md)
- [backend/BALANCE_FLOW_GUIDE.md](backend/BALANCE_FLOW_GUIDE.md)
- [backend/CLASSIFIER_README.md](backend/CLASSIFIER_README.md)

## Desenvolvimento

- [development/GETTING_STARTED.md](development/GETTING_STARTED.md)
- [development/CONVENTIONS.md](development/CONVENTIONS.md)

## Negócio e segurança

- [business/LOGIC_MAP.md](business/LOGIC_MAP.md)
- [business/AUDIT_REPORT.md](business/AUDIT_REPORT.md)
- [business/SECURITY_AUDIT_2026-02.md](business/SECURITY_AUDIT_2026-02.md)
- [SECURITY_REMEDIATION_CHECKLIST.md](SECURITY_REMEDIATION_CHECKLIST.md)

## Integrações

- [integrations/MCP_TOOLS.md](integrations/MCP_TOOLS.md) (servidor em `tools/mcp-koin-db`)
- [integrations/MISTRAL_INTEGRATION.md](integrations/MISTRAL_INTEGRATION.md)
