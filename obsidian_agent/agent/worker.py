from obsidian_agent.agent.base import WorkerResult
from obsidian_agent.agent.claude import ClaudeBackendAdapter

# Backward-compatible aliases while callers migrate to the backend-neutral factory.
ClaudeCodeWorker = ClaudeBackendAdapter

__all__ = ["ClaudeBackendAdapter", "ClaudeCodeWorker", "WorkerResult"]
