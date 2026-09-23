#!/usr/bin/env bash
# Forced command da chave SSH de deploy do GitHub Actions (instalado em /usr/local/bin/koin-deploy).
# A chave só consegue rodar isto:
#   tar -czf - deploy ghcr_token | ssh deploy@<vm> "<hml|prod> sha-xxxxxxx"
# O tar traz a pasta deploy/ do commit e o GITHUB_TOKEN efêmero do job (só para o pull no GHCR).
# Se a imagem nova não ficar saudável, volta para a anterior.
# Mudou este arquivo? Reinstale na VM à mão (veja docs/infra/DEPLOY.md): o CD não se autoatualiza.
set -euo pipefail

read -r KOIN_ENV TAG _ <<<"${SSH_ORIGINAL_COMMAND:-}"
[[ "${KOIN_ENV:-}" =~ ^(hml|prod)$ ]] || { echo "ambiente inválido: '${KOIN_ENV:-}'" >&2; exit 2; }
[[ "${TAG:-}" =~ ^sha-[0-9a-f]{7,40}$ ]] || { echo "tag inválida: '${TAG:-}'" >&2; exit 2; }

IMAGE=ghcr.io/appfinanceiro-gecs/koin-api
BASE=/opt/koin
ENV_DIR="$BASE/$KOIN_ENV"
[ -f "$ENV_DIR/.env" ] || { echo "$ENV_DIR/.env não existe: crie a partir de deploy/env.example" >&2; exit 2; }
[ -f "$BASE/proxy/.env" ] || { echo "$BASE/proxy/.env não existe" >&2; exit 2; }

exec 9>"$BASE/.deploy.lock"
flock 9

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
tar -xzf - -C "$tmp"

install -D -m 644 "$tmp/deploy/compose.yml" "$ENV_DIR/compose.yml"
install -D -m 644 "$tmp/deploy/proxy/compose.yml" "$BASE/proxy/compose.yml"
install -D -m 644 "$tmp/deploy/proxy/Caddyfile" "$BASE/proxy/caddy/Caddyfile"

set_image() { sed -i '/^API_IMAGE=/d' "$ENV_DIR/.env"; echo "API_IMAGE=$1" >>"$ENV_DIR/.env"; }
compose() { docker compose -p "koin-$KOIN_ENV" --project-directory "$ENV_DIR" -f "$ENV_DIR/compose.yml" "$@"; }

docker network inspect koin-edge >/dev/null 2>&1 || docker network create koin-edge >/dev/null

prev=$(sed -n 's/^API_IMAGE=//p' "$ENV_DIR/.env")
echo "==> $KOIN_ENV: ${prev:-(nenhuma)} -> $IMAGE:$TAG"

export DOCKER_CONFIG="$tmp/docker"
docker login ghcr.io -u github-actions --password-stdin <"$tmp/ghcr_token" >/dev/null
docker pull -q "$IMAGE:$TAG"
docker logout ghcr.io >/dev/null
unset DOCKER_CONFIG

set_image "$IMAGE:$TAG"
if ! compose up -d --wait --wait-timeout 300; then
  echo "==> falhou; logs da api:" >&2
  compose logs --tail 80 api >&2 || true
  if [ -n "$prev" ]; then
    echo "==> rollback para $prev" >&2
    set_image "$prev"
    compose up -d --wait --wait-timeout 300 || true
  fi
  exit 1
fi

docker compose -p koin-proxy --project-directory "$BASE/proxy" -f "$BASE/proxy/compose.yml" up -d --wait
docker compose -p koin-proxy --project-directory "$BASE/proxy" -f "$BASE/proxy/compose.yml" \
  exec -T caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null

docker image prune -af --filter "until=168h" >/dev/null || true
echo "==> $KOIN_ENV no ar com $IMAGE:$TAG"
