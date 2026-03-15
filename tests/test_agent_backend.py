from __future__ import annotations

from dataclasses import dataclass

from obsidian_agent.agent.base import (
    AgentBackend,
    AgentCapabilities,
    AgentWorker,
    WorkerResult,
)


def test_worker_result_supports_backend_metadata() -> None:
    result = WorkerResult(
        returncode=0,
        output="READY",
        stderr="",
        backend_id="claude",
        model_version="claude/sonnet",
    )

    assert result.backend_id == "claude"
    assert result.model_version == "claude/sonnet"


def test_backend_capability_validation_raises_for_unsupported_feature() -> None:
    backend = AgentBackend(
        backend_id="fake",
        capabilities=AgentCapabilities(mcp=False),
    )

    try:
        backend.require_capability("mcp")
    except ValueError as exc:
        assert "fake" in str(exc)
        assert "mcp" in str(exc)
    else:
        raise AssertionError("Expected unsupported capability to raise")


def test_agent_worker_protocol_is_backend_neutral() -> None:
    @dataclass
    class FakeWorker:
        backend: AgentBackend

        def run(
            self,
            prompt: str,
            *,
            web_search: bool = False,
            with_mcp: bool = True,
        ) -> WorkerResult:
            assert prompt == "ping"
            assert web_search is False
            assert with_mcp is True
            return WorkerResult(0, "pong", "", backend_id=self.backend.backend_id)

    worker = FakeWorker(
        backend=AgentBackend(
            backend_id="fake",
            capabilities=AgentCapabilities(
                mcp=True,
                web_search=True,
                structured_output=True,
            ),
        )
    )

    assert isinstance(worker, AgentWorker)
    result = worker.run("ping")
    assert result.output == "pong"
    assert result.backend_id == "fake"
