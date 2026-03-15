from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from obsidian_agent.outputs import _DESTINATIONS_DIR

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromoteResult:
    promoted: int
    skipped: int    # destination already exists
    errors: int


def promote(
    outbox_root: Path,
    vault_path: Path,
    bot_inbox_rel: str,
    *,
    dry_run: bool = False,
) -> PromoteResult:
    """Copy eligible artifacts from outbox into vault/BotInbox/<job>/<filename>.

    Enforces:
    - .md extension only
    - No symlinks
    - No path traversal
    - No overwriting existing files

    With dry_run=True, logs what would be promoted but copies nothing.
    """
    inbox_root = vault_path / bot_inbox_rel
    inbox_resolved = inbox_root.resolve()

    promoted = 0
    skipped = 0
    errors = 0

    if not outbox_root.exists():
        log.info("Outbox does not exist, nothing to promote: %s", outbox_root)
        return PromoteResult(promoted=0, skipped=0, errors=0)

    for src in sorted(outbox_root.rglob("*")):
        if not src.is_file() and not src.is_symlink():
            continue

        rel = src.relative_to(outbox_root)

        # Reject symlinks
        if src.is_symlink():
            log.error("Rejecting symlink: %s", src)
            errors += 1
            continue

        # Reject non-.md files
        if src.suffix != ".md":
            log.warning("Rejecting non-.md file: %s", src)
            errors += 1
            continue

        # Compute destination: vault/BotInbox/<job>/<filename>.md by default,
        # or a custom vault-relative destination for artifacts staged under
        # outbox/__destinations__/...
        if rel.parts and rel.parts[0] == _DESTINATIONS_DIR:
            if len(rel.parts) < 2:
                log.error("Rejecting malformed destination artifact path: %s", src)
                errors += 1
                continue
            dest = vault_path / Path(*rel.parts[1:])
            allowed_root = vault_path.resolve()
        else:
            dest = inbox_root / rel
            allowed_root = inbox_resolved

        # Traversal check
        try:
            dest_resolved = dest.resolve()
        except OSError as exc:
            log.error("Could not resolve destination path %s: %s", dest, exc)
            errors += 1
            continue

        if not dest_resolved.is_relative_to(allowed_root):
            log.error(
                "Rejecting path traversal attempt: %s -> %s", src, dest_resolved
            )
            errors += 1
            continue

        # Skip if destination already exists
        if dest.exists():
            log.info("Skipping (already exists): %s", dest)
            skipped += 1
            continue

        if dry_run:
            log.info("[dry-run] Would promote: %s -> %s", src, dest)
            promoted += 1
            continue

        # Atomic copy: write to .tmp sibling, then os.replace()
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(dir=dest.parent, suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(src.read_bytes())
                os.replace(tmp_path, dest)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as exc:
            log.error("Failed to promote %s: %s", src, exc)
            errors += 1
            continue

        log.info("Promoted: %s -> %s", src, dest)
        promoted += 1

    return PromoteResult(promoted=promoted, skipped=skipped, errors=errors)
