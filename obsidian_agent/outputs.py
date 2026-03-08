from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VaultArtifact:
    job_name: str
    filename: str   # e.g. "2026-03-07_task-digest.md"
    content: str

    def write_to_outbox(self, outbox_root: Path) -> Path:
        """Write content atomically to outbox_root / job_name / filename.

        Raises ValueError if filename contains '..' or is an absolute path.
        Returns the final destination path.
        """
        if Path(self.filename).is_absolute():
            raise ValueError(f"filename must not be an absolute path: {self.filename!r}")
        if ".." in Path(self.filename).parts:
            raise ValueError(f"filename must not contain '..': {self.filename!r}")

        dest_dir = outbox_root / self.job_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / self.filename

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
