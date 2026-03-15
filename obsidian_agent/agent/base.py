from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class WorkerResult:
    returncode: int
    output: str
    stderr: str
    backend_id: str | None = None
    model_version: str | None = None


@dataclass(frozen=True)
class AgentCapabilities:
    prompt_execution: bool = True
    mcp: bool = False
    web_search: bool = False
    structured_output: bool = False


@dataclass(frozen=True)
class AgentBackend:
    backend_id: str
    model_version: str | None = None
    capabilities: AgentCapabilities = field(default_factory=AgentCapabilities)

    def require_capability(self, capability: str) -> None:
        if not getattr(self.capabilities, capability):
            raise ValueError(
                f"Backend '{self.backend_id}' does not support capability '{capability}'"
            )


@runtime_checkable
class AgentWorker(Protocol):
    @property
    def backend(self) -> AgentBackend:
        ...

    def run(
        self,
        prompt: str,
        *,
        web_search: bool = False,
        with_mcp: bool = True,
    ) -> WorkerResult:
        ...
