# 10-2 — Worker: Treat Claude `is_error` Results as Failures

**Status**: `open`
**Parent**: 10
**Children**: —
**Depends on**: 5-1

## Description

The Claude worker currently parses `--output-format json`, logs `is_error=true`, but still
returns the `result` text as if the invocation succeeded. This can allow failed Claude runs
to flow downstream into jobs that validate only for loose output shape.

The worker should convert structured Claude failures into failed `WorkerResult`s so callers
do not accidentally promote or deliver error output.

## Implementation Notes

- Update `obsidian_agent/agent/worker.py`
- If the parsed JSON result object contains `is_error: true`:
  - return non-zero `WorkerResult.returncode`
  - return empty `output`
  - surface the error text in `stderr`
- Preserve current fallback behavior when stdout is not parseable JSON at all
- Keep the fix local so existing job callers do not need redesign

## Testing & Validation

Red/green TDD:

- Add a failing worker test for a JSON result object with `is_error=true`
- Assert the returned result is treated as a failure
- Add at least one regression test proving normal success objects still pass through unchanged

## Definition of Done

- Structured Claude failures can no longer be mistaken for successful job output
- Worker tests cover both `is_error=false` and `is_error=true` paths
