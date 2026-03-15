#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <obsidian-agent-config-path> [codex-command]" >&2
  exit 1
fi

CONFIG_PATH="$1"
CODEX_CMD="${2:-codex}"
TMP_DIR="$(mktemp -d)"
SCHEMA_PATH="$TMP_DIR/status-schema.json"
OUTPUT_PATH="$TMP_DIR/status-output.json"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

printf '%s\n' '{"type":"object","properties":{"status":{"type":"string"}},"required":["status"],"additionalProperties":false}' > "$SCHEMA_PATH"

echo "== simple non-interactive run =="
"$CODEX_CMD" -a never exec --sandbox read-only --ephemeral \
  "Say READY and nothing else."

echo
echo "== structured output run =="
"$CODEX_CMD" -a never exec --sandbox read-only --ephemeral \
  --output-schema "$SCHEMA_PATH" \
  -o "$OUTPUT_PATH" \
  "Return JSON with status set to READY."
cat "$OUTPUT_PATH"

echo
echo "== search-enabled JSON event stream =="
"$CODEX_CMD" --search -a never exec --json --sandbox read-only --ephemeral \
  "Use web search. Find the title of the OpenAI Codex docs landing page and reply exactly as TITLE: <title>."

echo
echo "== MCP connectivity run =="
"$CODEX_CMD" -a never exec --sandbox read-only --ephemeral \
  -c 'mcp_servers.obsidian.command="uv"' \
  -c "mcp_servers.obsidian.args=[\"run\",\"obsidian-agent\",\"mcp\",\"--config\",\"$CONFIG_PATH\"]" \
  -c 'mcp_servers.obsidian.required=true' \
  "Call the get_vault_stats MCP tool and reply with NOTE_COUNT: <n> and nothing else."
