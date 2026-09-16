# 03 — Decisões de arquitetura e seus motivos

Registro das decisões estruturais do projeto (formato ADR compacto). O objetivo é responder "por que é assim?" antes que você tente "consertar" algo que é intencional — e deixar claro o que É dívida técnica (essas estão no [04-SUSTENTACAO.md](04-SUSTENTACAO.md)).

---

## ADR-001 — Monolito modular, não microserviços

**Decisão:** um único backend FastAPI, organizado em 29 módulos verticais (`app/modules/<feature>/`) com routers finos e services gordos.

**Motivo:** o projeto é mantido por um time pequeno e roda em infraestrutura mínima (um container). Microserviços adicionariam custo operacional (deploy, observabilidade, rede) sem benefício nessa escala. A estrutura por módulos mantém as fronteiras claras e permitiria extrair um módulo para serviço próprio no futuro, se algum dia fizer sentido.

**Consequência:** disciplina é necessária — um módulo não deve importar service de outro módulo sem pensar; se dois módulos se entrelaçam demais, discuta antes.

## ADR-002 — SQLite no dev, PostgreSQL na produção

**Decisão:** `DATABASE_URL` padrão é SQLite (`aiosqlite`); produção usa PostgreSQL (`asyncpg`). O mesmo código SQLAlchemy async serve os dois.

**Motivo:** onboarding sem fricção — ninguém precisa de Docker ou de um Postgres instalado para desenvolver. Os testes também usam SQLite in-memory, o que os torna rápidos e sem dependências.

**Consequência (trade-off consciente):** existe risco de divergência de dialeto — algo que funciona no SQLite pode se comportar diferente no Postgres (tipos de data, constraints, `ILIKE`, concorrência). Para mudanças sensíveis a banco, teste também contra o Postgres do `docker-compose` antes do PR.

## ADR-003 — APScheduler em vez de Celery/Redis

**Decisão:** jobs agendados (recorrências, projeções, limpezas) rodam com APScheduler dentro do processo da API, no lifespan do FastAPI. O Celery foi avaliado e descartado.

**Motivo:** Celery exigiria um broker (Redis) e um worker separado — mais dois processos para operar e pagar, num app que roda em um container com memória limitada. O APScheduler resolve os agendamentos atuais sem infraestrutura extra.

**Consequência:** ⚠️ isso **só funciona com uma réplica**. Se um dia o backend rodar com múltiplas instâncias, os jobs dispararão duplicados — nesse cenário será preciso migrar para fila externa ou eleger um líder. Restos de config do Celery ainda existem no código (`app/core/celery_config.py`) e são código morto a remover.

## ADR-004 — Extração multi-provider com Gemini como padrão

**Decisão:** a extração de documentos usa uma abstração `BaseProvider` com implementações Google (Gemini), Mistral, OpenAI e Anthropic. O padrão é **Gemini** (`VISION_PROVIDER=google`).

**Motivo:** benchmarks internos (abril/2026) mostraram o Gemini ~2,2x mais rápido com precisão igual ou melhor nas faturas testadas, além de ter camada gratuita generosa para dev. A abstração existe porque provedores de LLM mudam de preço/qualidade rápido — trocar de provider é mudar uma env var, não reescrever o pipeline.

**Consequência:** só Google e Mistral têm SDK instalado; os providers OpenAI/Anthropic existem como código mas não são exercitados. Prompts são arquivos Markdown versionados (`modules/documents/prompts/`), inclusive específicos por banco — melhorar a extração de um banco geralmente é editar prompt, não código.

## ADR-005 — Registro fechado por convite

**Decisão:** não existe cadastro público. Usuários entram por convite (com licenças controladas pelo módulo `admin`) ou via script `create_admin.py`.

**Motivo:** o app lida com dados financeiros reais e cada usuário ativo consome cota de LLM (custo). O modelo de convites controla custo e exposição enquanto o produto amadurece.

**Consequência:** todo fluxo de teste começa criando usuário por script ou convite — não perca tempo procurando a tela de signup.

## ADR-006 — JWT no frontend + API Keys para integrações

**Decisão:** dois esquemas de autenticação: JWT Bearer (HS256, access 30min/refresh 7d) para o SPA, e API Keys `biv_...` (armazenadas como SHA-256) para integrações externas (servidor MCP, scripts).

**Motivo:** JWT com refresh dá sessão fluida no browser sem estado no servidor. API Keys dão acesso programático revogável e por usuário, sem expor senha — e o servidor MCP consome a **API REST** com a chave (em vez de acessar o banco direto), o que preserva o isolamento entre usuários.

**Consequência:** existem dois servidores MCP no repo: `mcp-biveto-db/` (raiz, read-only via API — o suportado) e `backend/mcp_server.py` (legado, acessa o banco direto). Use o primeiro; o segundo é candidato a remoção.

## ADR-007 — Frontend servido pelo backend em produção

**Decisão:** em produção não há servidor de frontend separado: o `backend/Dockerfile` (multi-stage) builda o React e o FastAPI serve os estáticos na mesma origem, porta 8080.

**Motivo:** um único artefato de deploy, sem CORS em produção, sem custo de hosting extra.

**Consequência:** o build do container usa a **raiz do repo** como contexto: `docker build -f backend/Dockerfile .`. O catch-all de SPA no FastAPI precisa continuar por último na ordem de rotas. Migrações **não** rodam no start do container — `alembic upgrade head` é passo manual do deploy.

## ADR-008 — Sem biblioteca de componentes de UI

**Decisão:** o frontend usa Tailwind puro; componentes construídos à mão, sem Radix/shadcn/MUI.

**Motivo:** controle total do visual (identidade própria do produto) e bundle menor; a decisão foi tomada no início e trocar agora custaria mais do que rende.

**Consequência:** consistência visual depende de copiar padrões existentes. Antes de criar um componente, procure um parecido em `src/components/`.

## ADR-009 — Saldo calculado, nunca armazenado

**Decisão:** o saldo de uma conta é sempre derivado da soma das transações — não existe coluna `balance` atualizada incrementalmente.

**Motivo:** elimina toda uma classe de bugs de sincronização (saldo divergindo das transações após edição/exclusão/importação). Correção > performance nessa escala.

**Consequência:** consultas de saldo agregam transações; se um dia isso pesar, a resposta é view materializada/cache — não uma coluna mutável.

## ADR-010 — Histórico do repositório recomeçado em agosto/2026 (`biveto-fin`)

**Decisão:** o repositório público `biveto-fin` foi criado a partir do histórico **reescrito** do repo original (privado), após uma auditoria de segurança.

**Motivo:** o histórico antigo continha segredos e dados pessoais reais (chave de API, dump de banco, extratos) que foram purgados com `git filter-repo`. Como o GitHub retém objetos antigos acessíveis por SHA e via `refs/pull`, publicar o repo original nunca seria seguro — daí o repositório novo.

**Consequência:** **o repo antigo permanece privado para sempre**; nunca puxe ou cite commits dele. As regras do que jamais commitar estão no [04-SUSTENTACAO.md](04-SUSTENTACAO.md) e no `.gitignore` (que é parte da defesa — não o afrouxe).
