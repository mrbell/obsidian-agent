# 1-6 — CLI: index and status Commands

**Status**: `open`
**Parent**: 1
**Children**: —
**Depends on**: 1-1, 1-2, 1-5

## Description

Implement `obsidian_agent/cli.py` with the `index` and `status` commands using Typer.

## Implementation Notes

### CLI structure

```python
app = typer.Typer()

@app.command()
def index(config: Path = ..., verbose: bool = False): ...

@app.command()
def status(config: Path = ..., verbose: bool = False): ...
```

Global options (`--config`, `--verbose`) apply to all commands.

### `index` command

1. Load config
2. Setup logging
3. Open `IndexStore`
4. Call `build_index(vault_path, store)`
5. Log and print `IndexStats` summary

### `status` command

Print a summary of the current index:
- Last indexed timestamp (if recorded)
- Note count, daily note count
- Open task count, tasks with due dates
- Pending outbox artifact count
- Any notes with broken links (targets not in index)

Store a `last_indexed_at` timestamp in a simple state file or a `meta` table in DuckDB.

### No business logic in cli.py

`cli.py` loads config, sets up logging, instantiates objects, calls functions, prints results.
That is all.

## Testing & Validation

- `obsidian-agent index` runs without error against a temp vault
- `obsidian-agent status` prints accurate counts

## Definition of Done

Both commands work end-to-end. `index` followed by `status` shows accurate vault stats.
