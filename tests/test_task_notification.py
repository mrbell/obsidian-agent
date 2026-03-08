from datetime import date, timedelta
from pathlib import Path

import pytest

from obsidian_agent.config import (
    AgentConfig,
    CacheConfig,
    Config,
    DeliveryConfig,
    JobsConfig,
    PathsConfig,
    ResearchDigestConfig,
    TaskNotificationConfig,
)
from obsidian_agent.context import JobContext
from obsidian_agent.index.store import IndexStore
from obsidian_agent.jobs import task_notification
from obsidian_agent.outputs import Notification, VaultArtifact

TODAY = date(2026, 3, 8)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_config(tmp_path: Path, **job_kwargs) -> Config:
    vault = tmp_path / "vault"
    vault.mkdir()
    return Config(
        paths=PathsConfig(
            vault=vault,
            outbox=tmp_path / "outbox",
            state_dir=tmp_path / "state",
            bot_inbox_rel="BotInbox",
        ),
        cache=CacheConfig(duckdb_path=tmp_path / "index.duckdb"),
        delivery=DeliveryConfig(),
        agent=None,
        jobs=JobsConfig(
            task_notification=TaskNotificationConfig(**job_kwargs),
            research_digest=ResearchDigestConfig(),
        ),
    )


@pytest.fixture
def store(tmp_path: Path) -> IndexStore:
    s = IndexStore(tmp_path / "index.duckdb")
    yield s
    s.close()


def _insert_task(
    store: IndexStore,
    relpath: str,
    text: str,
    due_date: date | None,
    status: str = "open",
) -> None:
    store.conn.execute(
        "INSERT INTO tasks VALUES (?, ?, ?, ?, ?)",
        [relpath, 1, status, text, due_date],
    )


def _ctx(store: IndexStore, config: Config) -> JobContext:
    return JobContext(store=store, config=config, today=TODAY)


# ---------------------------------------------------------------------------
# Basic bucketing
# ---------------------------------------------------------------------------

class TestBucketing:
    def test_due_today_in_due_today_section(self, store, tmp_path):
        _insert_task(store, "note.md", "Do the thing", TODAY)
        cfg = _make_config(tmp_path)
        result = task_notification.run(_ctx(store, cfg))
        assert len(result) == 1
        body = result[0].body
        assert "## Due today" in body
        assert "Do the thing" in body

    def test_upcoming_task_in_upcoming_section(self, store, tmp_path):
        future = TODAY + timedelta(days=2)
        _insert_task(store, "note.md", "Future task", future)
        cfg = _make_config(tmp_path)
        result = task_notification.run(_ctx(store, cfg))
        body = result[0].body
        assert "## Due in the next" in body
        assert "Future task" in body

    def test_overdue_task_in_overdue_section(self, store, tmp_path):
        past = TODAY - timedelta(days=5)
        _insert_task(store, "note.md", "Old task", past)
        cfg = _make_config(tmp_path)
        result = task_notification.run(_ctx(store, cfg))
        body = result[0].body
        assert "## Overdue" in body
        assert "Old task" in body

    def test_task_beyond_lookahead_not_included(self, store, tmp_path):
        far_future = TODAY + timedelta(days=10)
        _insert_task(store, "note.md", "Far future task", far_future)
        cfg = _make_config(tmp_path, notify_if_empty=True)
        result = task_notification.run(_ctx(store, cfg))
        notification = result[0]
        assert "Far future task" not in notification.body


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

