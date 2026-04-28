#!/usr/bin/env bash
# Test directo del servidor MCP en localhost
curl -s -X POST http://127.0.0.1:8765/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"search_corpus\",\"arguments\":{\"query\":\"sombra Peter Pan\",\"category\":\"analisis de obra\",\"top_k\":3}}}" \
  2>&1 | head -60

