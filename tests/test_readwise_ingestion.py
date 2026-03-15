from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from obsidian_agent.config import CacheConfig, Config, DeliveryConfig, JobsConfig, PathsConfig, ReadwiseIngestionConfig
from obsidian_agent.context import JobContext
from obsidian_agent.index.store import IndexStore
from obsidian_agent.jobs.readwise_ingestion import run
from obsidian_agent.outputs import VaultArtifact
from obsidian_agent.readwise.client import ReadwiseDocument, ReadwiseHighlight


def _make_ctx(tmp_path: Path) -> JobContext:
    vault = tmp_path / "vault"
    vault.mkdir()
    outbox = tmp_path / "outbox"
    state = tmp_path / "state"
    db = tmp_path / "index.duckdb"
    cfg = Config(
        paths=PathsConfig(
            vault=vault,
            outbox=outbox,
            state_dir=state,
            bot_inbox_rel="BotInbox",
        ),
        cache=CacheConfig(duckdb_path=db),
        delivery=DeliveryConfig(),
        agent=None,
        jobs=JobsConfig(
            readwise_ingestion=ReadwiseIngestionConfig(enabled=True, schedule="0 6 * * *")
        ),
    )
    return JobContext(
        store=IndexStore(db),
        config=cfg,
        today=date(2026, 3, 14),
    )


def _doc(
    doc_id: int,
    *,
    title: str = "Interesting Article",
    category: str = "articles",
    highlights: list[ReadwiseHighlight] | None = None,
    updated_at: str = "2026-03-12T10:00:00Z",
) -> ReadwiseDocument:
    return ReadwiseDocument(
        id=doc_id,
        title=title,
        author="Ada",
        category=category,
        source_url="https://example.com/post",
        readwise_url=f"https://readwise.io/bookreview/{doc_id}",
        saved_at="2026-03-11T12:00:00Z",
        updated_at=updated_at,
        highlights=highlights if highlights is not None else [
            ReadwiseHighlight(
                id=doc_id * 100,
                text="Highlighted text",
                note=None,
                location=None,
                location_type=None,
                highlighted_at="2026-03-11T12:00:00Z",
                updated_at=updated_at,
            )
        ],
    )


def test_run_emits_destination_artifact_and_writes_state(tmp_path: Path, monkeypatch) -> None:
    ctx = _make_ctx(tmp_path)
    monkeypatch.setenv("READWISE_API_TOKEN", "token")

    with patch("obsidian_agent.jobs.readwise_ingestion.ReadwiseClient.fetch_documents", return_value=[_doc(123)]):
        outputs = run(ctx)

    artifact = next(o for o in outputs if isinstance(o, VaultArtifact))
    assert artifact.destination == "Readwise"
    assert artifact.filename == "interesting-article.md"

    state = json.loads((tmp_path / "state" / "readwise_ingestion.json").read_text(encoding="utf-8"))
    assert state["last_sync"] == "2026-03-12T10:00:00Z"
    assert state["promoted_ids"] == [123]


def test_run_skips_already_promoted_ids(tmp_path: Path, monkeypatch) -> None:
    ctx = _make_ctx(tmp_path)
    monkeypatch.setenv("READWISE_API_TOKEN", "token")
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "readwise_ingestion.json").write_text(
        json.dumps({"last_sync": "2026-03-10T00:00:00Z", "promoted_ids": [123]}),
        encoding="utf-8",
    )

    with patch("obsidian_agent.jobs.readwise_ingestion.ReadwiseClient.fetch_documents", return_value=[_doc(123)]):
        outputs = run(ctx)

    assert outputs == []


def test_run_skips_documents_without_highlights(tmp_path: Path, monkeypatch) -> None:
    ctx = _make_ctx(tmp_path)
    monkeypatch.setenv("READWISE_API_TOKEN", "token")

    with patch(
        "obsidian_agent.jobs.readwise_ingestion.ReadwiseClient.fetch_documents",
        return_value=[_doc(123, highlights=[])],
    ):
        outputs = run(ctx)

    assert outputs == []


def test_run_appends_id_on_filename_collision(tmp_path: Path, monkeypatch) -> None:
    ctx = _make_ctx(tmp_path)
    monkeypatch.setenv("READWISE_API_TOKEN", "token")
    readwise_dir = tmp_path / "vault" / "Readwise"
    readwise_dir.mkdir()
    (readwise_dir / "interesting-article.md").write_text("existing", encoding="utf-8")

    with patch("obsidian_agent.jobs.readwise_ingestion.ReadwiseClient.fetch_documents", return_value=[_doc(123)]):
        outputs = run(ctx)

    artifact = next(o for o in outputs if isinstance(o, VaultArtifact))
    assert artifact.filename == "interesting-article-123.md"


def test_run_tracks_max_seen_updated_timestamp(tmp_path: Path, monkeypatch) -> None:
    ctx = _make_ctx(tmp_path)
    monkeypatch.setenv("READWISE_API_TOKEN", "token")

    docs = [
        _doc(123, updated_at="2026-03-11T10:00:00Z"),
        _doc(456, title="Other Article", updated_at="2026-03-12T15:30:00Z"),
    ]
    with patch("obsidian_agent.jobs.readwise_ingestion.ReadwiseClient.fetch_documents", return_value=docs):
        run(ctx)

    state = json.loads((tmp_path / "state" / "readwise_ingestion.json").read_text(encoding="utf-8"))
    assert state["last_sync"] == "2026-03-12T15:30:00Z"
    assert state["promoted_ids"] == [123, 456]
