# Documentação do biveto-api

> Este repositório nasceu da divisão do antigo monorepo `biveto-fin` em **biveto-api** (este: backend + infra) e **biveto-app** (mobile React Native). As docs abaixo vieram do monorepo; onde falarem de `frontend/`, Vite ou PWA, o equivalente atual é o [biveto-app](https://github.com/AppFinanceiro-GECS/biveto-app). Para subir o ambiente, siga o [README](../README.md) (Docker).

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

- [integrations/MCP_TOOLS.md](integrations/MCP_TOOLS.md) (servidor em `tools/mcp-biveto-db`)
- [integrations/MISTRAL_INTEGRATION.md](integrations/MISTRAL_INTEGRATION.md)
