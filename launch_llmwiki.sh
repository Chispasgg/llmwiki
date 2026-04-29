#!/usr/bin/env bash

set -euo pipefail

# Require bash >= 4.3 (wait -n)
if (( BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 3) )); then
  echo "ERROR: Se requiere bash >= 4.3 (tienes ${BASH_VERSION}). En macOS: brew install bash" >&2
  exit 1
fi

# ── Helpers ──────────────────────────────────────────────────────────────────

log() {
  echo "[$(date '+%H:%M:%S')] $*"
}

step() {
  echo
  echo "──────────────────────────────────────────────────────"
  echo "[$(date '+%H:%M:%S')] $*"
  echo "──────────────────────────────────────────────────────"
}

die() {
  echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2
  exit 1
}

check_tool() {
  local tool="$1"
  if ! command -v "$tool" &>/dev/null; then
    die "'$tool' no encontrado en PATH. Instálalo antes de continuar."
  fi
  log "'$tool' disponible: $($tool --version 2>&1 | head -1)"
}

_get_local_ip() {
  # Abre un socket UDP hacia una IP pública (no envía tráfico) para
  # determinar qué interfaz usaría el kernel — devuelve esa IP local.
  python3 -c "
import socket
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
    try:
        s.connect(('8.8.8.8', 80))
        print(s.getsockname()[0])
    except Exception:
        print('127.0.0.1')
"
}

# ── Configuración ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/config/llmwiki-launcher.conf"

step "Cargando configuración desde ${CONFIG_FILE}"

if [[ ! -f "${CONFIG_FILE}" ]]; then
  die "No se encontró el archivo de configuración: ${CONFIG_FILE}"
fi

# shellcheck disable=SC1090
source "${CONFIG_FILE}"

for var in LLMWIKI_ROOT WORKSPACES_ROOT API_PORT WEB_PORT; do
  if [[ -z "${!var:-}" ]]; then
    die "La configuración debe definir ${var}."
  fi
  log "  ${var}=${!var}"
done

# ── Resolución de IP LAN ───────────────────────────────────────────────────────

if [[ -z "${LAN_HOST:-}" ]]; then
  LAN_HOST="$(_get_local_ip)"
  log "IP LAN auto-detectada: ${LAN_HOST}"
else
  log "IP LAN configurada: ${LAN_HOST}"
fi

if [[ ! -x "${LLMWIKI_ROOT}/llmwiki" ]]; then
  die "No se encontró el ejecutable de llmwiki en: ${LLMWIKI_ROOT}/llmwiki"
fi

# ── Verificar herramientas ─────────────────────────────────────────────────────

step "Verificando herramientas del sistema"

check_tool uv
check_tool bun

# ── Dependencias Python (API) ─────────────────────────────────────────────────

step "Sincronizando dependencias Python de la API"

log "Ejecutando: uv sync en ${LLMWIKI_ROOT}/api"
(
  cd "${LLMWIKI_ROOT}/api"
  uv sync --group dev 2>&1 | while IFS= read -r line; do
    log "  [uv] $line"
  done
) || die "Falló uv sync para la API. Revisa ${LLMWIKI_ROOT}/api/pyproject.toml."

API_PYTHON="${LLMWIKI_ROOT}/api/.venv/bin/python"
if [[ ! -x "${API_PYTHON}" ]]; then
  die "No se encontró el Python del entorno virtual en: ${API_PYTHON}"
fi
log "Python API: $(${API_PYTHON} --version)"

# ── Dependencias Node.js (frontend) ───────────────────────────────────────────

step "Sincronizando dependencias Node.js del frontend"

log "Ejecutando: bun install en ${LLMWIKI_ROOT}/web"
(
  cd "${LLMWIKI_ROOT}/web"
  bun install 2>&1 | while IFS= read -r line; do
    log "  [bun] $line"
  done
) || die "Falló bun install para el frontend. Revisa ${LLMWIKI_ROOT}/web/package.json."

# ── Selección de workspace ─────────────────────────────────────────────────────

step "Buscando workspaces disponibles en ${WORKSPACES_ROOT}"

mapfile -t workspace_wikis < <(find "${WORKSPACES_ROOT}" -mindepth 2 -maxdepth 4 -type d -name wiki | sort)

