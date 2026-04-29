#!/usr/bin/env bash

set -euo pipefail

# ── Helpers ──────────────────────────────────────────────────────────────────

log() {
  echo "[$(date '+%H:%M:%S')] $*"
}

die() {
  echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2
  exit 1
}

# ── Configuración ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MCP_DIR="${SCRIPT_DIR}/mcp"
WORKSPACE="${1:-${SCRIPT_DIR}/../workspace}"
WORKSPACE="$(cd "${WORKSPACE}" 2>/dev/null && pwd)" \
  || die "El directorio de workspace no existe: ${WORKSPACE}"

log "Directorio MCP: ${MCP_DIR}"
log "Workspace: ${WORKSPACE}"

# ── Verificar herramientas ─────────────────────────────────────────────────────

if ! command -v uv &>/dev/null; then
  die "'uv' no encontrado en PATH. Instálalo con: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi
log "uv disponible: $(uv --version)"

# ── Sincronizar dependencias ───────────────────────────────────────────────────

if [[ ! -f "${MCP_DIR}/pyproject.toml" ]]; then
  die "No se encontró pyproject.toml en: ${MCP_DIR}"
fi

log "Sincronizando dependencias Python del MCP..."
(
  cd "${MCP_DIR}"
  uv sync 2>&1 | while IFS= read -r line; do
    log "  [uv] $line"
  done
) || die "Falló uv sync en ${MCP_DIR}. Revisa pyproject.toml."

VENV="${MCP_DIR}/.venv"
MCP_PYTHON="${VENV}/bin/python"

if [[ ! -x "${MCP_PYTHON}" ]]; then
  die "No se encontró el intérprete Python en: ${MCP_PYTHON}"
fi
log "Python MCP: $(${MCP_PYTHON} --version)"

# ── Lanzar servidor MCP ────────────────────────────────────────────────────────

log "Iniciando servidor MCP local para workspace: ${WORKSPACE}"
PYTHONPATH="${MCP_DIR}" exec "${MCP_PYTHON}" -m local_server --workspace "${WORKSPACE}"
