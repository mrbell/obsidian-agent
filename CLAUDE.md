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
uv run obsidian-agent status         # show index and outbox status

uv run pytest                        # run all tests
uv run pytest tests/test_parser.py   # run a specific test file
```
