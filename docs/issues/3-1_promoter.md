# 3-1 — Promoter Implementation

**Status**: `open`
**Parent**: 3
**Children**: —
**Depends on**: 1-1, 2-1

## Description

Implement `obsidian_agent/promote/promoter.py`. Scans the outbox and copies eligible
artifacts into `vault/BotInbox/YYYY/MM/<job>/` with strict safety enforcement.

## Implementation Notes

```python
@dataclass(frozen=True)
class PromoteResult:
    promoted: int
    skipped: int    # already exists at destination
    errors: int

def promote(outbox_root: Path, vault_path: Path, bot_inbox_rel: str) -> PromoteResult: ...
```

### For each file in outbox (recursive):

1. Reject if not `.md` extension
2. Reject if symlink
3. Compute destination: `vault / bot_inbox_rel / YYYY / MM / relative_outbox_path`
   - YYYY/MM derived from today's date (promotion date)
4. Resolve destination and verify it is inside `vault / bot_inbox_rel` (path traversal check)
5. Skip if destination already exists (log as skipped)
6. Create destination parent directories
7. Copy atomically: write to `.tmp` sibling, then `os.replace()`
8. Log each promotion

### Traversal check

```python
dest_resolved = dest_path.resolve()
inbox_resolved = (vault / bot_inbox_rel).resolve()
assert dest_resolved.is_relative_to(inbox_resolved)
```

## Testing & Validation

Required test cases:
- Promotes a new `.md` file to correct destination path
- Skips if destination already exists (no overwrite)
- Rejects a symlink source file
- Rejects a non-`.md` file
- Rejects a path with `..` traversal attempt
- Creates destination directories if absent
- Returns accurate `PromoteResult` counts

## Definition of Done

All test cases above pass. No existing vault file can be overwritten.
