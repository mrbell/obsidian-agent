import pytest

# Importing jobs triggers __init__.py which registers all jobs
import obsidian_agent.jobs  # noqa: F401
from obsidian_agent.jobs.registry import get_job, list_jobs


class TestGetJob:
    def test_task_notification_registered(self) -> None:
        job = get_job("task_notification")
        assert callable(job)

    def test_unknown_job_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="nonexistent"):
            get_job("nonexistent")

    def test_error_message_lists_available_jobs(self) -> None:
        with pytest.raises(KeyError, match="task_notification"):
            get_job("nonexistent")

    def test_returns_same_function_as_registered(self) -> None:
        from obsidian_agent.jobs.task_notification import run
        assert get_job("task_notification") is run


class TestListJobs:
    def test_returns_list(self) -> None:
        assert isinstance(list_jobs(), list)

    def test_contains_task_notification(self) -> None:
        assert "task_notification" in list_jobs()

    def test_sorted(self) -> None:
        jobs = list_jobs()
        assert jobs == sorted(jobs)
