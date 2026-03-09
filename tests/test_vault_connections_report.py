from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from obsidian_agent.agent.worker import WorkerResult
from obsidian_agent.context import JobContext
from obsidian_agent.index.store import IndexStore
from obsidian_agent.jobs.vault_connections_report import (
    run,
    _validate_output,
    _has_semantic_data,
)
from obsidian_agent.outputs import Notification, VaultArtifact


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

VALID_OUTPUT = """\
# Vault Connections — 2026-03-09

## What you've been thinking about (last 14 days)
You have been thinking about note-taking systems and knowledge management lately.

## Connections worth revisiting

### Reflections on Information Overload
**Note**: Archive/2025-08-12.md  **Last touched**: 2025-08-12
This note connects to your recent thinking on knowledge management by exploring
how to filter signal from noise — a recurring theme in your recent daily notes.

## Implicit items that connect to your recent thinking
- From Archive/2025-07-01.md: "Idea to build a weekly review template"
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
        VaultConnectionsReportConfig,
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
            vault_connections_report=VaultConnectionsReportConfig(
                enabled=True,
                lookback_recent_days=14,
                lookback_old_days=30,
                max_connections=5,
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
# _validate_output
# ---------------------------------------------------------------------------

class TestValidateOutput:
    def test_valid_output_passes(self):
        assert _validate_output(VALID_OUTPUT) is True

    def test_empty_string_fails(self):
        assert _validate_output("") is False

    def test_whitespace_only_fails(self):
        assert _validate_output("   \n\n") is False

    def test_no_headings_fails(self):
        assert _validate_output("Some text without any headings.") is False

    def test_has_heading_passes(self):
        assert _validate_output("# Title\n\n## Section\nContent.") is True


# ---------------------------------------------------------------------------
# _has_semantic_data
# ---------------------------------------------------------------------------

class TestHasSemanticData:
    def test_returns_false_when_empty(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, with_semantic_data=False)
        assert _has_semantic_data(ctx) is False

    def test_returns_true_when_data_present(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, with_semantic_data=True)
        assert _has_semantic_data(ctx) is True


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
        assert artifact.filename == "2026-03-09_vault-connections-report.md"

    def test_artifact_job_name(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker())
        outputs = run(ctx)
        artifact = next(o for o in outputs if isinstance(o, VaultArtifact))
        assert artifact.job_name == "vault_connections_report"

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
# Job: invalid / failed output is rejected
# ---------------------------------------------------------------------------

class TestRunRejectsInvalidOutput:
    def test_empty_output_returns_empty(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(output=""))
        assert run(ctx) == []

    def test_output_without_headings_returns_empty(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(output="No headings."))
        assert run(ctx) == []

    def test_nonzero_returncode_returns_empty(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(returncode=1))
        assert run(ctx) == []


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

    def test_no_notification_when_worker_fails(self, tmp_path: Path):
        ctx = _make_ctx(
            tmp_path, worker=_mock_worker(returncode=1), also_notify=True
        )
        assert run(ctx) == []
