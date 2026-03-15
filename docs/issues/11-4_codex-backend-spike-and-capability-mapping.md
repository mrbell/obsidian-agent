# 11-4 — Codex Backend Spike and Capability Mapping

**Status**: `completed`
**Parent**: 11
**Children**: —
**Depends on**: 11-1

## Description

Run a focused spike on the Codex CLI to determine how closely it can match the required
agent capabilities for this project and where adapter design needs to compensate for
behavioral differences.

This issue should reduce uncertainty before committing to a full Codex adapter.

## Questions to Answer

- How should non-interactive Codex runs be invoked for this project?
- What is the most reliable machine-readable output format for final model output?
- How should MCP servers be registered or supplied for an isolated run?
- Is per-run MCP configuration possible, or must Codex rely on pre-registered/global MCP state?
- How should web search be enabled/disabled in a backend-neutral way?
- What sandbox/approval settings are appropriate for scheduled local runs?

## Deliverables

- A concrete capability matrix: Claude vs Codex
- A recommended invocation pattern for Codex
- A list of functionality that is:
  - fully supported
  - supported with adaptation
  - unsupported or risky

## Testing & Validation

Prefer executable spike notes and small verification scripts/tests over prose-only conclusions.

If possible, validate:

- simple prompt execution
- MCP connectivity to `obsidian-agent mcp`
- search-enabled run shape
- structured output extraction path

## Definition of Done

- The project has a clear go/no-go decision for Codex support
- Backend adapter implementation can proceed with known constraints rather than guesses

## Spike Findings

### Go/No-Go

**Decision**: `go`

Codex is viable for this project's backend abstraction. The current CLI supports the
required non-interactive execution model, machine-readable final output, MCP-based vault
access, and web search. The main differences from Claude are configuration shape and
security controls, not missing core capability.

### Verified Commands

An executable smoke script for the verified command patterns lives at:

- `scripts/codex_spike_11_4.sh`

Live verification against the current Codex CLI (`v0.108.0-alpha.12`) confirmed:

1. Simple non-interactive run works:

```bash
codex -a never exec --sandbox read-only --ephemeral \
  "Say READY and nothing else."
```

2. Structured output works reliably with a JSON Schema plus `-o`:

```bash
codex -a never exec --sandbox read-only --ephemeral \
  --output-schema /tmp/schema.json \
  -o /tmp/output.json \
  "Return JSON with status set to READY."
```

3. MCP can be injected per run via config overrides; a dedicated `--mcp-config` flag is not
   required:

```bash
codex -a never exec --sandbox read-only --ephemeral \
  -c 'mcp_servers.obsidian.command="uv"' \
  -c 'mcp_servers.obsidian.args=["run","obsidian-agent","mcp","--config","/path/to/config.yaml"]' \
  -c 'mcp_servers.obsidian.required=true' \
  "Call the get_vault_stats MCP tool and reply with NOTE_COUNT: <n> and nothing else."
```

This was validated against the real `obsidian-agent mcp` server; Codex successfully called
`get_vault_stats` and returned `NOTE_COUNT: 1`.

4. Search-enabled runs work with the top-level `--search` flag:

```bash
codex --search -a never exec --json --sandbox read-only --ephemeral \
  "Use web search. Find the title of the OpenAI Codex docs landing page and reply exactly as TITLE: <title>."
```

The JSON event stream included a `web_search` item and a final response.

### Capability Matrix

| Capability | Claude | Codex | Notes |
|---|---|---|---|
| Non-interactive execution | Yes | Yes | Claude uses `claude -p`; Codex uses `codex exec` |
| MCP vault access | Yes | Yes | Codex uses per-run `-c mcp_servers...` overrides or config state |
| Web search | Yes | Yes | Claude uses tool allowlisting; Codex uses top-level `--search` |
| Structured output | Yes | Yes | Codex is best with `--output-schema` + `-o` |
| Fail fast on broken MCP | Yes | Yes | Codex supports `mcp_servers.<name>.required=true` |
| Per-run MCP config | Yes | Yes, with adaptation | No dedicated `--mcp-config`, but `-c` overrides work |

### Recommended Invocation Pattern

For the Codex adapter:

```bash
codex -a never exec --sandbox read-only --ephemeral \
  [--search] \
  [--output-schema /tmp/schema.json] \
  [-o /tmp/output.json] \
  -c 'mcp_servers.obsidian.command="uv"' \
  -c 'mcp_servers.obsidian.args=["run","obsidian-agent","mcp","--config","/path/to/config.yaml"]' \
  -c 'mcp_servers.obsidian.required=true' \
  -- "<prompt>"
```

Adapter recommendations:

- Use `codex exec`, not the interactive default entrypoint
- Pass approval policy as the top-level `-a never`
- Default to `--sandbox read-only` for this project
- Add `--search` only when `web_search=True`
- For structured-output paths, prefer `--output-schema` plus `-o` over parsing the event stream
- Inject the vault MCP server per run with `-c mcp_servers...` overrides instead of mutating
  ambient user config
- Mark the MCP server as required when `with_mcp=True` so scheduled runs fail fast

### Fully Supported

- Simple non-interactive prompt execution
- Search-enabled runs
- Structured final output with schema validation
- MCP-backed access to `obsidian-agent mcp`
- Fail-fast startup when a required MCP server cannot initialize

### Supported With Adaptation

- Per-run MCP setup: supported via `-c` overrides rather than a dedicated `--mcp-config`
- Final output parsing: use output files/schema rather than scraping the `--json` event stream
- Backend security parity: Codex uses sandbox and approval settings instead of Claude-style
  built-in tool allowlists

### Unsupported or Risky

- Exact Claude-style per-run built-in tool allowlisting was not verified for Codex
- A documented Codex equivalent of a project-managed `CODEX_HOME` or alternate state dir was
  not confirmed during this spike
- Even with `--ephemeral`, Codex still touched `~/.codex` for state/auth in live runs

### Implications for 11-5

- `agent.command` for Codex should likely be `codex`
- The Codex adapter should build command-line `-c` overrides for MCP instead of writing a
  separate MCP config file
- `with_mcp=False` should omit the `mcp_servers` overrides entirely
- `web_search=True` should map to top-level `--search`
- The adapter should use a schema file plus `-o` for deterministic structured extraction paths
- The adapter should document that auth/state may still depend on the user's Codex installation,
  even when MCP registration does not
