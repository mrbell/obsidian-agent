# Obsidian Agent

Scheduled automation framework that runs jobs over an Obsidian vault — delivering task
notifications, research digests, and eventually richer synthesis — while guaranteeing the
vault is never modified by automation.

**Read `DESIGN.md` before making any changes.**

---

## Critical Safety Rules

- Jobs **never** write to the vault directory. Ever.
- `promote/promoter.py` is the **only** component that writes into the vault, and only under `BotInbox/`.
- Claude Code **never** receives the vault filesystem path — it accesses vault content through the MCP server only.
- The MCP server exposes **no write tools**.

---

## Stack and Conventions

- Python 3.12+, managed with `uv`
- Typed throughout — dataclasses and type hints everywhere
- CLI via Typer (`obsidian_agent/cli.py`) — no business logic in `cli.py`
- Tests in `tests/`, run with `pytest`
- Config loaded from `config/config.yaml`; secrets via environment variables only

---

## Package Structure

```
obsidian_agent/
    cli.py            # CLI entrypoint — dispatch only
    config.py         # config loading and validation
    context.py        # JobContext dataclass
    logging_utils.py  # logging setup
    outputs.py        # VaultArtifact, Notification dataclasses

    vault/            # reads vault files; no writes
    index/            # DuckDB schema, build, queries
    mcp/              # MCP server exposing vault to Claude Code
    agent/            # headless Claude Code worker
    jobs/             # job implementations
    promote/          # vault inbox promotion (only write path into vault)
    delivery/         # email and notification delivery
```

Full layout and dependency rules: `DESIGN.md §15–16`.

---

## Dependency Direction

`promote`, `delivery`, and `agent` do not depend on each other.
`vault` knows nothing about the index. `mcp` depends on vault and index, not on jobs.
Jobs may not depend on `cli` or `promote`.

---

## Issue Tracking

Issues live in `docs/issues/`. One file per issue.

- Parent issues: `N_title.md` (e.g. `1_foundation.md`)
- Child issues: `N-M_title.md` (e.g. `1-1_config.md`)
- Child issues reference their parent; parent issues list their children
- Update the **Status** field when starting or completing work
- Valid statuses: `open`, `in_progress`, `completed`, `blocked`

---

## Common Commands

```bash
uv run obsidian-agent index          # rebuild vault index
uv run obsidian-agent run <job>      # run a named job
uv run obsidian-agent promote        # promote outbox artifacts to vault
uv run obsidian-agent mcp            # start MCP server
uv run obsidian-agent agent test     # verify Claude Code is available
uv run obsidian-agent agent test --mcp  # also verify MCP vault connectivity
uv run obsidian-agent status         # show index and outbox status

uv run pytest                        # run all tests
uv run pytest tests/test_parser.py   # run a specific test file
```

---

## Log Locations

All logs are under `~/.local/share/obsidian-agent/`:

```
logs/obsidian-agent.log      # main rotating log (all commands)
research_digest.log          # research_digest job runs
task_notification.log        # task_notification job runs
vault_connections_report.log # vault_connections_report job runs
vault_hygiene_report.log     # vault_hygiene_report job runs
index.log                    # structural index runs
index-semantic.log           # semantic index runs
vault-backup.log             # nightly vault backup script
```

The main log (`logs/obsidian-agent.log`) is the best starting point for diagnosing failures — it captures all job runs with timestamps, errors, and worker output previews.

---

## DuckDB Concurrency

Only `index` and `index-semantic` open the DB in **write mode**. All other commands (`run`, `status`, MCP server) open it **read-only** (`IndexStore(path, read_only=True)`). This allows multiple concurrent readers (e.g. a job and its MCP server subprocess) without lock conflicts.

---

## MCP Tool Permissions

When adding a new tool to `mcp/server.py`, also add it to `_MCP_TOOLS` in `agent/worker.py`. This list is used to build the `--allowedTools` flag for headless Claude Code workers. If a tool is missing from the list, the worker cannot call it (permission denied in headless mode, with no error — the model just says the tool is unavailable).
