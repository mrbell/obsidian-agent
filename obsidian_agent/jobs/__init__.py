# Import all job modules here to trigger self-registration via @register.
# Any new job module must be added to this list.
from obsidian_agent.jobs import task_notification as task_notification  # noqa: F401
from obsidian_agent.jobs import research_digest as research_digest  # noqa: F401
from obsidian_agent.jobs import vault_connections_report as vault_connections_report  # noqa: F401
from obsidian_agent.jobs import vault_hygiene_report as vault_hygiene_report  # noqa: F401