class TestFiltering:
    def test_tasks_without_due_date_excluded(self, store, tmp_path):
        _insert_task(store, "note.md", "No date task", None)
        cfg = _make_config(tmp_path, notify_if_empty=True)
        result = task_notification.run(_ctx(store, cfg))
        assert "No date task" not in result[0].body

    def test_done_tasks_excluded(self, store, tmp_path):
        _insert_task(store, "note.md", "Done task", TODAY, status="done")
        cfg = _make_config(tmp_path, notify_if_empty=True)
        result = task_notification.run(_ctx(store, cfg))
        assert "Done task" not in result[0].body

    def test_cancelled_tasks_excluded(self, store, tmp_path):
        _insert_task(store, "note.md", "Cancelled task", TODAY, status="cancelled")
        cfg = _make_config(tmp_path, notify_if_empty=True)
        result = task_notification.run(_ctx(store, cfg))
        assert "Cancelled task" not in result[0].body

    def test_include_overdue_false_hides_overdue(self, store, tmp_path):
        past = TODAY - timedelta(days=3)
        _insert_task(store, "note.md", "Old task", past)
        cfg = _make_config(tmp_path, include_overdue=False, notify_if_empty=True)
        result = task_notification.run(_ctx(store, cfg))
        assert "Old task" not in result[0].body
        assert "## Overdue" not in result[0].body


# ---------------------------------------------------------------------------
# notify_if_empty
# ---------------------------------------------------------------------------

class TestNotifyIfEmpty:
    def test_no_output_when_empty_and_notify_false(self, store, tmp_path):
        cfg = _make_config(tmp_path, notify_if_empty=False)
        result = task_notification.run(_ctx(store, cfg))
        assert result == []

    def test_output_when_empty_and_notify_true(self, store, tmp_path):
        cfg = _make_config(tmp_path, notify_if_empty=True)
        result = task_notification.run(_ctx(store, cfg))
        assert len(result) == 1

    def test_no_output_when_overdue_only_and_include_overdue_false(
        self, store, tmp_path
    ):
        past = TODAY - timedelta(days=3)
        _insert_task(store, "note.md", "Old task", past)
        cfg = _make_config(tmp_path, include_overdue=False, notify_if_empty=False)
        result = task_notification.run(_ctx(store, cfg))
        assert result == []


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------

class TestOutputFormat:
    def test_notification_type(self, store, tmp_path):
        _insert_task(store, "note.md", "Task", TODAY)
        cfg = _make_config(tmp_path)
        result = task_notification.run(_ctx(store, cfg))
        assert isinstance(result[0], Notification)

    def test_subject_contains_count(self, store, tmp_path):
        _insert_task(store, "a.md", "Task 1", TODAY)
        _insert_task(store, "b.md", "Task 2", TODAY)
        cfg = _make_config(tmp_path)
        result = task_notification.run(_ctx(store, cfg))
        assert "2 tasks" in result[0].subject

    def test_subject_singular_task(self, store, tmp_path):
        _insert_task(store, "note.md", "Solo task", TODAY)
        cfg = _make_config(tmp_path)
        result = task_notification.run(_ctx(store, cfg))
        assert "1 task " in result[0].subject
        assert "tasks" not in result[0].subject

    def test_note_basename_in_body(self, store, tmp_path):
        _insert_task(store, "projects/work/sprint.md", "Sprint task", TODAY)
        cfg = _make_config(tmp_path)
        result = task_notification.run(_ctx(store, cfg))
        assert "sprint.md" in result[0].body

    def test_upcoming_shows_due_date(self, store, tmp_path):
        future = TODAY + timedelta(days=2)
        _insert_task(store, "note.md", "Future task", future)
        cfg = _make_config(tmp_path)
        result = task_notification.run(_ctx(store, cfg))
        assert str(future) in result[0].body


# ---------------------------------------------------------------------------
# also_write_vault_artifact
# ---------------------------------------------------------------------------

class TestVaultArtifact:
    def test_artifact_not_produced_by_default(self, store, tmp_path):
        _insert_task(store, "note.md", "Task", TODAY)
        cfg = _make_config(tmp_path, also_write_vault_artifact=False)
        result = task_notification.run(_ctx(store, cfg))
        assert not any(isinstance(o, VaultArtifact) for o in result)

    def test_artifact_produced_when_configured(self, store, tmp_path):
        _insert_task(store, "note.md", "Task", TODAY)
        cfg = _make_config(tmp_path, also_write_vault_artifact=True)
        result = task_notification.run(_ctx(store, cfg))
        artifacts = [o for o in result if isinstance(o, VaultArtifact)]
        assert len(artifacts) == 1
        assert artifacts[0].job_name == "task_notification"
        assert artifacts[0].filename.endswith(".md")
