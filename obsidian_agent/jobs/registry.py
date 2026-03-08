from __future__ import annotations

from collections.abc import Callable

from obsidian_agent.context import JobContext
from obsidian_agent.outputs import JobOutput

JobFn = Callable[[JobContext], list[JobOutput]]

_REGISTRY: dict[str, JobFn] = {}


def register(name: str) -> Callable[[JobFn], JobFn]:
    """Decorator that registers a job function under the given name."""
    def decorator(fn: JobFn) -> JobFn:
        _REGISTRY[name] = fn
        return fn
    return decorator


def get_job(name: str) -> JobFn:
    """Return the job function registered under *name*.

    Raises KeyError with a helpful message if the name is unknown.
    """
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY)) or "(none registered)"
        raise KeyError(f"Unknown job: {name!r}. Available: {available}")
    return _REGISTRY[name]


def list_jobs() -> list[str]:
    """Return a sorted list of all registered job names."""
    return sorted(_REGISTRY.keys())
