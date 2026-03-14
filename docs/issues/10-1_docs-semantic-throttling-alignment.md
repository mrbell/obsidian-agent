# 10-1 — Docs: Semantic Throttling Alignment

**Status**: `open`
**Parent**: 10
**Children**: —
**Depends on**: 6-2

## Description

Clarify the semantic indexing docs and config comments so they reflect the implementation:
embeddings run for all stale notes, while `semantic.max_notes_per_run` limits only the
Claude-driven intelligence extraction phase.

This is intentionally a docs/config alignment issue, not a behavior change.

## Implementation Notes

- Update [README.md](/home/mbell/Code/obsidian-agent/README.md) setup guidance for
  `index-semantic`
- Update [config/config.yaml.example](/home/mbell/Code/obsidian-agent/config/config.yaml.example)
  comments around `semantic.max_notes_per_run`
- Update [DESIGN.md](/home/mbell/Code/obsidian-agent/DESIGN.md) anywhere the throttling behavior
  is implied incorrectly

Call out explicitly that:

- local embeddings are unthrottled and run on all stale notes
- the throttle exists to cap external Claude usage during the intelligence phase

## Testing & Validation

Follow TDD even for docs alignment:

- Add or update a lightweight test if any user-facing help text or config rendering is covered
- Otherwise validate by review that all three documents say the same thing

## Definition of Done

- README, DESIGN, and config example all describe the same throttling behavior
- No code behavior changed
