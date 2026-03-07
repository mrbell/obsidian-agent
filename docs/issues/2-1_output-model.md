# 2-1 — Output Model

**Status**: `open`
**Parent**: 2
**Children**: —
**Depends on**: 1-1

## Description

Implement `obsidian_agent/outputs.py` defining `VaultArtifact` and `Notification`, and the
logic to write artifacts atomically to the outbox.

## Implementation Notes

```python
@dataclass(frozen=True)
class VaultArtifact:
    job_name: str
    filename: str   # e.g. "2026-03-07_task-digest.md"
    content: str

    def write_to_outbox(self, outbox_root: Path) -> Path:
        # destination: outbox_root / job_name / filename
        # write atomically via temp file + rename
        # reject ".." in filename
        ...

@dataclass(frozen=True)
class Notification:
    subject: str
    body: str

JobOutput = VaultArtifact | Notification
```

Atomic write: write to a `.tmp` file in the same directory, then `os.replace()`.
Reject any `filename` containing `..` or an absolute path component.

## Testing & Validation

- `write_to_outbox` creates file at expected path
- Atomic write: file appears complete (no partial write visible)
- `..` in filename raises `ValueError`
- Outbox subdirectory created if absent

## Definition of Done

Both dataclasses defined. `write_to_outbox` writes correctly and atomically.
