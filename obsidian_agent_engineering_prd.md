
# Obsidian Agent — Engineering PRD (Agent-Oriented Version)

This document is designed to seed development by an autonomous coding agent
(e.g., Codex, Claude Code). It provides explicit architectural guidance,
module structure, contracts, and implementation priorities.

---

# 1. Product Vision

Obsidian Agent is a **local automation framework** that runs scheduled
analysis and synthesis jobs over a user's Obsidian vault.

The system:

- Reads the vault **safely** (read‑only)
- Builds a **structured index** of the vault
- Runs automated **agent jobs**
- Writes results to a **staging outbox**
- Promotes results into the vault via a **safe promoter tool**

The system must **never allow agents to modify existing vault notes.**

All automation outputs must be **additive only.**

---

# 2. Core Design Principles

## Immutable Vault

Agents treat the vault as **read‑only**.

They must not modify files directly.

All vault access occurs through:

```
vault_ro/
```

which is a read‑only filesystem mount.

---

## Staging + Promotion Pattern

Agent outputs are written to:

```
outbox/
```

A separate **promoter process** copies validated outputs into:

```
Vault/BotInbox/YYYY/MM/
```

The promoter enforces:

- allowed extensions
- no overwrite
- safe path validation

---

## Local‑First

The system operates entirely locally.

It must work without:

- cloud services
- external APIs
- internet connectivity (except optional research jobs)

---

## Agent Integration

The system must integrate with **existing coding agent CLIs**.

Examples:

- Codex
- Claude Code

The system **does not call LLM APIs directly**.

Instead it executes an external CLI in headless mode.

---

# 3. System Architecture

```
                    +-------------------+
                    |   Obsidian Vault |
                    |  ~/ObsidianVault |
                    +---------+--------+
                              |
                              | read‑only mount
                              v
                       /mnt/vault_ro
                              |
                              v
                     +----------------+
                     | Index Builder  |
                     | (DuckDB)       |
                     +--------+-------+
                              |
                              v
                     +----------------+
                     | Agent Jobs     |
                     +--------+-------+
                              |
                              | write
                              v
                        ~/agent_outbox
                              |
                              v
                      +----------------+
                      | Promoter Tool  |
                      +--------+-------+
                               |
                               v
           ~/ObsidianVault/BotInbox/YYYY/MM/
```

---

# 4. Directory Layout

The repository should be structured as:

```
obsidian-agent/

    pyproject.toml

    config/
        config.yaml

    obsidian_agent/

        cli.py

        config.py

        logging.py

        context.py

        runner.py

        artifacts.py

        vault/
            reader.py
            parser.py

        index/
            build_index.py
            schema.sql
            store.py

        jobs/
            registry.py
            task_digest.py
            weekly_thought_starters.py

        promote/
            promoter.py

    tests/

    scripts/
```

---

# 5. CLI Interface

The system exposes a CLI command:

```
obsidian-agent
```

### Build Index

```
obsidian-agent index
```

Scans vault_ro and updates DuckDB index.

---

### Run Job

```
obsidian-agent run job <job_name>
```

Executes a job and writes results to outbox.

---

### Promote Artifacts

```
obsidian-agent promote
```

Moves new artifacts into BotInbox safely.

---

### Test Agent Runner

```
obsidian-agent runner test
```

Verifies configured headless agent CLI works.

---

# 6. Configuration

Example `config.yaml`

```
paths:
  vault_readonly: /mnt/vault_ro
  vault_real: ~/ObsidianVault
  outbox: ~/agent_outbox
  state_dir: ~/.obsidian-agent

cache:
  duckdb_path: ~/.obsidian-agent/index.duckdb

runner:
  command: codex
  args: ["run", "--non-interactive"]
  timeout_seconds: 900
```

---

# 7. DuckDB Data Model

The index is stored in DuckDB.

Tables:

### notes

```
note_relpath TEXT PRIMARY KEY
title TEXT
mtime_ns BIGINT
size_bytes BIGINT
content_hash TEXT
word_count INT
```

### tasks

```
note_relpath TEXT
line_no INT
checked BOOLEAN
text TEXT
```

### links

```
note_relpath TEXT
target TEXT
kind TEXT
```

### tags

```
note_relpath TEXT
tag TEXT
```

### headings

```
note_relpath TEXT
heading TEXT
```

---

# 8. Job Interface

All jobs must implement:

```
def run(context: JobContext) -> list[OutboxArtifact]
```

Where:

```
JobContext
```

contains:

- config
- duckdb store
- vault_ro path
- logger

Jobs must:

1. Read vault or index
2. Optionally call agent runner
3. Produce artifacts
4. Write artifacts to outbox

Jobs must **never write directly to the vault.**

---

# 9. Artifact Format

Artifacts represent files written to outbox.

Example:

```
OutboxArtifact(
    relpath="task_digest/2026-03-05.md",
    content="<markdown>"
)
```

Artifacts are written atomically.

---

# 10. Headless Agent Runner

The runner executes external agent CLIs.

Contract:

- prompt passed via stdin
- process must run autonomously
- must exit with return code

Interface:

```
Runner.run(prompt:str) -> RunnerResult
```

RunnerResult:

```
returncode
stdout
stderr
```

---

# 11. Promoter Safety Model

The promoter enforces strict rules:

Allowed:

- `.md` files only

Forbidden:

- overwrite existing files
- symlinks
- paths escaping BotInbox

Destination format:

```
BotInbox/YYYY/MM/<job>/<artifact>.md
```

---

# 12. Initial Jobs

## Task Digest

Find open tasks and produce a daily summary.

---

## Weekly Thought Starters

Generate prompts connecting distant tags.

---

# 13. Future Jobs

### Research Harvester

Collect RSS feeds and summarize papers.

### Idea Incubator

Detect orphan ideas and generate project proposals.

### Stale Thread Detector

Find abandoned notes.

### Knowledge Graph Builder

Cluster notes into topics.

---

# 14. Development Milestones

### Phase 1

Implement:

- CLI
- index builder
- DuckDB schema
- task digest job
- promoter

### Phase 2

Add:

- agent runner integration
- thought starter job

### Phase 3

Add:

- research ingestion
- topic clustering
- embeddings

---

# 15. Observability

Logs stored in:

```
state/logs/
```

Include:

- job runs
- promotion actions
- runner output

---

# 16. Safety Guarantees

The architecture must ensure:

1. Agents cannot modify vault files.
2. Promotion cannot overwrite files.
3. Writes are limited to BotInbox.
4. All writes are additive.

---

# 17. Guiding Philosophy

The system prioritizes:

- **vault safety**
- **local control**
- **simple primitives**
- **extensibility**

Automation should enhance the knowledge system
without introducing fragility.
