from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


_DESTINATIONS_DIR = "__destinations__"


def _validate_relative_path(value: str, *, field_name: str) -> str:
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"{field_name} must not be an absolute path: {value!r}")
    if ".." in path.parts:
        raise ValueError(f"{field_name} must not contain '..': {value!r}")
    normalized = str(path).strip()
    if normalized in {"", "."}:
        raise ValueError(f"{field_name} must not be empty: {value!r}")
    return normalized


@dataclass(frozen=True)
class VaultArtifact:
    job_name: str
    filename: str   # e.g. "2026-03-07_task-digest.md"
    content: str
    destination: str | None = None

    def write_to_outbox(self, outbox_root: Path) -> Path:
        """Write content atomically to outbox_root / job_name / filename.

        Raises ValueError if filename contains '..' or is an absolute path.
        Returns the final destination path.
        """
        filename = _validate_relative_path(self.filename, field_name="filename")

        if self.destination is None:
            dest_dir = outbox_root / self.job_name
        else:
            destination = _validate_relative_path(
                self.destination,
                field_name="destination",
            )
            dest_dir = outbox_root / _DESTINATIONS_DIR / destination
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename

        # Atomic write: write to a sibling .tmp file then rename into place
        fd, tmp_path = tempfile.mkstemp(dir=dest_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(self.content)
            os.replace(tmp_path, dest)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return dest


@dataclass(frozen=True)
class Notification:
    subject: str
    body: str


JobOutput = VaultArtifact | Notification
