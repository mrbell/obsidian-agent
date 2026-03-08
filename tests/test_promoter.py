from __future__ import annotations

import os
from pathlib import Path

import pytest

from obsidian_agent.promote.promoter import PromoteResult, promote


@pytest.fixture()
def dirs(tmp_path: Path):
    outbox = tmp_path / "outbox"
    vault = tmp_path / "vault"
    outbox.mkdir()
    vault.mkdir()
    return outbox, vault


BOT_INBOX = "BotInbox"


def _write(path: Path, content: str = "# Note\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_promotes_md_file_to_correct_destination(dirs):
    outbox, vault = dirs
    _write(outbox / "task_notification" / "2026-03-08_tasks.md")

    result = promote(outbox, vault, BOT_INBOX)

    dest = vault / BOT_INBOX / "task_notification" / "2026-03-08_tasks.md"
    assert dest.exists()
    assert result == PromoteResult(promoted=1, skipped=0, errors=0)


def test_creates_destination_directories_if_absent(dirs):
    outbox, vault = dirs
    _write(outbox / "research_digest" / "2026-03-08_agentic-coding.md")

    promote(outbox, vault, BOT_INBOX)

    assert (vault / BOT_INBOX / "research_digest").is_dir()


def test_preserves_file_content(dirs):
    outbox, vault = dirs
    content = "# Research\n\nSome content here.\n"
    _write(outbox / "research_digest" / "digest.md", content)

    promote(outbox, vault, BOT_INBOX)

    dest = vault / BOT_INBOX / "research_digest" / "digest.md"
    assert dest.read_text(encoding="utf-8") == content


def test_returns_accurate_counts_for_mixed_batch(dirs):
    outbox, vault = dirs
    _write(outbox / "job_a" / "note1.md")
    _write(outbox / "job_a" / "note2.md")

    result = promote(outbox, vault, BOT_INBOX)

    assert result == PromoteResult(promoted=2, skipped=0, errors=0)


# ---------------------------------------------------------------------------
# Skip / no overwrite
# ---------------------------------------------------------------------------

def test_skips_if_destination_already_exists(dirs):
    outbox, vault = dirs
    _write(outbox / "task_notification" / "note.md", "# New")
    existing = vault / BOT_INBOX / "task_notification" / "note.md"
    _write(existing, "# Original")

    result = promote(outbox, vault, BOT_INBOX)

    assert existing.read_text(encoding="utf-8") == "# Original"
    assert result == PromoteResult(promoted=0, skipped=1, errors=0)


# ---------------------------------------------------------------------------
# Rejections
# ---------------------------------------------------------------------------

def test_rejects_symlink_source(dirs):
    outbox, vault = dirs
    real = outbox / "real.md"
    _write(real)
    link = outbox / "task_notification" / "linked.md"
    link.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(real, link)

    result = promote(outbox, vault, BOT_INBOX)

    dest = vault / BOT_INBOX / "task_notification" / "linked.md"
    assert not dest.exists()
    assert result.errors >= 1


def test_rejects_non_md_file(dirs):
    outbox, vault = dirs
    path = outbox / "task_notification" / "export.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not markdown")

    result = promote(outbox, vault, BOT_INBOX)

    assert result == PromoteResult(promoted=0, skipped=0, errors=1)


def test_rejects_path_traversal_via_symlinked_directory(dirs):
    outbox, vault = dirs
    # A symlinked directory inside the outbox whose resolved path escapes the inbox.
    # rglob follows directory symlinks (Python 3.12+ default), so the file is found.
    # The traversal check (dest.resolve().is_relative_to(inbox_resolved)) catches it.
    escape_target = outbox.parent / "escape_target"
    escape_target.mkdir()
    _write(escape_target / "evil.md", "# evil")

    job_dir = outbox / "some_job"
    job_dir.mkdir()
    os.symlink(escape_target, job_dir / "escape_link")

    result = promote(outbox, vault, BOT_INBOX)

    # File should be rejected — resolved destination escapes vault/BotInbox
    assert not (vault / BOT_INBOX / "some_job" / "escape_link" / "evil.md").exists()
    assert result.errors >= 1


# ---------------------------------------------------------------------------
# Empty outbox
# ---------------------------------------------------------------------------

def test_empty_outbox_returns_zero_counts(dirs):
    outbox, vault = dirs

    result = promote(outbox, vault, BOT_INBOX)

    assert result == PromoteResult(promoted=0, skipped=0, errors=0)


def test_nonexistent_outbox_returns_zero_counts(tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    outbox = tmp_path / "outbox_does_not_exist"

    result = promote(outbox, vault, BOT_INBOX)

    assert result == PromoteResult(promoted=0, skipped=0, errors=0)


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

def test_dry_run_does_not_copy_files(dirs):
    outbox, vault = dirs
    _write(outbox / "task_notification" / "note.md")

    result = promote(outbox, vault, BOT_INBOX, dry_run=True)

    dest = vault / BOT_INBOX / "task_notification" / "note.md"
    assert not dest.exists()
    assert result == PromoteResult(promoted=1, skipped=0, errors=0)
