from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from obsidian_agent.context import JobContext
from obsidian_agent.jobs.registry import register
from obsidian_agent.outputs import JobOutput, VaultArtifact
from obsidian_agent.readwise.client import ReadwiseClient, ReadwiseClientError, ReadwiseDocument
from obsidian_agent.readwise.formatter import build_filename, format_document


STATE_FILE_NAME = "readwise_ingestion.json"
DESTINATION_DIR = "Readwise"


@dataclass(frozen=True)
class ReadwiseIngestionState:
    last_sync: str | None
    promoted_ids: frozenset[int]


@register("readwise_ingestion")
def run(ctx: JobContext) -> list[JobOutput]:
    if not os.environ.get("READWISE_API_TOKEN"):
        ctx.logger.error("readwise_ingestion: READWISE_API_TOKEN is not set")
        return []

    state_path = ctx.config.paths.state_dir / STATE_FILE_NAME
    state = _load_state(state_path)

    try:
        client = ReadwiseClient()
        documents = client.fetch_documents(updated_after=state.last_sync)
    except ReadwiseClientError as exc:
        ctx.logger.error("readwise_ingestion: %s", exc)
        return []

    outputs: list[JobOutput] = []
    promoted_ids = set(state.promoted_ids)
    existing_filenames = _existing_destination_filenames(ctx)
    new_ids: list[int] = []
    max_updated_at = state.last_sync

    for document in documents:
        if document.id in promoted_ids:
            continue
        if not document.highlights:
            continue

        filename = _choose_filename(document, existing_filenames)
        existing_filenames.add(filename)

        outputs.append(
            VaultArtifact(
                job_name="readwise_ingestion",
                filename=filename,
                content=format_document(document),
                destination=DESTINATION_DIR,
            )
        )
        promoted_ids.add(document.id)
        new_ids.append(document.id)
        max_updated_at = _max_iso_timestamp(max_updated_at, document.updated_at)

    if new_ids or max_updated_at != state.last_sync:
        _save_state(
            state_path,
            ReadwiseIngestionState(
                last_sync=max_updated_at,
                promoted_ids=frozenset(promoted_ids),
            ),
        )

    return outputs


def _load_state(path: Path) -> ReadwiseIngestionState:
    if not path.exists():
        return ReadwiseIngestionState(last_sync=None, promoted_ids=frozenset())

    data = json.loads(path.read_text(encoding="utf-8"))
    raw_ids = data.get("promoted_ids", [])
    promoted_ids = frozenset(int(item) for item in raw_ids)
    last_sync = data.get("last_sync")
    if last_sync is not None and not isinstance(last_sync, str):
        raise ValueError("readwise_ingestion state last_sync must be a string or null")
    return ReadwiseIngestionState(last_sync=last_sync, promoted_ids=promoted_ids)


def _save_state(path: Path, state: ReadwiseIngestionState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_sync": state.last_sync,
        "promoted_ids": sorted(state.promoted_ids),
    }
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _existing_destination_filenames(ctx: JobContext) -> set[str]:
    filenames: set[str] = set()

    vault_dest = ctx.config.paths.vault / DESTINATION_DIR
    if vault_dest.exists():
        filenames.update(path.name for path in vault_dest.glob("*.md"))

    outbox_dest = ctx.config.paths.outbox / "__destinations__" / DESTINATION_DIR
    if outbox_dest.exists():
        filenames.update(path.name for path in outbox_dest.glob("*.md"))

    return filenames


def _choose_filename(document: ReadwiseDocument, existing_filenames: set[str]) -> str:
    filename = build_filename(document)
    if filename not in existing_filenames:
        return filename
    return build_filename(document, with_id_suffix=True)


def _max_iso_timestamp(left: str | None, right: str | None) -> str | None:
    if not left:
        return right
    if not right:
        return left
    return right if _parse_iso(right) >= _parse_iso(left) else left


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
