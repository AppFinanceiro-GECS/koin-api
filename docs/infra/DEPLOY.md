# Deploy

## Ambientes atuais (CD automático)

A API roda numa VM da Oracle Cloud (Always Free, São Paulo: `koin-01`, ARM 4 OCPU/24 GB, Ubuntu 24.04). O deploy é feito pelo job `deploy` do [`ci.yml`](../../.github/workflows/ci.yml) depois que lint, testes, smoke test e publish passam:

| Branch | Environment no GitHub | URL | Stack na VM |
|---|---|---|---|
| `main` | `homologacao` | https://hml.144-22-232-63.sslip.io | `/opt/koin/hml` (projeto `koin-hml`) |
| `prod` | `producao` | https://api.144-22-232-63.sslip.io | `/opt/koin/prod` (projeto `koin-prod`) |

Swagger em `<URL>/docs`. Os domínios `sslip.io` resolvem para o IP embutido no nome; ao trocar por um domínio próprio, mude `HML_DOMAIN`/`PROD_DOMAIN` em `/opt/koin/proxy/.env`, a variável `PUBLIC_URL` de cada environment e o `eas.json` do koin-app.

Como funciona:

1. O CI gera a imagem nativamente para `amd64` e `arm64` e publica em `ghcr.io/appfinanceiro-gecs/koin-api` (`sha-xxxxxxx`).
2. O job `deploy` envia a pasta [`deploy/`](../../deploy) do commit por SSH para o usuário `deploy` da VM. A chave (secret `DEPLOY_SSH_KEY`) só executa o [`koin-deploy`](../../deploy/koin-deploy.sh), que atualiza os compose, faz o pull da tag, sobe a stack com `--wait` e, **se a API não ficar saudável, volta para a imagem anterior**.
3. Um Caddy compartilhado ([`deploy/proxy`](../../deploy/proxy)) serve os dois domínios com HTTPS e encaminha cada um para a API do seu ambiente pela rede Docker `koin-edge`. Cada ambiente tem o próprio Postgres.
4. O job termina com `curl <PUBLIC_URL>/health`.

Segredos (senhas do banco, `SECRET_KEY`, chaves de IA, SMTP) existem **só** em `/opt/koin/<env>/.env` na VM, com modelo em [`deploy/env.example`](../../deploy/env.example). As migrações rodam no start do container.

Operação na VM (`ssh ubuntu@144.22.232.63`, chave com o grupo de infra):

```bash
cd /opt/koin/hml    # ou prod
sudo -u deploy docker compose -p koin-hml logs -f api
sudo -u deploy docker compose -p koin-hml exec api python scripts/create_admin.py "email" "senha" "Nome"
sudo -u deploy docker compose -p koin-hml exec db pg_dump -U koin koin_db > backup.sql
```

**Rollback manual:** rode de novo o job `deploy` de um commit anterior (Actions → CI → *Re-run jobs*), ou na VM troque `API_IMAGE` no `.env` para a tag `sha-` anterior e rode `sudo -u deploy docker compose -p koin-<env> up -d --wait`.

**Mudou `deploy/koin-deploy.sh`?** Ele não se atualiza sozinho (é o comando que a chave executa). Reinstale: `scp deploy/koin-deploy.sh ubuntu@144.22.232.63:/tmp/ && ssh ubuntu@144.22.232.63 'sudo install -m 755 /tmp/koin-deploy.sh /usr/local/bin/koin-deploy'`.

## Deploy manual numa VPS qualquer

O que segue abaixo é o caminho sem CD, com um único ambiente: Stack de produção: `docker-compose.yml` + `docker-compose.prod.yml`.

| Serviço | Imagem | Exposto |
|---|---|---|
| `caddy` | `caddy:2-alpine` | 80, 443 (HTTPS automático) |
| `api` | build local ou `ghcr.io/appfinanceiro-gecs/koin-api` | só na rede interna (8000) |
| `db` | `postgres:16-alpine` | só na rede interna (5432) |

