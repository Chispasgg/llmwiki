#!/usr/bin/env bash
# Deploy llmwiki en producción.
# El proxy HTTP frontal es un nginx COMPARTIDO externo al stack (central-ngix en
# server_ia, edge-nginx en AWS) que enruta a api/web por sus puertos de host
# (1502/1503); llmwiki no lleva su propio nginx.
# Uso:
#   ./deploy.sh              → rebuild api web + up -d
#   ./deploy.sh api          → rebuild api + up -d api
#   ./deploy.sh api web      → rebuild api web + up -d api web
set -euo pipefail

COMPOSE_FILE="docker-compose.server.yml"
SERVICES=("${@:-api web}")

# Si no se pasan argumentos, usar los servicios por defecto
if [[ $# -eq 0 ]]; then
    SERVICES=(api web)
fi

echo "→ git pull"
git pull

echo "→ build: ${SERVICES[*]}"
docker compose -f "$COMPOSE_FILE" build "${SERVICES[@]}"

echo "→ up -d: ${SERVICES[*]}"
docker compose -f "$COMPOSE_FILE" up -d "${SERVICES[@]}"

echo "→ estado"
docker compose -f "$COMPOSE_FILE" ps
