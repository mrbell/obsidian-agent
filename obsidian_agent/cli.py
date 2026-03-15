from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console

from obsidian_agent.config import ConfigError, load_config
from obsidian_agent.index.build_index import build_index
from obsidian_agent.index.store import IndexStore
from obsidian_agent.logging_utils import setup_logging
import obsidian_agent.jobs  # noqa: F401 — triggers job self-registration

app = typer.Typer(add_completion=False)
console = Console()

_DEFAULT_CONFIG = Path("~/.config/obsidian-agent/config.yaml")
_CONFIG_ENV_VAR = "OBSIDIAN_AGENT_CONFIG"


def _resolve_config_path(config_path: Path) -> Path:
    """Return config path from CLI arg, env var fallback, or default."""
    if str(config_path) != str(_DEFAULT_CONFIG):
        # Explicitly provided via --config flag
        return config_path.expanduser().resolve()
    env_val = os.environ.get(_CONFIG_ENV_VAR)
    if env_val:
        return Path(env_val).expanduser().resolve()
    return config_path.expanduser().resolve()


def _load(config_path: Path, verbose: bool):
    """Expand path, load config, set up logging. Exits on error."""
    config_path = _resolve_config_path(config_path)
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
        stats = build_index(cfg.paths.vault, store, cfg.indexing.exclude_paths)

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
# index-semantic
# ---------------------------------------------------------------------------