if [[ ${#workspace_wikis[@]} -eq 0 ]]; then
  die "No se encontraron workspaces con carpeta wiki dentro de: ${WORKSPACES_ROOT}"
fi

declare -a workspaces=()

echo
echo "Workspaces disponibles:"
for wiki_dir in "${workspace_wikis[@]}"; do
  workspace_dir="$(dirname "${wiki_dir}")"
  workspaces+=("${workspace_dir}")
  index="${#workspaces[@]}"
  echo "  ${index}) ${workspace_dir}"
done

echo
read -r -p "Elige un workspace por número: " selection

if [[ ! "${selection}" =~ ^[0-9]+$ ]]; then
  die "Selección inválida: debe ser un número."
fi

if (( selection < 1 || selection > ${#workspaces[@]} )); then
  die "Selección inválida: fuera de rango (1-${#workspaces[@]})."
fi

selected_workspace="${workspaces[selection-1]}"
log "Workspace seleccionado: ${selected_workspace}"

# ── Inicialización del workspace ──────────────────────────────────────────────

if [[ ! -f "${selected_workspace}/.llmwiki/index.db" ]]; then
  step "Inicializando workspace por primera vez"
  "${API_PYTHON}" "${LLMWIKI_ROOT}/llmwiki" init "${selected_workspace}" \
    && log "Workspace inicializado correctamente." \
    || die "Falló la inicialización del workspace."
fi

# ── Lanzamiento de procesos ───────────────────────────────────────────────────

# URLs efectivas: valor explícito del conf > construido desde LAN_HOST
effective_app_url="${APP_URL:-http://${LAN_HOST}:${WEB_PORT}}"
effective_cors="${CORS_ORIGIN:-${effective_app_url}}"
effective_api_url="${NEXT_PUBLIC_API_URL:-http://${LAN_HOST}:${API_PORT}}"
internal_api_url="http://${LAN_HOST}:${API_PORT}"

api_pid=""
web_pid=""

cleanup() {
  trap - INT TERM EXIT
  echo
  log "Deteniendo procesos..."
  if [[ -n "${api_pid}" ]] && kill -0 "${api_pid}" 2>/dev/null; then
    log "  Deteniendo API (PID ${api_pid})..."
    kill "${api_pid}" 2>/dev/null || true
  fi
  if [[ -n "${web_pid}" ]] && kill -0 "${web_pid}" 2>/dev/null; then
    log "  Deteniendo frontend (PID ${web_pid})..."
    kill "${web_pid}" 2>/dev/null || true
  fi
  wait "${api_pid}" "${web_pid}" 2>/dev/null || true
  log "Todos los procesos detenidos."
}

trap cleanup INT TERM EXIT

step "Lanzando API en ${internal_api_url}"
(
  cd "${LLMWIKI_ROOT}/api"
  export MODE="local"
  export WORKSPACE_PATH="${selected_workspace}"
  export DATABASE_URL=""
  export APP_URL="${effective_cors}"
  # API_URL: URL de auto-referencia del servidor (siempre la IP de escucha, no la URL pública del cliente)
  export API_URL="${internal_api_url}"
  exec "${API_PYTHON}" -m uvicorn main:app --host 0.0.0.0 --port "${API_PORT}"
) &
api_pid=$!
log "  API iniciada con PID ${api_pid}"

step "Lanzando frontend en ${effective_app_url}"
(
  cd "${LLMWIKI_ROOT}/web"
  export NEXT_PUBLIC_MODE="local"
  export NEXT_PUBLIC_API_URL="${effective_api_url}"
  export NEXT_TELEMETRY_DISABLED="1"
  export PORT="${WEB_PORT}"
  export HOSTNAME="0.0.0.0"
  exec bun run dev
) &
web_pid=$!
log "  Frontend iniciado con PID ${web_pid}"

echo
echo "════════════════════════════════════════════════════════"
echo "  API:      ${internal_api_url}"
echo "  Frontend: ${effective_app_url}"
echo "  MCP:      ${MCP_TRANSPORT} (puerto ${MCP_PORT})"
if [[ "${MCP_TRANSPORT}" == "streamable-http" ]]; then
  echo "  MCP URL:  http://${LAN_HOST}:${MCP_PORT}/mcp"
else
  echo "  MCP:      Para acceso LAN, configura MCP_TRANSPORT=streamable-http en el conf"
fi
echo "  Workspace: ${selected_workspace}"
echo "  Ctrl+C para detener ambos procesos."
echo "════════════════════════════════════════════════════════"
echo

wait -n "${api_pid}" "${web_pid}"
exit_code=$?
log "Un proceso ha terminado con código ${exit_code}. Deteniendo el resto..."
