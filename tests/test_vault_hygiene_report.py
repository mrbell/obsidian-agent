from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from obsidian_agent.agent.worker import WorkerResult
from obsidian_agent.context import JobContext
from obsidian_agent.index.semantic_queries import get_stale_concepts
from obsidian_agent.index.store import IndexStore
from obsidian_agent.jobs.vault_hygiene_report import (
    run,
    _validate_output,
    _has_semantic_data,
    _ninety_days_before,
)
from obsidian_agent.outputs import Notification, VaultArtifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_OUTPUT = """\
# Vault Hygiene Report — 2026-03-09

## Implied tasks not formally captured
- **"Follow up with Alice about the proposal"** — from [[2026-02-14]]
  *(No matching open task found)*

## Threads that went quiet
- **distributed systems** — last seen October 2025. Several notes expressed intent
  to build a side project. No recent mention.
"""


def _make_ctx(
    tmp_path: Path,
    worker=None,
    also_notify: bool = True,
    with_semantic_data: bool = True,
):
    db = tmp_path / "index.duckdb"
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)

    from obsidian_agent.config import (
        Config, PathsConfig, CacheConfig, DeliveryConfig, JobsConfig,
        VaultHygieneReportConfig,
    )

    cfg = Config(
        paths=PathsConfig(
            vault=vault,
            outbox=tmp_path / "outbox",
            state_dir=tmp_path / "state",
            bot_inbox_rel="BotInbox",
        ),
        cache=CacheConfig(duckdb_path=db),
        delivery=DeliveryConfig(),
        agent=None,
        jobs=JobsConfig(
            vault_hygiene_report=VaultHygieneReportConfig(
                enabled=True,
                also_notify=also_notify,
            )
        ),
    )

    store = IndexStore(db)

    if with_semantic_data:
        store.conn.execute(
            "INSERT INTO note_intelligence (note_relpath, summary, extracted_at, model_version) "
            "VALUES ('test.md', 'A test note.', NOW(), 'test')"
        )

    return JobContext(
        store=store,
        config=cfg,
        today=date(2026, 3, 9),
        worker=worker,
    )


def _mock_worker(output: str = VALID_OUTPUT, returncode: int = 0) -> MagicMock:
    worker = MagicMock()
    worker.run.return_value = WorkerResult(
        returncode=returncode,
        output=output,
        stderr="",
    )
    return worker


# ---------------------------------------------------------------------------
# _ninety_days_before
# ---------------------------------------------------------------------------

class TestNinetyDaysBefore:
    def test_correct_offset(self):
        result = _ninety_days_before("2026-03-09")
        assert result == "2025-12-09"

    def test_returns_iso_string(self):
        result = _ninety_days_before("2026-01-01")
        assert result == "2025-10-03"


# ---------------------------------------------------------------------------
# _validate_output
# ---------------------------------------------------------------------------

class TestValidateOutput:
    def test_valid_output_passes(self):
        assert _validate_output(VALID_OUTPUT) is True

    def test_empty_fails(self):
        assert _validate_output("") is False

    def test_no_headings_fails(self):
        assert _validate_output("Plain text only.") is False


# ---------------------------------------------------------------------------
# _has_semantic_data
# ---------------------------------------------------------------------------

class TestHasSemanticData:
    def test_false_when_empty(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, with_semantic_data=False)
        assert _has_semantic_data(ctx) is False

    def test_true_with_note_intelligence(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, with_semantic_data=True)
        assert _has_semantic_data(ctx) is True

    def test_true_with_only_implicit_items(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, with_semantic_data=False)
        ctx.store.conn.execute(
            "INSERT INTO notes (note_relpath, title, is_daily_note, mtime_ns, "
            "size_bytes, content_sha256, word_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["daily.md", "daily", True, int(time.time() * 1e9), 100, "abc", 10],
        )
        ctx.store.conn.execute(
            "INSERT INTO chunks (id, note_relpath, chunk_index, text, token_count, "
            "embedded_sha256, embedded_at) VALUES (?, ?, ?, ?, ?, ?, NOW())",
            ["daily.md:0", "daily.md", 0, "some text", 5, "abc"],
        )
        ctx.store.conn.execute(
            "INSERT INTO implicit_items (id, chunk_id, note_relpath, type, text, extracted_at) "
            "VALUES (1, 'daily.md:0', 'daily.md', 'task', 'do something', NOW())"
        )
        assert _has_semantic_data(ctx) is True


# ---------------------------------------------------------------------------
# get_stale_concepts query helper
# ---------------------------------------------------------------------------

