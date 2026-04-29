#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MCP_DIR="$SCRIPT_DIR/mcp"
VENV="$MCP_DIR/.venv"
WORKSPACE="${1:-$SCRIPT_DIR/../workspace}"

# Crear/sincronizar venv con uv (Python 3.11, igual que el lock)
uv venv "$VENV" --python 3.11 --quiet 2>/dev/null || true
uv pip sync "$MCP_DIR/requirements.lock" --python "$VENV/bin/python" --require-hashes --quiet

# Lanzar servidor MCP
PYTHONPATH="$MCP_DIR" exec "$VENV/bin/python" -m local_server --workspace "$WORKSPACE"
