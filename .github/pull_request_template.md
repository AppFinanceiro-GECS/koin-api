## O que este PR faz

<!-- 2-3 frases: o problema e a solução. Link da issue: Closes #NN -->

## Como testar

<!-- Passo a passo para o revisor reproduzir: telas, endpoints, comandos -->

## Checklist (Definition of Done)

- [ ] `make lint test` passa localmente
- [ ] Regra de negócio alterada tem teste cobrindo
- [ ] Migração Alembic incluída e testada em banco limpo (se mudei modelo)
- [ ] `docker compose up --build` sobe e `/health` responde (se mexi em Dockerfile/compose/deps)
- [ ] Testei manualmente o endpoint afetado
- [ ] Nenhum segredo/dado real/arquivo gerado no diff
- [ ] Docs atualizadas se o comportamento visível mudou

## Logs / evidências

<!-- Saída de curl, logs do container etc. Se não se aplica, apague a seção -->
