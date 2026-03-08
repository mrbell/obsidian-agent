# 2-4 — Job Registry and Runner

**Status**: `completed`
**Parent**: 2
**Children**: —
**Depends on**: 1-1, 1-4, 2-1

## Description

Implement `obsidian_agent/jobs/registry.py`, `obsidian_agent/context.py`, and the job
dispatch logic used by the `run` CLI command.

## Implementation Notes

### context.py

```python
@dataclass(frozen=True)
class JobContext:
    cfg: Config
    vault_path: Path
    store: IndexStore
    delivery: Delivery | None
    worker: ClaudeCodeWorker | None   # None for Class A jobs
    logger: logging.Logger
    run_date: datetime.date           # today; injected for testability
```

`worker` and `delivery` are optional so Class A jobs can be constructed without them.

### registry.py

```python
JobFn = Callable[[JobContext], list[JobOutput]]

_REGISTRY: dict[str, JobFn] = {}

def register(name: str):
    def decorator(fn: JobFn) -> JobFn:
        _REGISTRY[name] = fn
        return fn
    return decorator

def get_job(name: str) -> JobFn: ...
def list_jobs() -> list[str]: ...
```

Jobs self-register using `@register("task_notification")` at module import time.

### Runner

A thin function in `cli.py` (or a helper module):
1. Load config
2. Open `IndexStore`
3. Instantiate `Delivery` if needed
4. Instantiate `ClaudeCodeWorker` if needed
5. Build `JobContext`
6. Call `job_fn(ctx)`
7. For each output: write `VaultArtifact` to outbox or send `Notification` via delivery

## Testing & Validation

- `get_job("task_notification")` returns the correct function
- `get_job("nonexistent")` raises `KeyError` with a helpful message
- `list_jobs()` returns registered job names

## Definition of Done

Registry works. Job can be looked up by name and executed via `JobContext`.
