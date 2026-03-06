
# Obsidian Agent — Product Requirements Document (PRD)

## 1. Overview

**Obsidian Agent** is a local automation framework designed to run scheduled “agent jobs” over a user's Obsidian vault.  
The goal is to augment a personal knowledge base with automated analysis, summarization, and idea generation while **preserving strict safety guarantees** that prevent accidental modification or corruption of the vault.

The system enables:

- Scheduled analysis of vault content
- Automated research ingestion and summarization
- Idea discovery and “thought prompts” from note relationships
- Task reminders and summaries
- Long‑term structure inference (graphs, topic clusters, etc.)

The system is designed for **local-first operation** and integrates with **existing coding agents (Codex, Claude Code, etc.) running headlessly**, rather than directly calling LLM APIs.

---

# 2. Goals

## Primary Goals

1. **Safe automation over an Obsidian vault**
   - Prevent agents from modifying or deleting vault content.
   - Ensure that all automation outputs are additive.

2. **Scheduled agent workflows**
   - Run jobs via cron/systemd/launchd.
   - Jobs should run autonomously without user interaction.

3. **Agent‑assisted knowledge synthesis**
   - Automatically generate summaries, insights, and prompts based on vault content.

4. **Extensible architecture**
   - Make it easy to add new jobs.
   - Support multiple agent CLIs.

5. **Local-first operation**
   - No requirement to use external APIs.
   - Work entirely with local tools and files.

---

# 3. Non‑Goals

- Replacing Obsidian as a note editor
- Editing existing notes automatically
- Providing a web interface
- Cloud-based operation
- Full knowledge graph visualization (initial version)

---

# 4. Core Design Principles

## Safety First

The Obsidian vault is considered **immutable from the perspective of the agent**.

Agents:

- **MAY read** the vault
- **MUST NOT write** to the vault

Writes are only performed by a **separate promoter process**.

## Deterministic Writes

All agent outputs must first be written to a staging directory.

A simple promotion script:

- Validates files
- Copies them into the vault
- Prevents overwriting existing notes

## Local Execution

The system should run locally using:

- filesystem access
- local CLI agents
- local scheduling tools

No web services are required.

---

# 5. Architecture Overview

                +------------------------+
                |   Obsidian Vault       |
                | ~/ObsidianVault        |
                +-----------+------------+
                            |
                            | read-only mount
                            v
                   /mnt/vault_ro
                            |
                            v
               +------------------------+
               |   Obsidian Agent Jobs  |
               |   (read only)          |
               +-----------+------------+
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

---

# 6. Core Components

## Vault Reader

Responsible for reading and parsing markdown notes.

Extracts:

- tasks (`- [ ]`)
- tags (`#tag`)
- wikilinks (`[[link]]`)
- headings
- metadata

Outputs structured representations for indexing.

---

## Index Builder

Creates a cached structured representation of the vault using DuckDB.

Stored data includes:

- notes
- tasks
- tags
- links
- headings
- file metadata

The index is refreshed periodically.

Purpose:

- enable fast queries
- support graph inference
- support jobs without re-scanning vault

---

## Job Runner

Executes scheduled tasks.

Jobs read from:

- vault readonly mount
- DuckDB index

Jobs write only to:

outbox/

Each job produces artifacts such as:

- markdown notes
- research summaries
- task digests

---

## Headless Agent Runner

Allows jobs to invoke external coding agents such as:

- Codex
- Claude Code
- other CLI tools

The runner:

- pipes prompts via stdin
- captures stdout/stderr
- enforces timeouts
- requires non‑interactive mode

---

## Outbox (Staging Area)

All job outputs are written here.

Example:

outbox/
    task_digest/
        2026-03-05_task-digest.md

Properties:

- outside the vault
- safe to overwrite
- staging for promotion

---

## Promoter

Responsible for copying artifacts into the vault.

Safety guarantees:

- only `.md` files allowed
- no overwrite
- only writes inside `BotInbox`
- rejects symlinks

Destination format:

BotInbox/YYYY/MM/<job>/<file>.md

---

# 7. Scheduling

Jobs are designed to run via system schedulers.

Example schedule:

| Job | Frequency |
|----|----|
| index builder | daily |
| task digest | daily |
| research summary | daily |
| thought starters | weekly |

---

# 8. Initial Jobs

## Task Digest

Scans index for open tasks and produces a daily summary.

---

## Weekly Thought Starters

Identifies distant tags and generates prompts connecting ideas.

---

# 9. Future Jobs

Potential additional jobs:

- Research Harvester
- Idea Incubator
- Stale Thread Detector
- Knowledge Graph Builder

---

# 10. Data Model (DuckDB)

Example tables:

notes  
tasks  
links  
tags  
headings  

Future tables may include:

topics  
clusters  
embeddings  

---

# 11. Security Model

Agent processes have:

read: vault_ro  
write: outbox  

Vault writes only occur via promoter.

---

# 12. Configuration Example

paths:
  vault_readonly: /mnt/vault_ro
  vault_real: ~/ObsidianVault
  outbox: ~/agent_outbox

runner:
  command: codex
  args: ["run","--non-interactive"]

---

# 13. Extensibility

New jobs should:

1. Query the index
2. Optionally invoke agent CLI
3. Write artifacts to outbox

Jobs should **never write directly to the vault**.

---

# 14. Development Philosophy

The system should remain:

- simple
- local
- observable
- safe

Automation should enhance thinking without risking the integrity of the knowledge base.
