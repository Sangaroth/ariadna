#!/usr/bin/env bash
# Arranca el servidor MCP de Ariadna en puerto 8765.
# Si tienes ngrok configurado, lo expone al exterior en otra terminal:
#   ngrok http 8765
# La URL publica (ej. https://abcd-1234.ngrok-free.app) es la que configuras
# en Mattermost > System Console > Agents > MCP Servers > Server URL:
#   https://abcd-1234.ngrok-free.app/mcp

set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

PORT="${ARIADNA_MCP_PORT:-8765}"
HOST="${ARIADNA_MCP_HOST:-0.0.0.0}"

echo "Arrancando Ariadna MCP en http://${HOST}:${PORT}/mcp"
exec python -m ariadna.mcp_server --host "$HOST" --port "$PORT" --warm
