# 1-5 — Index Builder

**Status**: `completed`
**Parent**: 1
**Children**: —
**Depends on**: 1-3, 1-4

## Description

Implement `obsidian_agent/index/build_index.py`. Incremental scan of the vault that updates
the DuckDB index while correctly handling modified, deleted, and renamed/moved notes.

## Implementation Notes

Full algorithm is documented in `DESIGN.md §7`. Summary:

1. Walk all `.md` files, collect `seen_paths`
2. For each file: check `mtime_ns` + `size_bytes` against DB
   - Unchanged → skip
   - Changed → compute `content_sha256`
     - Hash unchanged → update metadata only
     - Hash changed → delete derived rows, re-parse, re-insert, invalidate `note_summaries`
3. Detect deleted paths (in DB but not in `seen_paths`)
4. Rename detection: match deleted paths to new paths by `content_sha256`; update in place
5. Delete records for confirmed deletions
6. All operations in a single transaction

### Key function

```python
def build_index(vault_path: Path, store: IndexStore) -> IndexStats:
    ...

@dataclass
class IndexStats:
    scanned: int
    added: int
    updated: int
    renamed: int
    deleted: int
    unchanged: int
```

### Derived row replacement pattern

When a note's content changes, delete-then-insert derived rows:
```sql
DELETE FROM tasks WHERE note_relpath = ?
DELETE FROM links WHERE note_relpath = ?
DELETE FROM tags WHERE note_relpath = ?
DELETE FROM headings WHERE note_relpath = ?
DELETE FROM frontmatter WHERE note_relpath = ?
DELETE FROM note_summaries WHERE note_relpath = ?
-- then insert fresh rows from parse result
```

## Testing & Validation

Integration tests using a temp vault directory:
- New note is indexed
- Modified note updates derived rows (old content gone, new content present)
- Deleted note is removed from all tables
- Renamed note: `note_relpath` updated in place, derived data preserved
- Unchanged note is skipped (mtime/size check)
- Hash-only change (mtime touched, content same) updates metadata without re-parsing

## Definition of Done

`build_index()` passes all integration test scenarios above. Returns accurate `IndexStats`.
