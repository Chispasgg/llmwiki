#!/usr/bin/env bash
# Deploy llmwiki en producción.
# Uso:
#   ./deploy.sh              → rebuild api web nginx + up -d + restart nginx
#   ./deploy.sh api          → rebuild api + up -d api + restart nginx
#   ./deploy.sh api web      → rebuild api web + up -d api web + restart nginx
#   ./deploy.sh nginx        → rebuild nginx + up -d nginx (sin restart extra)
set -euo pipefail

COMPOSE_FILE="docker-compose.server.yml"
SERVICES=("${@:-api web nginx}")

# Si no se pasan argumentos, usar los servicios por defecto
if [[ $# -eq 0 ]]; then
    SERVICES=(api web nginx)
fi

echo "→ git pull"
git pull

echo "→ build: ${SERVICES[*]}"
docker compose -f "$COMPOSE_FILE" build "${SERVICES[@]}"

echo "→ up -d: ${SERVICES[*]}"
docker compose -f "$COMPOSE_FILE" up -d "${SERVICES[@]}"

# Reiniciar nginx si no estaba ya en la lista de servicios a desplegar,
# para que resuelva los nuevos IPs de los contenedores reconstruidos.
NEEDS_NGINX_RESTART=true
for s in "${SERVICES[@]}"; do
    [[ "$s" == "nginx" ]] && NEEDS_NGINX_RESTART=false && break
done

if $NEEDS_NGINX_RESTART; then
    echo "→ restart nginx"
    docker compose -f "$COMPOSE_FILE" restart nginx
fi

echo "→ estado"
docker compose -f "$COMPOSE_FILE" ps
