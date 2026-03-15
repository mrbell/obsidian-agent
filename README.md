# Obsidian Agent

A scheduled automation framework for [Obsidian](https://obsidian.md) vaults. Runs jobs on a schedule to deliver notifications, surface forgotten ideas, and generate research digests — without ever modifying your notes.

## What it does

**Task notifications** — Each morning, get an email listing tasks with upcoming or overdue due dates pulled from your vault.

**Research digests** — Weekly, Claude searches the web and consults your existing notes to produce a markdown report on topics you care about (e.g. "agentic coding", "personal knowledge management"), deposited directly into your vault.

**Vault connections** — Weekly, surface old notes and ideas that connect to what you've been writing about recently. Corrects the recency bias that causes good ideas to be forgotten.

**Vault hygiene** — Periodically, get a report of suggestions: implied tasks you never formalized, ideas scattered across daily notes that might deserve their own note, and semantically related notes that aren't linked to each other. Suggestions only — nothing is changed automatically.

**Readwise ingestion** — Pull Readwise article and tweet highlights into permanent notes in a `Readwise/` folder in your vault.

Your existing notes are never modified, moved, or deleted. All outputs are either emails or new notes placed in a `BotInbox/` folder inside your vault.

## How it works

Obsidian Agent maintains two indexes of your vault:

- A **structural index** (DuckDB) — notes, tasks, tags, links, headings. Fast to build, updated before each job run.
- A **semantic index** — paragraph-level embeddings and LLM-extracted concepts, entities, and implicit ideas. Built incrementally on a nightly schedule.

Jobs query these indexes and optionally invoke a configured agent backend to produce outputs. A local MCP server gives the agent read-only access to your vault — it never touches the filesystem directly.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- An Obsidian vault
- A supported agent backend for LLM-assisted jobs:
  - [Claude Code](https://claude.ai/code)
  - [Codex CLI](https://developers.openai.com/codex/)
- A Gmail or Fastmail account (for email delivery)

## Setup

**1. Install**

```bash
git clone https://github.com/yourusername/obsidian-agent
cd obsidian-agent
uv sync
```

**2. Configure**

```bash
mkdir -p ~/.config/obsidian-agent
cp config/config.yaml.example ~/.config/obsidian-agent/config.yaml
```

Edit the config to set your vault path, SMTP settings, agent backend, and job preferences. See `config/config.yaml.example` for all available options.

**3. Set your email password**

Add to `~/.bashrc` or equivalent — never put passwords in the config file:

```bash
export OBSIDIAN_AGENT_SMTP_PASSWORD="your-app-password"
```

For Gmail: enable 2FA, then generate an app password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).

**4. Build the structural index**

```bash
uv run obsidian-agent index
uv run obsidian-agent status   # verify the note count looks right
```

**5. Build the semantic index**

The semantic index involves local embeddings and one LLM call per note. On a large vault, use `max_notes_per_run` in your config to throttle the initial build and run it in batches over a few nights:

```yaml
semantic:
  max_notes_per_run: 50
```

Then run:

```bash
uv run obsidian-agent index-semantic
```

Repeat nightly (or via cron — see below) until caught up. Remove `max_notes_per_run` once the initial build is complete.

**6. Test a job**

```bash
uv run obsidian-agent run task_notification
```

**7. Schedule with cron**

```bash
uv run obsidian-agent cron install
```

This reads your config and installs cron entries for all enabled jobs, including nightly index runs. Preview what will be installed first with `cron show`.

## Commands

```
obsidian-agent index              # rebuild structural index
obsidian-agent index-semantic     # update semantic index (nightly)
obsidian-agent run <job>          # run a job by name
obsidian-agent promote            # copy outbox artifacts into vault BotInbox
obsidian-agent status             # show index stats and pending outbox items
obsidian-agent cron show          # preview cron entries for enabled jobs
obsidian-agent cron install       # install cron entries
obsidian-agent cron uninstall     # remove cron entries
obsidian-agent agent test         # verify the configured agent backend is reachable
obsidian-agent mcp                # start the MCP server (also usable in Claude Desktop)
```

## Agent backends

The job layer is backend-neutral. Configure the `agent` section in `config.yaml` to select a backend:

```yaml
agent:
  backend: claude
  command: claude
  args: ["--print", "--output-format", "json", "--no-session-persistence"]
  timeout_seconds: 300
  work_dir: ~/.local/share/obsidian-agent/agent_workdir
```

Codex is also supported:

```yaml
agent:
  backend: codex
  command: codex
  args: ["exec", "--sandbox", "read-only", "--ephemeral"]
  timeout_seconds: 300
  work_dir: ~/.local/share/obsidian-agent/agent_workdir
```

Compatibility matrix:

| Backend | Non-interactive runs | MCP vault access | Web search | Structured output | Status |
|---|---|---|---|---|---|
| `claude` | Yes | Yes | Yes | Yes | Reference implementation |
| `codex` | Yes | Yes | Yes | Yes | Supported |

Notes:
- Claude uses per-run `--mcp-config` and tool allowlists.
- Codex uses per-run `-c mcp_servers...` overrides and `--search`.
- `obsidian-agent agent test --mcp` works for both backends.

## Available jobs

| Job | Schedule | Output |
|---|---|---|
| `task_notification` | Daily | Email with upcoming and overdue tasks |
| `research_digest` | Weekly | Vault note per configured topic |
| `vault_connections_report` | Weekly | Vault note surfacing old ideas related to recent activity |
| `vault_hygiene_report` | Bi-weekly | Vault note with suggestions for implied tasks, missing links, orphaned threads |
| `readwise_ingestion` | Daily | Permanent vault note per new Readwise article or tweet |

For `readwise_ingestion`, set `READWISE_API_TOKEN` in your environment. Promoted notes go to `Readwise/` rather than `BotInbox/`.

## Using the MCP server interactively

The MCP server runs automatically during job execution — you don't need to manage it. But you can also register it with Claude Code, Codex, or Claude Desktop to query your vault interactively in conversation.

**Claude Code — this project only**

A `.mcp.json` is already included at the project root. Update the `--directory` path if you
cloned the repo elsewhere:

```json
{
  "mcpServers": {
    "obsidian-vault": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "/path/to/obsidian-agent", "run", "obsidian-agent", "mcp"]
    }
  }
}
```

Claude Code will prompt you to approve the server the first time you open the project.

**Claude Code — all projects (global)**

Run:

```bash
claude mcp add obsidian-vault --scope user -- uv --directory /path/to/obsidian-agent run obsidian-agent mcp
```

**Claude Desktop**

Add the same block under `mcpServers` in Claude Desktop's settings file (Settings → Developer → Edit Config).

Once registered, you can ask Claude things like "what tasks do I have due this week", "find notes related to X", or "what ideas have I been writing about recently" and it will query your live vault index directly.

**Codex CLI**

Codex can register the MCP server globally:

```bash
codex mcp add obsidian-vault -- uv --directory /path/to/obsidian-agent run obsidian-agent mcp
```

For scheduled Obsidian Agent runs, the Codex backend injects MCP configuration per run, so global registration is optional.

## Safety

- Jobs have no write access to your vault
- The only component that writes into the vault is `promote`, and it only creates new files under `BotInbox/`
- The MCP server exposes read-only tools — no write operations are possible through it
- No existing note is ever modified or deleted
