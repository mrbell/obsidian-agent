from pathlib import Path

import pytest

from obsidian_agent.outputs import Notification, VaultArtifact


class TestVaultArtifactWriteToOutbox:
    def test_file_created_at_expected_path(self, tmp_path: Path) -> None:
        artifact = VaultArtifact(
            job_name="task_notification",
            filename="2026-03-07_tasks.md",
            content="# Tasks\n",
        )
        dest = artifact.write_to_outbox(tmp_path)
        assert dest == tmp_path / "task_notification" / "2026-03-07_tasks.md"
        assert dest.exists()

    def test_file_content_correct(self, tmp_path: Path) -> None:
        content = "# My Report\n\nSome content here.\n"
        artifact = VaultArtifact(job_name="job", filename="report.md", content=content)
        dest = artifact.write_to_outbox(tmp_path)
        assert dest.read_text(encoding="utf-8") == content

    def test_outbox_subdirectory_created(self, tmp_path: Path) -> None:
        artifact = VaultArtifact(job_name="new_job", filename="out.md", content="x")
        artifact.write_to_outbox(tmp_path)
        assert (tmp_path / "new_job").is_dir()

    def test_returns_destination_path(self, tmp_path: Path) -> None:
        artifact = VaultArtifact(job_name="job", filename="f.md", content="")
        result = artifact.write_to_outbox(tmp_path)
        assert isinstance(result, Path)
        assert result.is_file()
        assert result == tmp_path / "job" / "f.md"

    def test_no_tmp_file_left_behind(self, tmp_path: Path) -> None:
        artifact = VaultArtifact(job_name="job", filename="f.md", content="data")
        artifact.write_to_outbox(tmp_path)
        tmp_files = list((tmp_path / "job").glob("*.tmp"))
        assert tmp_files == []

    def test_dotdot_in_filename_raises(self, tmp_path: Path) -> None:
        artifact = VaultArtifact(job_name="job", filename="../escape.md", content="x")
        with pytest.raises(ValueError, match=r"\.\."):
            artifact.write_to_outbox(tmp_path)

    def test_absolute_filename_raises(self, tmp_path: Path) -> None:
        artifact = VaultArtifact(job_name="job", filename="/etc/passwd", content="x")
        with pytest.raises(ValueError, match="absolute"):
            artifact.write_to_outbox(tmp_path)

    def test_overwrite_existing_file(self, tmp_path: Path) -> None:
        artifact1 = VaultArtifact(job_name="job", filename="f.md", content="v1")
        artifact2 = VaultArtifact(job_name="job", filename="f.md", content="v2")
        artifact1.write_to_outbox(tmp_path)
        artifact2.write_to_outbox(tmp_path)
        assert (tmp_path / "job" / "f.md").read_text() == "v2"

    def test_destination_writes_to_destinations_staging_area(self, tmp_path: Path) -> None:
        artifact = VaultArtifact(
            job_name="readwise_ingestion",
            filename="article.md",
            content="# Note\n",
            destination="Readwise",
        )
        dest = artifact.write_to_outbox(tmp_path)
        assert dest == tmp_path / "__destinations__" / "Readwise" / "article.md"

    def test_dotdot_in_destination_raises(self, tmp_path: Path) -> None:
        artifact = VaultArtifact(
            job_name="readwise_ingestion",
            filename="article.md",
            content="# Note\n",
            destination="../escape",
        )
        with pytest.raises(ValueError, match=r"\.\."):
            artifact.write_to_outbox(tmp_path)

    def test_absolute_destination_raises(self, tmp_path: Path) -> None:
        artifact = VaultArtifact(
            job_name="readwise_ingestion",
            filename="article.md",
            content="# Note\n",
            destination="/Readwise",
        )
        with pytest.raises(ValueError, match="absolute"):
            artifact.write_to_outbox(tmp_path)


class TestNotification:
    def test_fields(self) -> None:
        n = Notification(subject="Hello", body="World")
        assert n.subject == "Hello"
        assert n.body == "World"

    def test_frozen(self) -> None:
        n = Notification(subject="Hello", body="World")
        with pytest.raises(Exception):
            n.subject = "Changed"  # type: ignore[misc]