class TestGetStaleConcepts:
    def _setup_concept_in_old_note(self, store: IndexStore, mtime_ns: int) -> None:
        store.conn.execute(
            "INSERT INTO notes (note_relpath, title, is_daily_note, mtime_ns, "
            "size_bytes, content_sha256, word_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["old.md", "Old Note", False, mtime_ns, 100, "sha_old", 50],
        )
        store.conn.execute(
            "INSERT INTO chunks (id, note_relpath, chunk_index, text, token_count, "
            "embedded_sha256, embedded_at) VALUES (?, ?, ?, ?, ?, ?, NOW())",
            ["old.md:0", "old.md", 0, "content about distributed systems", 10, "sha_old"],
        )
        store.conn.execute(
            "INSERT INTO concepts (id, name) VALUES (1, 'distributed systems')"
        )
        store.conn.execute(
            "INSERT INTO chunk_concepts (chunk_id, concept_id, salience) VALUES (?, ?, ?)",
            ["old.md:0", 1, 0.9],
        )

    def test_returns_concept_older_than_cutoff(self, tmp_path: Path):
        store = IndexStore(tmp_path / "index.duckdb")
        # Note modified 6 months ago
        old_ns = int((time.time() - 180 * 86400) * 1e9)
        self._setup_concept_in_old_note(store, old_ns)

        # Cutoff is 30 days ago — concept is stale
        cutoff = date.fromtimestamp(time.time() - 30 * 86400).isoformat()
        results = get_stale_concepts(store.conn, inactive_before=cutoff)
        assert len(results) == 1
        assert results[0].name == "distributed systems"

    def test_excludes_concept_in_recent_note(self, tmp_path: Path):
        store = IndexStore(tmp_path / "index.duckdb")
        # Note modified yesterday — not stale
        recent_ns = int((time.time() - 86400) * 1e9)
        self._setup_concept_in_old_note(store, recent_ns)

        # Cutoff is 30 days ago — concept is NOT stale
        cutoff = date.fromtimestamp(time.time() - 30 * 86400).isoformat()
        results = get_stale_concepts(store.conn, inactive_before=cutoff)
        assert results == []

    def test_returns_last_seen_date(self, tmp_path: Path):
        store = IndexStore(tmp_path / "index.duckdb")
        old_ns = int((time.time() - 180 * 86400) * 1e9)
        self._setup_concept_in_old_note(store, old_ns)

        cutoff = date.fromtimestamp(time.time() - 30 * 86400).isoformat()
        results = get_stale_concepts(store.conn, inactive_before=cutoff)
        assert results[0].last_seen_date  # non-empty ISO date string
        # Verify it's a parseable date
        date.fromisoformat(results[0].last_seen_date)

    def test_empty_index_returns_empty(self, tmp_path: Path):
        store = IndexStore(tmp_path / "index.duckdb")
        results = get_stale_concepts(store.conn, inactive_before="2025-01-01")
        assert results == []


# ---------------------------------------------------------------------------
# Job: produces artifacts
# ---------------------------------------------------------------------------

class TestRunProducesArtifact:
    def test_produces_vault_artifact(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker())
        outputs = run(ctx)
        assert any(isinstance(o, VaultArtifact) for o in outputs)

    def test_artifact_filename_format(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker())
        outputs = run(ctx)
        artifact = next(o for o in outputs if isinstance(o, VaultArtifact))
        assert artifact.filename == "2026-03-09_vault-hygiene-report.md"

    def test_artifact_job_name(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker())
        outputs = run(ctx)
        artifact = next(o for o in outputs if isinstance(o, VaultArtifact))
        assert artifact.job_name == "vault_hygiene_report"

    def test_artifact_content_is_worker_output(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker())
        outputs = run(ctx)
        artifact = next(o for o in outputs if isinstance(o, VaultArtifact))
        assert artifact.content == VALID_OUTPUT

    def test_worker_called_with_web_search_false(self, tmp_path: Path):
        worker = _mock_worker()
        ctx = _make_ctx(tmp_path, worker=worker)
        run(ctx)
        _, kwargs = worker.run.call_args
        assert kwargs.get("web_search") is False


# ---------------------------------------------------------------------------
# Job: guards
# ---------------------------------------------------------------------------

class TestRunGuards:
    def test_no_worker_returns_empty(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=None)
        assert run(ctx) == []

    def test_no_semantic_data_returns_empty(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(), with_semantic_data=False)
        assert run(ctx) == []

    def test_worker_failure_returns_empty(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(returncode=1))
        assert run(ctx) == []

    def test_invalid_output_returns_empty(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(output="No headings here."))
        assert run(ctx) == []


# ---------------------------------------------------------------------------
# Job: notification
# ---------------------------------------------------------------------------

class TestRunNotification:
    def test_also_notify_produces_notification(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(), also_notify=True)
        outputs = run(ctx)
        assert any(isinstance(o, Notification) for o in outputs)

    def test_notification_subject_includes_date(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(), also_notify=True)
        outputs = run(ctx)
        notif = next(o for o in outputs if isinstance(o, Notification))
        assert "2026-03-09" in notif.subject

    def test_no_notification_when_also_notify_false(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(), also_notify=False)
        outputs = run(ctx)
        assert not any(isinstance(o, Notification) for o in outputs)
