from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from obsidian_agent.config import ConfigError, load_config
from obsidian_agent.index.build_index import build_index
from obsidian_agent.index.store import IndexStore
from obsidian_agent.logging_utils import setup_logging

app = typer.Typer(add_completion=False)
console = Console()

_DEFAULT_CONFIG = Path("~/.config/obsidian-agent/config.yaml")


def _load(config_path: Path, verbose: bool):
    """Expand path, load config, set up logging. Exits on error."""
    config_path = config_path.expanduser().resolve()
    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        console.print(f"[bold red]Config error:[/bold red] {exc}")
        raise typer.Exit(1)
    setup_logging(cfg.paths.state_dir, verbose=verbose)
    return cfg


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------

@app.command()
def index(
    config: Path = typer.Option(
        _DEFAULT_CONFIG, "--config", "-c", help="Path to config.yaml"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Scan the vault and update the DuckDB index."""
    import logging
    cfg = _load(config, verbose)
    log = logging.getLogger(__name__)

    log.info("Starting index build. vault=%s", cfg.paths.vault)
    cfg.paths.state_dir.mkdir(parents=True, exist_ok=True)

    with IndexStore(cfg.cache.duckdb_path) as store:
        stats = build_index(cfg.paths.vault, store)

    log.info(
        "Index complete. scanned=%d added=%d updated=%d renamed=%d deleted=%d unchanged=%d",
        stats.scanned, stats.added, stats.updated,
        stats.renamed, stats.deleted, stats.unchanged,
    )
    console.print(
        f"[bold]Index complete[/bold]  "
        f"scanned [cyan]{stats.scanned}[/cyan]  "
        f"added [green]{stats.added}[/green]  "
        f"updated [yellow]{stats.updated}[/yellow]  "
        f"renamed [blue]{stats.renamed}[/blue]  "
        f"deleted [red]{stats.deleted}[/red]  "
        f"unchanged {stats.unchanged}"
    )


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@app.command()
def status(
    config: Path = typer.Option(
        _DEFAULT_CONFIG, "--config", "-c", help="Path to config.yaml"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Show current index and outbox status."""
    import logging
    cfg = _load(config, verbose)
    log = logging.getLogger(__name__)

    db = cfg.cache.duckdb_path
    if not db.exists():
        console.print("[yellow]Index not found. Run [bold]obsidian-agent index[/bold] first.[/yellow]")
        raise typer.Exit(1)

    with IndexStore(db) as store:
        conn = store.conn

        last_indexed = conn.execute(
            "SELECT value FROM meta WHERE key = 'last_indexed_at'"
        ).fetchone()
        last_indexed_str = last_indexed[0] if last_indexed else "never"

        note_count = conn.execute("SELECT count(*) FROM notes").fetchone()[0]
        daily_count = conn.execute(
            "SELECT count(*) FROM notes WHERE is_daily_note = TRUE"
        ).fetchone()[0]

        open_tasks = conn.execute(
            "SELECT count(*) FROM tasks WHERE status = 'open'"
        ).fetchone()[0]
        tasks_with_due = conn.execute(
            "SELECT count(*) FROM tasks WHERE status = 'open' AND due_date IS NOT NULL"
        ).fetchone()[0]

        # Broken wikilinks: targets that don't match any known note stem
        wikilink_targets = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT target FROM links WHERE kind = 'wikilink'"
            ).fetchall()
        }
        note_stems: set[str] = set()
        for (relpath,) in conn.execute("SELECT note_relpath FROM notes").fetchall():
            # "folder/My Note.md" -> "My Note" and "folder/My Note"
            filename = relpath.rsplit("/", 1)[-1]
            if filename.endswith(".md"):
                note_stems.add(filename[:-3])
            if relpath.endswith(".md"):
                note_stems.add(relpath[:-3])
        broken_count = len(wikilink_targets - note_stems)

    # Pending outbox artifacts
    outbox = cfg.paths.outbox
    pending = len(list(outbox.glob("**/*.md"))) if outbox.exists() else 0

    log.info("Status displayed.")

    console.print()
    console.print("[bold]Index[/bold]")
    console.print(f"  Last indexed:      {last_indexed_str}")
    console.print(f"  Notes:             {note_count}  ({daily_count} daily)")
    console.print(f"  Open tasks:        {open_tasks}  ({tasks_with_due} with due dates)")
    if broken_count:
        console.print(f"  Broken wikilinks:  [yellow]{broken_count}[/yellow]")
    else:
        console.print(f"  Broken wikilinks:  {broken_count}")
    console.print()
    console.print("[bold]Outbox[/bold]")
    if pending:
        console.print(f"  Pending artifacts: [green]{pending}[/green]")
    else:
        console.print(f"  Pending artifacts: {pending}")
    console.print()