Volumes persistentes: `postgres_data` (banco), `uploads` (arquivos enviados), `caddy_data` (certificados).

## Requisitos da VPS

- Linux (Ubuntu 22.04+/Debian 12), 2 GB de RAM já dá conta (API limitada a 1 GB, Postgres a 512 MB)
- Docker Engine + plugin Compose v2
- Registro DNS `A`/`AAAA` do domínio da API (ex.: `api.biveto.com`) apontando para o IP da VPS
- Firewall liberando 22, 80 e 443

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # relogar depois
sudo ufw allow OpenSSH && sudo ufw allow 80 && sudo ufw allow 443/tcp && sudo ufw allow 443/udp && sudo ufw enable
```

## Primeiro deploy

```bash
git clone https://github.com/AppFinanceiro-GECS/koin-api.git && cd koin-api
make env                 # gera .env com SECRET_KEY aleatório
```

Edite o `.env`:

```dotenv
DEBUG=false
ENVIRONMENT=production
API_DOMAIN=api.biveto.com
POSTGRES_PASSWORD=<openssl rand -hex 24>
GOOGLE_API_KEY=<chave do Gemini>
SMTP_PASSWORD=<senha do e-mail>
```

> `DEBUG=false` é obrigatório em produção: liga HSTS e troca a lista de CORS de desenvolvimento pela `CORS_ORIGINS`.
> Trocar `POSTGRES_PASSWORD` **depois** que o volume do banco já foi criado não muda a senha dentro do Postgres; defina antes do primeiro `up`.

```bash
make prod-up
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
curl https://api.biveto.com/health
make create-admin email=admin@biveto.com senha='...' nome='Admin'
```

## Atualizar

```bash
git pull
make prod-up             # rebuild; as migrações rodam no start do container
```

Usando a imagem do GHCR em vez de build local: coloque `API_IMAGE=ghcr.io/appfinanceiro-gecs/koin-api:sha-xxxxxxx` no `.env` (produção usa só tags `sha-` publicadas a partir da branch `prod`; as tags `main`/`prod`/`latest` são móveis e servem para homologação) e rode
`docker compose -f docker-compose.yml -f docker-compose.prod.yml pull api && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build`.

**Rollback:** aponte `API_IMAGE` para a tag `sha-` anterior e rode o mesmo comando. Se a versão nova trouxe migração, faça `alembic downgrade` antes (`docker compose exec api alembic downgrade -1`) ou restaure o backup.

## Backup

Banco:

```bash
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > backup-$(date +%F).dump
```

Restaurar:

```bash
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < backup-AAAA-MM-DD.dump
```

Uploads:

```bash
docker run --rm -v koin_uploads:/data -v "$PWD":/backup alpine tar czf /backup/uploads-$(date +%F).tgz -C /data .
```

Sugestão: cron diário com os dois comandos acima, copiando os arquivos para object storage (e **nunca** para o repositório; `*.dump` já está no `.gitignore`).

## Operação

| Tarefa | Comando |
|---|---|
| Logs | `make prod-logs` ou `docker compose logs -f api` |
| Shell na API | `docker compose exec api sh` |
| psql | `docker compose exec db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'` |
| Limpar uploads antigos | `docker compose exec api python scripts/cleanup_uploads.py --days 30` |
| Espaço em disco | `docker system df` / `docker image prune` |

## Decisões

- **1 worker uvicorn.** O APScheduler roda dentro do processo da API; com N workers cada job rodaria N vezes. Para escalar horizontalmente, primeiro mover o scheduler para um container próprio.
- **Migrações no entrypoint.** Com uma única réplica é o caminho mais simples. Com várias réplicas, desligue (`RUN_MIGRATIONS=false`) e rode `alembic upgrade head` como passo separado do deploy.
- **Caddy em vez de Nginx + Certbot.** Certificado e renovação automáticos com um arquivo de 8 linhas.
- **Uploads em volume local.** Suficiente para o MVP; o próximo passo é object storage (S3 compatível).
