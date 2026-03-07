# 5-1 — Claude Code Worker

**Status**: `open`
**Parent**: 5
**Children**: —
**Depends on**: 4-4

## Description

Implement `obsidian_agent/agent/worker.py`. Launches Claude Code headlessly with the vault
MCP server registered. Used by all Class B and Class C jobs.

## Implementation Notes

Exact invocation details depend on spike 4-4. Update this issue with findings before implementing.

### Interface

```python
@dataclass(frozen=True)
class WorkerResult:
    returncode: int
    output: str     # stdout content (the model's response)
    stderr: str

@dataclass
class ClaudeCodeWorker:
    cfg: AgentConfig    # command, args, timeout, work_dir
    vault_path: Path
    db_path: Path

    def run(self, prompt: str, web_search: bool = False) -> WorkerResult: ...
```

### Run logic

1. Write MCP config JSON to a temp file pointing at `obsidian-agent mcp`
2. Build the `claude` command with headless flags and `--mcp-config <tempfile>`
3. Set working directory to a fresh temp dir (isolated per invocation)
4. Run via `subprocess.run()` with `timeout`
5. Return `WorkerResult`

Claude Code is never given the vault path directly. It accesses vault content through the
MCP server only.

### Error handling

- Timeout → log, return non-zero `WorkerResult` (do not raise)
- Non-zero exit → log stderr, return result (caller decides whether to fail)
- The worker does not interpret output; jobs do

## Testing & Validation

- Worker tested with a dummy command (`echo`) in place of `claude`
- Timeout is enforced (test with a command that sleeps longer than timeout)
- MCP config temp file is cleaned up after invocation
- Working directory is cleaned up after invocation

## Definition of Done

`ClaudeCodeWorker.run()` invokes the configured command, captures output, enforces timeout,
cleans up temp files. Tests pass with dummy command.
