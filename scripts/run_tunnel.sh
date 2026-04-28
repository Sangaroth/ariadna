#!/usr/bin/env bash
# Tunel ngrok para exponer el servidor local a Mattermost.
# Requiere: ngrok instalado y autenticado (ngrok authtoken <TOKEN>).
# La URL publica generada es la que copiar a la config de Mattermost.

set -euo pipefail

PORT="${ARIADNA_MCP_PORT:-8765}"

echo "Exponiendo puerto ${PORT} via ngrok..."
echo "Copia la URL HTTPS que aparece abajo + '/mcp' a:"
echo "  Mattermost > System Console > Agents > MCP Servers > Server URL"
echo ""
exec ngrok http "$PORT"
