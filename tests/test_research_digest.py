from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from obsidian_agent.agent.worker import WorkerResult
from obsidian_agent.config import ResearchTopic
from obsidian_agent.context import JobContext
from obsidian_agent.index.store import IndexStore
from obsidian_agent.jobs.research_digest import run, _topic_slug, _validate_output, _build_prompt
from obsidian_agent.outputs import Notification, VaultArtifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_OUTPUT = """\
# Weekly Research Digest: agentic coding
**Period**: 2026-03-01 to 2026-03-08

## Trends
Things are moving fast in agentic coding this week.

## Notable Articles
### Some Article
**Source**: example.com  **Date**: 2026-03-05  **URL**: https://example.com/a
A brief summary of why this matters.

## Follow-up Questions
- What does this mean for developers?
"""


_UNSET = object()


def _make_ctx(tmp_path: Path, worker=None, topics=_UNSET, also_notify=False):
    db = tmp_path / "index.duckdb"
    vault = tmp_path / "vault"
    vault.mkdir(exist_ok=True)

    from obsidian_agent.config import (
        Config, PathsConfig, CacheConfig, DeliveryConfig, JobsConfig,
        ResearchDigestConfig,
    )

    default_topics = [ResearchTopic(name="agentic coding")]
    cfg = Config(
        paths=PathsConfig(
            vault=vault,
            outbox=tmp_path / "outbox",
            state_dir=tmp_path / "state",
            bot_inbox_rel="BotInbox",
        ),
        cache=CacheConfig(duckdb_path=db),
        delivery=DeliveryConfig(),
        agent=None,
        jobs=JobsConfig(
            research_digest=ResearchDigestConfig(
                enabled=True,
                topics=default_topics if topics is _UNSET else topics,
                lookback_days=7,
                also_notify=also_notify,
            )
        ),
    )

    store = IndexStore(db)
    return JobContext(
        store=store,
        config=cfg,
        today=date(2026, 3, 8),
        worker=worker,
    )


def _mock_worker(output: str = VALID_OUTPUT, returncode: int = 0) -> MagicMock:
    worker = MagicMock()
    worker.run.return_value = WorkerResult(
        returncode=returncode,
        output=output,
        stderr="",
    )
    return worker


# ---------------------------------------------------------------------------
# _topic_slug
# ---------------------------------------------------------------------------

class TestTopicSlug:
    def test_spaces_become_hyphens(self):
        assert _topic_slug(ResearchTopic(name="agentic coding")) == "agentic-coding"

    def test_lowercased(self):
        assert _topic_slug(ResearchTopic(name="Large Language Models")) == "large-language-models"

    def test_special_chars_removed(self):
        assert _topic_slug(ResearchTopic(name="C++ & Rust")) == "c-rust"


# ---------------------------------------------------------------------------
# _validate_output
# ---------------------------------------------------------------------------

class TestValidateOutput:
    def test_valid_output_passes(self):
        assert _validate_output(VALID_OUTPUT) is True

    def test_empty_string_fails(self):
        assert _validate_output("") is False

    def test_whitespace_only_fails(self):
        assert _validate_output("   \n\n") is False

    def test_no_headings_fails(self):
        assert _validate_output("Some text without headings.") is False

    def test_has_heading_passes(self):
        assert _validate_output("# Title\n\n## Section\nContent.") is True


# ---------------------------------------------------------------------------
# Job: produces artifacts
# ---------------------------------------------------------------------------

class TestRunProducesArtifacts:
    def test_produces_one_artifact_per_topic(self, tmp_path: Path):
        worker = _mock_worker()
        ctx = _make_ctx(tmp_path, worker=worker, topics=[ResearchTopic(name="agentic coding"), ResearchTopic(name="llms")])
        worker.run.return_value = WorkerResult(0, VALID_OUTPUT, "")

        outputs = run(ctx)
        artifacts = [o for o in outputs if isinstance(o, VaultArtifact)]
        assert len(artifacts) == 2

    def test_artifact_filename_format(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(), topics=[ResearchTopic(name="agentic coding")])
        outputs = run(ctx)
        artifact = next(o for o in outputs if isinstance(o, VaultArtifact))
        assert artifact.filename == "2026-03-08_research-digest-agentic-coding.md"

    def test_artifact_job_name(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker())
        outputs = run(ctx)
        artifact = next(o for o in outputs if isinstance(o, VaultArtifact))
        assert artifact.job_name == "research_digest"

    def test_artifact_content_is_worker_output(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker())
        outputs = run(ctx)
        artifact = next(o for o in outputs if isinstance(o, VaultArtifact))
        assert artifact.content == VALID_OUTPUT

    def test_worker_called_with_web_search_true(self, tmp_path: Path):
        worker = _mock_worker()
        ctx = _make_ctx(tmp_path, worker=worker)
        run(ctx)
        _, kwargs = worker.run.call_args
        assert kwargs.get("web_search") is True


# ---------------------------------------------------------------------------
# Job: invalid / failed output is rejected
# ---------------------------------------------------------------------------

