from __future__ import annotations

from pathlib import Path

from obsidian_agent.config import (
    Config, PathsConfig, CacheConfig, DeliveryConfig, JobsConfig,
    IndexingConfig,
)
from obsidian_agent.cron import (
    _BEGIN, _END,
    remove_managed_section,
    build_managed_section,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(tmp_path: Path) -> Config:
    vault = tmp_path / "vault"
    vault.mkdir()
    state = tmp_path / "state"

    from obsidian_agent.config import (
        TaskNotificationConfig, ResearchDigestConfig,
        VaultConnectionsReportConfig, VaultHygieneReportConfig,
    )

    return Config(
        paths=PathsConfig(
            vault=vault,
            outbox=tmp_path / "outbox",
            state_dir=state,
            bot_inbox_rel="BotInbox",
        ),
        cache=CacheConfig(
            duckdb_path=tmp_path / "index.duckdb"
        ),
        delivery=DeliveryConfig(),
        agent=None,
        jobs=JobsConfig(
            task_notification=TaskNotificationConfig(enabled=True, schedule="0 7 * * *"),
            research_digest=ResearchDigestConfig(enabled=True, schedule="0 18 * * 0"),
            vault_connections_report=VaultConnectionsReportConfig(enabled=True, schedule="0 9 * * 1"),
            vault_hygiene_report=VaultHygieneReportConfig(enabled=True, schedule="0 10 1,15 * *"),
        ),
        indexing=IndexingConfig(
            schedule="0 3 * * *",
            semantic_schedule="5 3 * * *",
        ),
    )


FAKE_BINARY = Path("/usr/local/bin/obsidian-agent")
FAKE_CONFIG = Path("/home/user/.config/obsidian-agent/config.yaml")


# ---------------------------------------------------------------------------
# remove_managed_section
# ---------------------------------------------------------------------------

class TestRemoveManagedSection:
    def test_removes_section(self):
        crontab = f"0 1 * * * something\n{_BEGIN}\n0 3 * * * obsidian-agent\n{_END}\n0 5 * * * other\n"
        result = remove_managed_section(crontab)
        assert "obsidian-agent" not in result
        assert "0 1 * * * something" in result
        assert "0 5 * * * other" in result

    def test_no_section_is_noop(self):
        crontab = "0 1 * * * something\n0 5 * * * other\n"
        result = remove_managed_section(crontab)
        assert result == crontab

    def test_empty_crontab(self):
        assert remove_managed_section("") == ""

    def test_idempotent(self):
        crontab = f"existing line\n{_BEGIN}\nmanaged entry\n{_END}\n"
        once = remove_managed_section(crontab)
        twice = remove_managed_section(once)
        assert once == twice

    def test_preserves_lines_outside_section(self):
        crontab = f"before\n{_BEGIN}\ninside\n{_END}\nafter\n"
        result = remove_managed_section(crontab)
        assert "before" in result
        assert "after" in result
        assert "inside" not in result


# ---------------------------------------------------------------------------
# build_managed_section
# ---------------------------------------------------------------------------

class TestBuildManagedSection:
    def test_contains_begin_and_end_markers(self, tmp_path: Path):
        cfg = _make_config(tmp_path)
        section = build_managed_section(cfg, FAKE_CONFIG, FAKE_BINARY)
        assert _BEGIN in section
        assert _END in section

    def test_contains_index_entry(self, tmp_path: Path):
        cfg = _make_config(tmp_path)
        section = build_managed_section(cfg, FAKE_CONFIG, FAKE_BINARY)
        assert "0 3 * * *" in section
        assert "index-semantic" not in section.split("0 3 * * *")[1].split("\n")[0]
        # index (not index-semantic) at 03:00
        assert "obsidian-agent index " in section or "obsidian-agent index\n" in section

    def test_contains_semantic_index_entry(self, tmp_path: Path):
        cfg = _make_config(tmp_path)
        section = build_managed_section(cfg, FAKE_CONFIG, FAKE_BINARY)
        assert "5 3 * * *" in section
        assert "index-semantic" in section

    def test_contains_all_enabled_jobs(self, tmp_path: Path):
        cfg = _make_config(tmp_path)
        section = build_managed_section(cfg, FAKE_CONFIG, FAKE_BINARY)
        assert "task_notification" in section
        assert "research_digest" in section
        assert "vault_connections_report" in section
        assert "vault_hygiene_report" in section

    def test_job_entry_chains_index(self, tmp_path: Path):
        cfg = _make_config(tmp_path)
        section = build_managed_section(cfg, FAKE_CONFIG, FAKE_BINARY)
        # Each job line should have 'index ... && ... run <job>'
        for line in section.splitlines():
            if "run task_notification" in line:
                assert "index" in line
                assert "&&" in line

    def test_disabled_job_excluded(self, tmp_path: Path):
        from obsidian_agent.config import ResearchDigestConfig
        cfg = _make_config(tmp_path)
        # Rebuild with research_digest disabled
        jobs = cfg.jobs
        import dataclasses
        cfg2 = dataclasses.replace(
            cfg,
            jobs=dataclasses.replace(
                jobs,
                research_digest=ResearchDigestConfig(enabled=False),
            ),
        )
        section = build_managed_section(cfg2, FAKE_CONFIG, FAKE_BINARY)
        assert "research_digest" not in section

    def test_uses_config_path_flag(self, tmp_path: Path):
        cfg = _make_config(tmp_path)
        section = build_managed_section(cfg, FAKE_CONFIG, FAKE_BINARY)
        assert str(FAKE_CONFIG) in section

    def test_uses_binary_path(self, tmp_path: Path):
        cfg = _make_config(tmp_path)
        section = build_managed_section(cfg, FAKE_CONFIG, FAKE_BINARY)
        assert str(FAKE_BINARY) in section

    def test_logs_to_state_dir(self, tmp_path: Path):
        cfg = _make_config(tmp_path)
        section = build_managed_section(cfg, FAKE_CONFIG, FAKE_BINARY)
        assert str(cfg.paths.state_dir) in section
        assert ".log" in section


# ---------------------------------------------------------------------------
# Round-trip: remove then rebuild
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_remove_then_rebuild_is_stable(self, tmp_path: Path):
        cfg = _make_config(tmp_path)
        section = build_managed_section(cfg, FAKE_CONFIG, FAKE_BINARY)
        existing = f"0 1 * * * my-other-job\n\n{section}"

        cleaned = remove_managed_section(existing)
        rebuilt = (cleaned.rstrip() + "\n\n" + section)

        # The managed section content should be identical
        assert section in rebuilt
        # The unrelated entry should be preserved
        assert "my-other-job" in rebuilt
