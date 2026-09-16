# Deploy na VPS

Stack de produção: `docker-compose.yml` + `docker-compose.prod.yml`.

| Serviço | Imagem | Exposto |
|---|---|---|
| `caddy` | `caddy:2-alpine` | 80, 443 (HTTPS automático) |
| `api` | build local ou `ghcr.io/appfinanceiro-gecs/biveto-api` | só na rede interna (8000) |
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
git clone https://github.com/AppFinanceiro-GECS/biveto-api.git && cd biveto-api
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

Usando a imagem do GHCR em vez de build local: coloque `API_IMAGE=ghcr.io/appfinanceiro-gecs/biveto-api:sha-xxxxxxx` no `.env` e rode
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
docker run --rm -v biveto_uploads:/data -v "$PWD":/backup alpine tar czf /backup/uploads-$(date +%F).tgz -C /data .
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