class TestRunRejectsInvalidOutput:
    def test_empty_output_produces_no_artifact(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(output=""))
        outputs = run(ctx)
        assert not any(isinstance(o, VaultArtifact) for o in outputs)

    def test_output_without_headings_produces_no_artifact(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(output="No headings here."))
        outputs = run(ctx)
        assert not any(isinstance(o, VaultArtifact) for o in outputs)

    def test_nonzero_returncode_produces_no_artifact(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(returncode=1))
        outputs = run(ctx)
        assert not any(isinstance(o, VaultArtifact) for o in outputs)

    def test_partial_failure_still_produces_successful_artifacts(self, tmp_path: Path):
        worker = MagicMock()
        worker.run.side_effect = [
            WorkerResult(0, VALID_OUTPUT, ""),   # topic 1 succeeds
            WorkerResult(1, "", "api error"),    # topic 2 fails
        ]
        ctx = _make_ctx(tmp_path, worker=worker, topics=[ResearchTopic(name="topic-a"), ResearchTopic(name="topic-b")])
        outputs = run(ctx)
        artifacts = [o for o in outputs if isinstance(o, VaultArtifact)]
        assert len(artifacts) == 1


# ---------------------------------------------------------------------------
# Job: notification
# ---------------------------------------------------------------------------

class TestRunNotification:
    def test_also_notify_produces_notification(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(), also_notify=True)
        outputs = run(ctx)
        notifications = [o for o in outputs if isinstance(o, Notification)]
        assert len(notifications) == 1

    def test_notification_subject_includes_count(self, tmp_path: Path):
        ctx = _make_ctx(
            tmp_path, worker=_mock_worker(),
            topics=[ResearchTopic(name="topic-a"), ResearchTopic(name="topic-b")], also_notify=True,
        )
        outputs = run(ctx)
        notif = next(o for o in outputs if isinstance(o, Notification))
        assert "2" in notif.subject

    def test_notification_body_lists_topics(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(), also_notify=True)
        outputs = run(ctx)
        notif = next(o for o in outputs if isinstance(o, Notification))
        assert "agentic coding" in notif.body

    def test_no_notification_when_also_notify_false(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(), also_notify=False)
        outputs = run(ctx)
        assert not any(isinstance(o, Notification) for o in outputs)

    def test_no_notification_when_all_topics_fail(self, tmp_path: Path):
        ctx = _make_ctx(
            tmp_path, worker=_mock_worker(returncode=1),
            also_notify=True,
        )
        outputs = run(ctx)
        assert not any(isinstance(o, Notification) for o in outputs)


# ---------------------------------------------------------------------------
# Job: no worker / no topics
# ---------------------------------------------------------------------------

class TestRunEdgeCases:
    def test_no_worker_returns_empty(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=None)
        outputs = run(ctx)
        assert outputs == []

    def test_no_topics_returns_empty(self, tmp_path: Path):
        ctx = _make_ctx(tmp_path, worker=_mock_worker(), topics=[])
        outputs = run(ctx)
        assert outputs == []


# ---------------------------------------------------------------------------
# _build_prompt: structured topic fields
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def _prompt(self, **kwargs) -> str:
        topic = ResearchTopic(**kwargs)
        return _build_prompt(topic, lookback_days=7, today_str="2026-03-08", since_str="2026-03-01")

    def test_name_only_contains_topic_name(self):
        p = self._prompt(name="agentic coding")
        assert "Topic: agentic coding" in p

    def test_name_only_no_focus_line(self):
        p = self._prompt(name="agentic coding")
        assert "Focus:" not in p

    def test_name_only_no_sources_line(self):
        p = self._prompt(name="agentic coding")
        assert "Prioritise" not in p

    def test_description_appears_in_prompt(self):
        p = self._prompt(name="Rust", description="focus on async and tokio")
        assert "Focus: focus on async and tokio" in p

    def test_sources_appear_in_prompt(self):
        p = self._prompt(name="ML", sources=["arxiv.org", "distill.pub"])
        assert "Prioritise these sources: arxiv.org, distill.pub" in p

    def test_all_fields_present(self):
        p = self._prompt(name="ML", description="interpretability", sources=["arxiv.org"])
        assert "Topic: ML" in p
        assert "Focus: interpretability" in p
        assert "Prioritise these sources: arxiv.org" in p

    def test_heading_uses_topic_name(self):
        p = self._prompt(name="agentic coding")
        assert "# Weekly Research Digest: agentic coding" in p


# ---------------------------------------------------------------------------
# Config parsing: ResearchTopic
# ---------------------------------------------------------------------------

class TestResearchTopicParsing:
    def _parse(self, topics_yaml):
        from obsidian_agent.config import _parse_research_digest
        return _parse_research_digest({"topics": topics_yaml}).topics

    def test_plain_string_becomes_research_topic(self):
        topics = self._parse(["agentic coding"])
        assert topics == [ResearchTopic(name="agentic coding")]

    def test_structured_name_only(self):
        topics = self._parse([{"name": "Rust"}])
        assert topics == [ResearchTopic(name="Rust")]

    def test_structured_with_description(self):
        topics = self._parse([{"name": "Rust", "description": "async patterns"}])
        assert topics[0].description == "async patterns"

    def test_structured_with_sources(self):
        topics = self._parse([{"name": "ML", "sources": ["arxiv.org", "distill.pub"]}])
        assert topics[0].sources == ["arxiv.org", "distill.pub"]

    def test_mixed_list(self):
        topics = self._parse(["plain", {"name": "structured", "description": "desc"}])
        assert topics[0] == ResearchTopic(name="plain")
        assert topics[1].name == "structured"
        assert topics[1].description == "desc"

    def test_slug_uses_topic_name(self):
        topic = ResearchTopic(name="Large Language Models")
        assert _topic_slug(topic) == "large-language-models"