@app.command("index-semantic")
def index_semantic(
    config: Path = typer.Option(
        _DEFAULT_CONFIG, "--config", "-c", help="Path to config.yaml"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Update the semantic index (embeddings + concept extraction) for changed notes."""
    import logging

    from obsidian_agent.embeddings.local import LocalEmbedder
    from obsidian_agent.index.semantic import run_semantic_index

    cfg = _load(config, verbose)
    log = logging.getLogger(__name__)

    if not cfg.cache.duckdb_path.exists():
        console.print(
            "[yellow]Index not found. Run [bold]obsidian-agent index[/bold] first.[/yellow]"
        )
        raise typer.Exit(1)

    log.info("Starting semantic index. vault=%s", cfg.paths.vault)

    embedder = LocalEmbedder(model_name=cfg.semantic.model)

    worker = None
    if cfg.agent:
        from obsidian_agent.agent.claude import ClaudeBackendAdapter
        worker = ClaudeBackendAdapter(
            cfg=cfg.agent,
            vault_path=cfg.paths.vault,
            db_path=cfg.cache.duckdb_path,
            config_path=_resolve_config_path(config),
        )

    with IndexStore(cfg.cache.duckdb_path) as store:
        emb_stats, intel_stats = run_semantic_index(
            cfg.paths.vault,
            store,
            embedder,
            worker=worker,
            max_notes_per_run=cfg.semantic.max_notes_per_run,
        )

    log.info(
        "Semantic index complete. embedding: processed=%d skipped=%d chunks=%d",
        emb_stats.notes_processed, emb_stats.notes_skipped, emb_stats.chunks_embedded,
    )
    if intel_stats is not None:
        log.info(
            "Intelligence phase: processed=%d skipped=%d failed=%d",
            intel_stats.notes_processed, intel_stats.notes_skipped, intel_stats.notes_failed,
        )

    console.print(
        f"[bold]Semantic index complete[/bold]  "
        f"embedded [cyan]{emb_stats.notes_processed}[/cyan]  "
        f"chunks [green]{emb_stats.chunks_embedded}[/green]"
    )
    if intel_stats is not None:
        console.print(
            f"  intelligence: processed [cyan]{intel_stats.notes_processed}[/cyan]  "
            f"failed [red]{intel_stats.notes_failed}[/red]"
        )
    elif cfg.agent is None:
        console.print("  [dim]Intelligence phase skipped (no agent configured)[/dim]")


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


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# promote
# ---------------------------------------------------------------------------

@app.command()
def promote(
    config: Path = typer.Option(
        _DEFAULT_CONFIG, "--config", "-c", help="Path to config.yaml"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be promoted without copying"),
) -> None:
    """Promote outbox artifacts into the vault BotInbox."""
    import logging
    from obsidian_agent.promote.promoter import promote as run_promote

    cfg = _load(config, verbose)
    log = logging.getLogger(__name__)

    if dry_run:
        console.print("[yellow][dry-run][/yellow] No files will be copied.")

    result = run_promote(
        cfg.paths.outbox,
        cfg.paths.vault,
        cfg.paths.bot_inbox_rel,
        dry_run=dry_run,
    )

    prefix = "[yellow][dry-run][/yellow] " if dry_run else ""
    console.print(
        f"{prefix}[bold]Promote complete[/bold]  "
        f"promoted [green]{result.promoted}[/green]  "
        f"skipped [yellow]{result.skipped}[/yellow]  "
        f"errors [red]{result.errors}[/red]"
    )

    log.info(
        "Promote complete. promoted=%d skipped=%d errors=%d dry_run=%s",
        result.promoted, result.skipped, result.errors, dry_run,
    )

    if result.errors:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# cron (sub-app)
# ---------------------------------------------------------------------------

cron_app = typer.Typer(help="Manage cron entries for scheduled jobs.")
app.add_typer(cron_app, name="cron")


@cron_app.command("show")
def cron_show(
    config: Path = typer.Option(
        _DEFAULT_CONFIG, "--config", "-c", help="Path to config.yaml"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Preview the cron entries that would be installed, without making changes."""
    from obsidian_agent.cron import build_managed_section, find_binary

    cfg = _load(config, verbose)
    config_path = _resolve_config_path(config)
    try:
        binary = find_binary()
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(1)

    section = build_managed_section(cfg, config_path, binary)
    console.print(section)


@cron_app.command("install")
def cron_install(
    config: Path = typer.Option(
        _DEFAULT_CONFIG, "--config", "-c", help="Path to config.yaml"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Install cron entries for all enabled jobs (replaces any existing managed entries)."""
    from obsidian_agent.cron import find_binary, install

    cfg = _load(config, verbose)
    config_path = _resolve_config_path(config)
    try:
        binary = find_binary()
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(1)

    new_crontab = install(cfg, config_path, binary)
    console.print("[bold green]Cron entries installed.[/bold green]")
    console.print("\n[dim]Installed entries:[/dim]")
    console.print(new_crontab)


@cron_app.command("uninstall")
def cron_uninstall(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Remove all obsidian-agent managed cron entries."""
    from obsidian_agent.cron import uninstall

    uninstall()
    console.print("[bold green]Cron entries removed.[/bold green]")


# ---------------------------------------------------------------------------
# agent (sub-app)
# ---------------------------------------------------------------------------

agent_app = typer.Typer(help="Commands for the Claude Code agent worker.")
app.add_typer(agent_app, name="agent")


@agent_app.command("test")
def agent_test(
    config: Path = typer.Option(
        _DEFAULT_CONFIG, "--config", "-c", help="Path to config.yaml"
    ),
    mcp: bool = typer.Option(False, "--mcp", help="Also verify MCP vault connectivity"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Verify Claude Code is installed and able to produce output.

    With --mcp, also verifies the worker can connect to the vault MCP server
    and call a vault tool successfully.
    """
    from obsidian_agent.agent.claude import ClaudeBackendAdapter

    cfg = _load(config, verbose)

    if not cfg.agent:
        console.print(
            "[bold red]Error:[/bold red] No 'agent' section in config.yaml. "
            "Add agent.command to use LLM-assisted jobs."
        )
        raise typer.Exit(1)

    worker = ClaudeBackendAdapter(
        cfg=cfg.agent,
        vault_path=cfg.paths.vault,
        db_path=cfg.cache.duckdb_path,
        config_path=_resolve_config_path(config),
    )

    console.print("Running agent smoke test (no MCP)...")
    result = worker.run(
        "Say the word READY and nothing else.",
        web_search=False,
        with_mcp=False,
    )

    if result.returncode == 0 and result.output.strip():
        console.print(f"[bold green]PASS[/bold green]  output: {result.output.strip()!r}")
    else:
        console.print(
            f"[bold red]FAIL[/bold red]  "
            f"exit={result.returncode}  "
            f"output={result.output.strip()!r}  "
            f"stderr={result.stderr[:200]!r}"
        )
        raise typer.Exit(1)

    if mcp:
        console.print("Running MCP connectivity test...")
        result = worker.run(
            "Call the get_vault_stats MCP tool and report the total note count "
            "as a single line: 'NOTE_COUNT: <n>'. Nothing else.",
            web_search=False,
            with_mcp=True,
        )
        if result.returncode == 0 and "NOTE_COUNT:" in result.output:
            console.print(f"[bold green]PASS[/bold green]  MCP reachable. {result.output.strip()!r}")
        else:
            console.print(
                f"[bold red]FAIL[/bold red]  MCP test failed.  "
                f"exit={result.returncode}  "
                f"output={result.output.strip()!r}  "
                f"stderr={result.stderr[:300]!r}"
            )
            raise typer.Exit(1)


# ---------------------------------------------------------------------------
# mcp
# ---------------------------------------------------------------------------

@app.command()
def mcp(
    config: Path = typer.Option(
        _DEFAULT_CONFIG, "--config", "-c", help="Path to config.yaml"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Start the MCP server on stdio (used by Claude Code worker and Claude Desktop)."""
    from obsidian_agent.mcp.server import run_server

    cfg = _load(config, verbose)
    run_server(cfg.paths.vault, cfg.cache.duckdb_path, semantic_model=cfg.semantic.model)


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@app.command()
def run(
    job_name: str = typer.Argument(..., help="Name of the job to run"),
    config: Path = typer.Option(
        _DEFAULT_CONFIG, "--config", "-c", help="Path to config.yaml"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Run a named job."""
    import logging
    from datetime import date

    from obsidian_agent.agent.claude import ClaudeBackendAdapter
    from obsidian_agent.context import JobContext
    from obsidian_agent.delivery.base import DeliveryError
    from obsidian_agent.delivery.smtp import SmtpDelivery
    from obsidian_agent.jobs.registry import get_job
    from obsidian_agent.outputs import Notification, VaultArtifact

    cfg = _load(config, verbose)
    log = logging.getLogger(__name__)

    try:
        job_fn = get_job(job_name)
    except KeyError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(1)

    delivery = None
    if cfg.delivery.email:
        try:
            delivery = SmtpDelivery(cfg.delivery.email)
        except DeliveryError as exc:
            console.print(f"[bold red]Delivery config error:[/bold red] {exc}")
            raise typer.Exit(1)

    worker = None
    if cfg.agent:
        worker = ClaudeBackendAdapter(
            cfg=cfg.agent,
            vault_path=cfg.paths.vault,
            db_path=cfg.cache.duckdb_path,
            config_path=_resolve_config_path(config),
        )

    cfg.paths.state_dir.mkdir(parents=True, exist_ok=True)
    cfg.paths.outbox.mkdir(parents=True, exist_ok=True)

    with IndexStore(cfg.cache.duckdb_path, read_only=True) as store:
        ctx = JobContext(
            store=store,
            config=cfg,
            today=date.today(),
            delivery=delivery,
            worker=worker,
            logger=log,
        )

        log.info("Running job: %s", job_name)
        outputs = job_fn(ctx)
        log.info("Job %s produced %d output(s)", job_name, len(outputs))

    for output in outputs:
        if isinstance(output, VaultArtifact):
            dest = output.write_to_outbox(cfg.paths.outbox)
            log.info("Artifact written: %s", dest)
            console.print(f"Artifact: [cyan]{dest}[/cyan]")
        elif isinstance(output, Notification):
            if delivery is None:
                log.warning("No delivery configured; skipping: %s", output.subject)
                console.print(
                    f"[yellow]No delivery configured — skipping:[/yellow] {output.subject}"
                )
            else:
                delivery.send(output.subject, output.body)
                log.info("Notification sent: %s", output.subject)
                console.print(f"Sent: [green]{output.subject}[/green]")

    console.print(f"[bold]Done:[/bold] {job_name}  {len(outputs)} output(s)")
