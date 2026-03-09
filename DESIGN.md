# Obsidian Agent — Design Document

This document supersedes `obsidian_agent_prd.md`, `obsidian_agent_engineering_prd.md`, and
`obsidian_agent_ARCHITECTURE.md`. Those files can be deleted.

---

## 1. Vision

Obsidian Agent is a scheduled automation framework that runs jobs over a personal Obsidian vault.

Jobs fall into three categories:

- **Notification jobs** — extract structured information from the vault and push it to external
  channels (email, SMS) that the user actually checks daily.
- **Synthesis jobs** — use an LLM to generate new content from vault material and deposit it as
  new notes in a designated inbox folder inside the vault.
- **Research jobs** — use an LLM agent with web access to gather external information, synthesize
  it (optionally with vault context), and deposit reports in the vault inbox.

The system is designed for a single user running it locally. It is not a web service.

---

## 2. Core Principles

### Vault integrity
The vault is read-only to all jobs and agent workers. The only component permitted to write into
the vault is the promoter, and it can only create new files in a designated inbox directory. No
existing vault file is ever modified or deleted by this system.

### Additive-only output
All automation outputs are new files. The system never edits, moves, or deletes content the user
has created. Organization suggestions are delivered as suggestion notes, not applied automatically.

### Flexible output model
Jobs are not required to produce vault notes. A job may produce:
- A `VaultArtifact` (a markdown file staged for promotion into the vault)
- A `Notification` (a message delivered to an external channel such as email)
- Both

### Claude Code as the LLM worker
Rather than calling the Anthropic API directly, LLM-assisted jobs invoke Claude Code headlessly.
This leverages an existing subscription rather than incurring separate API token costs. Claude
Code's built-in tools (web search, URL fetching) are used intentionally for research jobs.

Claude Code accesses vault content exclusively through a **read-only MCP server** provided by
this system. It is never given direct filesystem access to the vault. This is both a safety
boundary and an architectural benefit: Claude Code can navigate and retrieve vault content
naturally using MCP tools, without the orchestrator having to predict and pre-fetch the right
context.

### Internet-aware
Some jobs (research digest) require internet access by design. Jobs are categorized by whether
they require internet access so users understand what they are enabling.

### Privacy-conscious
Vault content is accessed through a locally-running MCP server. No vault content is transmitted
to third-party services except as part of a Claude Code invocation, subject to Anthropic's
privacy terms. Research jobs may fetch external content.

---

## 3. Architecture Overview

```
 Obsidian Vault (read-only to this system)
        |
        | read
        v
 +------------------+        +------------------+
 |   Vault Reader   |------->|  Index Builder   |
 |   (parser)       |        |  (DuckDB)        |
 +------------------+        +--------+---------+
        |                             |
        +-------------+---------------+
                      |
                      v
             +------------------+
             |   MCP Server     |  <-- read-only vault tools
             |   (local stdio)  |      exposed to Claude Code
             +--------+---------+
                      |
              +-------+-------+
              |               |
              | (MCP tools)   | (web tools)
              v               v
         +----------------------------+
         |     Claude Code Worker     |  (LLM-assisted jobs only)
         |     (headless, isolated)   |
         +-------------+--------------+
                       |
                       | writes output to working dir
                       v
              +---------------+
              |  Job Runner   |  reads output, creates JobOutputs
              +-------+-------+
                      |
           +----------+----------+
           |                     |
           v                     v
   +---------------+     +-------------------+
   | VaultArtifact |     |   Notification    |
   |  (outbox/)    |     |  (email / SMS)    |
   +-------+-------+     +-------------------+
           |
           v
      +----------+
      | Promoter |
      +----+-----+
           |
           v
  Vault/BotInbox/<job>/
```

For deterministic (no-LLM) jobs, the Claude Code Worker and MCP Server are not involved. The
job runner queries the index directly and produces outputs.

---

## 4. Components

### Vault Reader (`vault/reader.py`, `vault/parser.py`)

Walks the vault directory and parses markdown files. Extracts:
- Note title (first H1, or filename if none)
- Frontmatter (YAML block)
- Headings (with level)
- Tasks (with line number, completion state, and due date if present)
- Wikilinks and markdown links
- Tags (inline `#tag` and frontmatter `tags:`)
- Word count
- Whether the note is a daily note (filename matches `YYYY-MM-DD.md`)

Task due date format: Tasks plugin emoji syntax — `- [ ] Description 📅 2026-03-10`.

The vault directory is opened read-only. No write operations are performed here.

### Index Builder (`index/build_index.py`, `index/store.py`)

Builds and maintains a DuckDB database of vault metadata. Supports incremental updates using
`mtime_ns` + `size_bytes` as a fast change check, with SHA-256 hash as a secondary check.

The index is a fast filter and lookup layer. The MCP server exposes both the index (for
structured queries) and raw note content (read from disk on demand) to Claude Code.

See **Section 7 — Indexing Strategy** for the full scan algorithm and change handling details.

### MCP Server (`mcp/server.py`)

A local MCP server that exposes the vault and index to Claude Code through a set of read-only
tools. Runs as a stdio subprocess launched by the Claude Code worker for each job invocation.

**Exposed tools**:

| Tool | Description |
|---|---|
| `search_notes(query, limit)` | Full-text search across all notes. Returns paths and excerpts. |
| `get_note(path)` | Get the full content of a note by relative path. |
| `list_notes(folder, include_daily)` | List notes, optionally filtered by folder. |
| `get_daily_notes(start_date, end_date)` | Get daily notes in a date range with content. |
| `query_tasks(status, due_before)` | Query tasks from the index. |
| `get_note_links(path)` | Get outgoing and incoming links for a note. |
| `find_notes_by_tag(tag)` | Find all notes with a given tag. |
| `get_vault_stats()` | Note count, task count, last indexed timestamp, etc. |

**Safety properties**:
- No write tools are exposed. The MCP protocol boundary enforces read-only access.
- The server reads from the vault path and DuckDB index configured at startup.
- Claude Code using this server has no need to access the vault via its own filesystem tools.

This is the primary interface between Claude Code and the vault. It replaces the pattern of
the orchestrator pre-fetching and injecting context into prompts. Claude Code retrieves what
it needs, when it needs it, using these tools.

### Job Runner (`runner.py`, `jobs/`)

Loads and executes jobs by name. Each job receives a `JobContext` and returns a list of
`JobOutput` items (`VaultArtifact` or `Notification`).

Deterministic jobs interact with the index and vault reader directly.
LLM-assisted jobs write a prompt and delegate to the Claude Code worker.

### Claude Code Worker (`agent/worker.py`)

Invokes Claude Code headlessly for LLM-assisted jobs.

- Runs Claude Code with `-p` / `--print` for non-interactive output.
- Registers the vault MCP server via `--mcp-config <path-to-json>`.
- Claude Code runs in an isolated temporary working directory.
- Captures Claude Code's stdout (plain text by default).
- Enforces a configurable timeout.
- Returns raw output text for the job to validate and wrap as a `VaultArtifact`.

Claude Code is given a task description. It uses MCP tools to retrieve whatever vault context
it determines is relevant, and web tools (if enabled) for research tasks. The worker does not
need to predict or pre-fetch context.

**Confirmed invocation flags** (validated in spike 4-4):

```
claude -p "<prompt>" \
  --mcp-config /tmp/<uuid>-mcp.json \
  --output-format json \
  --no-session-persistence
```

Use `--output-format json` (not `text`) so the worker can parse the structured result:
the JSON object contains `result` (the text), `is_error` (boolean), and `stop_reason`.
This allows reliable error detection without guessing from output text.

For Class C (research) jobs, web search (`WebSearch`, `WebFetch`) is available by default
in `--print` mode — no extra flags needed.

**MCP config JSON format** (written to a temp file per invocation):

```json
{
  "mcpServers": {
    "obsidian-vault": {
      "command": "obsidian-agent",
      "args": ["mcp", "--config", "/path/to/config.yaml"]
    }
  }
}
```

**Exit codes**: 0 on success, 1 on error (bad invocation, empty prompt, API error).
Non-zero exit means no usable output — the worker returns a `WorkerResult` with the
returncode and stderr for the job to handle.

**Nested session note**: Claude Code blocks launching inside another Claude Code session
(detects the `CLAUDECODE` env var). In production cron use this is not an issue. In testing,
use a dummy command (`echo`) instead of `claude` to avoid the restriction.

### Delivery (`delivery/`)

Pluggable delivery system for `Notification` outputs.

Initial implementation: SMTP email.

```python
class Delivery(Protocol):
    def send(self, subject: str, body: str) -> None: ...
```

Implementations:
- `SmtpDelivery`: sends via any SMTP server (Gmail, Fastmail, etc.)

### Outbox + Promoter (`promote/promoter.py`)

The outbox is a staging directory outside the vault. Jobs write `VaultArtifact` files here.

The promoter copies files from the outbox into the vault's BotInbox directory, enforcing:
- `.md` files only
- No overwriting existing files
- Destination must be inside `BotInbox/`
- No symlinks
- No path traversal (`..`)

Destination structure:

```
BotInbox/<job>/<artifact-filename>.md
```

---

## 5. Safety Model

**Jobs never write to the vault.** This is enforced by:
1. Jobs only write to the outbox directory, configured to be outside the vault.
2. The `JobContext` does not expose the vault path for writing.
3. The promoter is the only component that holds the vault path for writing.

**Claude Code accesses the vault only through the MCP server.** The MCP server exposes no
write tools. Claude Code's own filesystem tools are not directed at the vault — it has an
MCP interface for vault access and uses that. This makes the read-only constraint structural
rather than prompt-level.

**The promoter is narrow and dumb.** It copies files. It does not parse LLM output, does not
make content decisions, and does not modify content. The less logic it contains, the safer it is.

**No OS-level read-only mount is required.** The safety guarantee comes from code contracts and
component boundaries. This reduces operational complexity significantly.

---

## 6. Data Model (DuckDB)

```sql
CREATE TABLE IF NOT EXISTS notes (
    note_relpath    TEXT PRIMARY KEY,
    title           TEXT,
    is_daily_note   BOOLEAN,
    mtime_ns        BIGINT,
    size_bytes      BIGINT,
    content_sha256  TEXT,
    word_count      INTEGER
);

CREATE TABLE IF NOT EXISTS frontmatter (
    note_relpath    TEXT,
    key             TEXT,
    value           TEXT  -- JSON-encoded to handle lists and scalars uniformly
);

CREATE TABLE IF NOT EXISTS headings (
    note_relpath    TEXT,
    line_no         INTEGER,
    level           INTEGER,  -- 1-6
    heading         TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    note_relpath    TEXT,
    line_no         INTEGER,
    status          TEXT,     -- 'open' | 'done' | 'cancelled' | 'in_progress'
    text            TEXT,
    due_date        DATE      -- NULL if not specified; parsed from 📅 YYYY-MM-DD
);

CREATE TABLE IF NOT EXISTS links (
    note_relpath    TEXT,
    line_no         INTEGER,
    target          TEXT,
    kind            TEXT      -- 'wikilink' | 'markdown'
);

CREATE TABLE IF NOT EXISTS tags (
    note_relpath    TEXT,
    tag             TEXT,
    source          TEXT      -- 'inline' | 'frontmatter'
);
```

Future tables (Milestone 6 — Semantic Vault Intelligence):

```sql
-- Paragraph-level chunks of note content
CREATE TABLE IF NOT EXISTS chunks (
    id              TEXT PRIMARY KEY,   -- "{note_relpath}:{chunk_index}"
    note_relpath    TEXT NOT NULL,
    chunk_index     INTEGER NOT NULL,
    section_header  TEXT,               -- nearest ## heading above this chunk, if any
    text            TEXT NOT NULL,
    token_count     INTEGER,
    embedded_sha256 TEXT,               -- content_sha256 at time of embedding (staleness check)
    embedded_at     TIMESTAMP
);

-- Vector embeddings for chunks (DuckDB VSS extension required)
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id        TEXT PRIMARY KEY,
    embedding       FLOAT[384]          -- all-MiniLM-L6-v2; update dimension if model changes
);

-- Per-note LLM-generated intelligence
CREATE TABLE IF NOT EXISTS note_intelligence (
    note_relpath    TEXT PRIMARY KEY,
    summary         TEXT,               -- 2-4 sentence summary
    extracted_at    TIMESTAMP,
    model_version   TEXT
);

-- Concepts extracted from chunks
CREATE TABLE IF NOT EXISTS concepts (
    id              INTEGER PRIMARY KEY,
    name            TEXT UNIQUE         -- canonical lowercase form
);

-- Concept mentions per chunk
CREATE TABLE IF NOT EXISTS chunk_concepts (
    chunk_id        TEXT NOT NULL,
    concept_id      INTEGER NOT NULL,
    salience        REAL,               -- 0.0–1.0
    PRIMARY KEY (chunk_id, concept_id)
);

-- Named entities extracted from chunks
CREATE TABLE IF NOT EXISTS entities (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL       -- person | project | tool | book | place | other
);

-- Entity mentions per chunk
CREATE TABLE IF NOT EXISTS chunk_entities (
    chunk_id        TEXT NOT NULL,
    entity_id       INTEGER NOT NULL,
    context_snippet TEXT,
    PRIMARY KEY (chunk_id, entity_id)
);

-- Informal ideas, questions, and intentions from prose (not formally tagged)
CREATE TABLE IF NOT EXISTS implicit_items (
    id              INTEGER PRIMARY KEY,
    chunk_id        TEXT NOT NULL,
    note_relpath    TEXT NOT NULL,      -- denormalized
    type            TEXT NOT NULL,      -- idea | question | intention | task
    text            TEXT NOT NULL,
    extracted_at    TIMESTAMP
);
```

---

## 7. Indexing Strategy

### Goals

The index must stay reasonably in sync with the vault so jobs operate on current data. The
vault can change at any time (notes added, edited, deleted, renamed, moved). The index does
not need to be real-time, but should be refreshed before each job run.

### Scheduled full scan

The default strategy is a full scan run before each job via cron. With ~300 notes, a full
scan completes in well under 5 seconds. No background daemon or filesystem watcher is needed.

```
0 7 * * *   obsidian-agent index && obsidian-agent run task_notification
0 18 * * 0  obsidian-agent index && obsidian-agent run research_digest && obsidian-agent promote
```

### Scan algorithm

All operations run inside a single transaction for consistency.

```
1. Walk all .md files in vault_path, collecting seen_paths = set()

2. For each file:
   a. Compute note_relpath (relative to vault root)
   b. Add to seen_paths
   c. Look up existing record in notes table
   d. If mtime_ns and size_bytes are unchanged → skip (no change)
   e. If changed or new → compute content_sha256
   f. If sha256 unchanged → update mtime_ns/size_bytes only; skip re-parse
   g. If sha256 changed or note is new:
      - Delete existing derived rows for this note_relpath
        (tasks, links, tags, headings, frontmatter)
      - Parse file content
      - Insert new derived rows
      - Upsert notes table record
      - Invalidate note_summaries row if present (delete it)

3. Find deleted paths:
   deleted_paths = DB note_relpaths NOT IN seen_paths

4. Rename detection (before deleting):
   For each deleted_path:
     - Check if any newly added path (in seen_paths but not previously in DB)
       has the same content_sha256
     - If match found → treat as rename:
         UPDATE all tables SET note_relpath = new_path WHERE note_relpath = old_path
         Preserve derived data (note_summaries, cluster assignments)
         Remove new_path from the "newly added" set to avoid double-processing
     - If no match → treat as deletion (step 5)

5. Delete records for remaining deleted_paths:
   Remove rows from notes, tasks, links, tags, headings, frontmatter,
   note_summaries, topic_clusters for each deleted path

6. Commit transaction
```

### Handling each change type

**Modified file (including content removed)**
mtime or size change triggers re-parse. All derived rows are delete-and-replaced. Content
that was removed from the file simply does not appear in the new parse and is gone from the
index. The `note_summary` cache row is deleted and will be regenerated on the next
summarization job run.

**Deleted file**
Detected in step 3. All records across all tables for that `note_relpath` are removed.

**Renamed or moved file**
At the filesystem level, a rename is a delete + create with identical content. The hash
comparison in step 4 identifies this case and updates `note_relpath` in place across all
tables, preserving cached derived data (summaries, cluster assignments) that would otherwise
need to be expensively regenerated. If no hash match is found, it is treated as a deletion of
the old note and a new note at the new path.

### Derived data invalidation

| Derived table | Invalidation trigger | Policy |
|---|---|---|
| `chunks` / `chunk_embeddings` | `content_sha256` changes | Delete and replace on next `index-semantic` run (detected via `embedded_sha256` mismatch) |
| `note_intelligence` | Note re-embedded (content changed) | Deleted during `index-semantic` embedding phase; regenerated by intelligence phase |
| `chunk_concepts` / `chunk_entities` / `implicit_items` | Note re-embedded | Deleted and replaced when `note_intelligence` is regenerated |

### Future: filesystem watching

For more responsive index updates (e.g. triggering re-summarization when a note changes),
a background watcher can be added as `obsidian-agent watch` using the `watchdog` library.

Benefits over scheduled scans:
- Near-real-time index updates
- `watchdog` on macOS (FSEvents) and Linux (inotify) provides rename events with both old
  and new paths, making rename detection trivial and reliable
- Enables cache warming (pre-computing summaries for recently changed notes)

This is a future milestone. Scheduled full scans are sufficient for all initial jobs.

---

## 8. Job Taxonomy

### Class A — Deterministic (no LLM)

Operate entirely on index data and/or vault content. No Claude Code involved.

Output: `Notification`, `VaultArtifact`, or both.

Examples:
- `task_notification` — finds tasks with upcoming due dates, sends email
- `stale_task_report` — finds long-dormant open tasks, writes vault note
- `orphan_note_report` — finds notes with no incoming or outgoing links

### Class B — LLM Synthesis

Claude Code is given a task description. It uses MCP tools to retrieve relevant vault content
and produces a new note. No web access required or enabled.

Output: `VaultArtifact` (optionally also `Notification`).

Examples:
- `vault_structure_report` — infers topics, relationships, and patterns across notes
- `idea_connection_report` — identifies conceptually adjacent notes and suggests connections

### Class C — Agentic Research

Claude Code is given a task description with web search enabled. It may use MCP tools for vault
context and web tools to gather external information.

Output: `VaultArtifact` (optionally also `Notification`).

Examples:
- `research_digest` — finds and summarizes recent articles/papers on configured topics

---

## 9. Initial Jobs

### `task_notification` (Class A)

**Purpose**: Each morning, alert the user to tasks with due dates in the next N days.

**Schedule**: Daily (e.g. 07:00)

**Inputs**:
- `tasks` table, filtered to `status = 'open'` and `due_date <= today + lookahead_days`
- Configurable `lookahead_days` (default: 3)
- Configurable `include_overdue` (default: true)

**Output**: `Notification` (email). Optionally also a `VaultArtifact`.

**Email format**:
```
Subject: Task Reminder — N tasks due soon

## Due today
- [ ] Task text (Note: SomeNote.md)

## Due in the next 3 days
- [ ] Task text — due 2026-03-09 (Note: ProjectNote.md)

## Overdue
- [ ] Task text — due 2026-02-28 (Note: OldNote.md)
```

If no tasks are due soon and `notify_if_empty` is false, the job skips sending.

---

### `research_digest` (Class C)

**Purpose**: Weekly, find and summarize recent articles/papers on configured topics.

**Schedule**: Weekly (e.g. Sunday evening)

**Inputs**:
- Configured list of topics in `config.yaml`
- Configured `lookback_days` (default: 7)

**Output**: One `VaultArtifact` per topic. Optionally a summary `Notification`.

**Flow**:
1. For each topic, construct a task prompt (see below).
2. Invoke Claude Code worker with web search enabled and vault MCP server registered.
3. Claude Code searches for recent articles, optionally consults vault notes for context
   on the user's existing interest in the topic, and produces a structured markdown report.
4. Orchestrator validates output is non-empty, valid markdown.
5. Write as `VaultArtifact`.

**Prompt**:
```
You have access to the user's Obsidian vault through MCP tools and can search the web.

Task:
Produce a weekly research digest on the topic: [topic]

Cover only content published or updated in the last [N] days (since [date]).

You may use the vault MCP tools to understand what the user already knows or finds
interesting about this topic — look for relevant notes to inform what is genuinely
new or useful to them.

Required output format (markdown only, no preamble):

# Weekly Research Digest: [topic]
**Period**: [date range]

## Trends
[3-5 sentences on what is happening in this space this week]

## Notable Articles
[For each of the 5-10 most relevant items:]
### [Title]
**Source**: [site]  **Date**: [date]  **URL**: [url]
[2-4 sentence summary. Why it matters to someone interested in this topic.]

## Follow-up Questions
[2-3 questions this week's reading raises]

If fewer than 3 relevant articles are found for the period, say so explicitly rather
than padding with older content.
```

**Failure handling**: If Claude Code exits non-zero, times out, or output is empty or clearly
malformed, log the error and do not write to the outbox. Do not promote partial output.

---

## 10. Future Jobs

### `stale_task_report` (Class A)
Find open tasks where the containing note has not been modified in more than N days. Weekly
report deposited in vault.

### `vault_structure_report` (Class B)
Claude Code uses MCP tools to explore the vault — reading notes, identifying themes, finding
notes that reference similar ideas without being linked. Produces a periodic report on: inferred
topics, interesting clusters, implied tasks or projects, suggested connections. Context window
management is handled by Claude Code navigating the vault iteratively via MCP rather than
receiving a single pre-built dump.

### `idea_connection_report` (Class B)
Identify pairs or groups of notes that share conceptual ground without explicit links. Generate
brief synthesis notes suggesting the connection and a possible direction to explore.

### `project_seeder` (Class B/C + future design)
Identify notes expressing enthusiasm about an idea. Gather related vault context. Produce a
project seed document: fleshed-out description, relevant prior art, a rough PRD. May eventually
kick off a downstream agentic development workflow. Requires separate design before
implementation.

---

## 11. Output Model

```python
@dataclass(frozen=True)
class VaultArtifact:
    job_name: str
    filename: str       # e.g. "2026-03-07_research-digest-agentic-coding.md"
    content: str        # markdown content

@dataclass(frozen=True)
class Notification:
    subject: str
    body: str           # plain text or markdown

JobOutput = VaultArtifact | Notification
```

The job runner writes `VaultArtifact` items to the outbox and passes `Notification` items to
the delivery layer.

---

## 12. Email Delivery

Initial implementation: SMTP.

**Recommended setup for Gmail**:
1. Enable 2-factor authentication on the Google account.
2. Create an app password at `myaccount.google.com/apppasswords`.
3. Configure with `smtp.gmail.com:587`, STARTTLS, username, and the app password.

**Recommended setup for Fastmail** (preferred if switching providers):
1. Create a dedicated sending address (e.g. `obsidian-agent@yourdomain.com`).
2. Generate an app password in Fastmail security settings.
3. Configure with `smtp.fastmail.com:587`.

Fastmail is the better long-term option: dedicated sending address, custom domain, independent
app passwords, no Google dependency.

The SMTP password is read from an environment variable, never stored in the config file.

Future delivery options: webhook (push notification services), SMS via email-to-SMS gateway
(carrier-specific, no third-party service required).

---

## 13. Configuration Schema

```yaml
paths:
  vault: ~/ObsidianVault           # real vault path; read-only to jobs
  outbox: ~/.local/share/obsidian-agent/outbox
  state_dir: ~/.local/share/obsidian-agent
  bot_inbox_rel: BotInbox          # relative path inside vault; must not be absolute

cache:
  duckdb_path: ~/.local/share/obsidian-agent/index.duckdb

delivery:
  email:
    smtp_host: smtp.gmail.com
    smtp_port: 587
    username: you@gmail.com
    password_env: OBSIDIAN_AGENT_SMTP_PASSWORD
    from_address: you@gmail.com
    to_address: you@gmail.com

agent:
  command: claude
  args: ["--print"]
  timeout_seconds: 300
  work_dir: ~/.local/share/obsidian-agent/agent_workdir

jobs:
  task_notification:
    enabled: true
    schedule: "0 7 * * *"
    lookahead_days: 3
    include_overdue: true
    notify_if_empty: false
    also_write_vault_artifact: false

  research_digest:
    enabled: true
    schedule: "0 18 * * 0"        # Sunday 18:00
    lookback_days: 7
    topics:
      - "agentic coding"
      - "large language models"
      - "personal knowledge management"
    also_notify: true
```

**Validation rules**:
- `bot_inbox_rel` must be a relative path (no leading `/`, no `..`)
- `outbox` must not be inside `vault`
- `state_dir` must not be inside `vault`
- `agent.command` required if any Class B or C job is enabled
- SMTP config required if any job produces a `Notification`

---

## 14. CLI Interface

```
obsidian-agent index              # scan vault, update DuckDB structural index
obsidian-agent index-semantic     # update semantic index (embeddings + concept extraction)
obsidian-agent run <job>          # run a named job
obsidian-agent promote            # promote outbox artifacts to vault BotInbox
obsidian-agent status             # index stats, pending outbox items, recent job runs
obsidian-agent agent test         # verify Claude Code is installed and working
obsidian-agent mcp                # start the MCP server (used internally; can also be
                                  # registered in Claude Desktop for manual exploration)
```

`index` and `index-semantic` are intentionally separate commands:
- `index` is fast (<5s), deterministic, no LLM. Run before every job.
- `index-semantic` is slower (LLM calls for changed notes), run on a daily schedule
  independent of per-job cron entries.

`run` and `promote` are intentionally separate steps. They can be chained in a cron entry
when auto-promotion is desired:

```
0 7 * * * obsidian-agent run task_notification
0 18 * * 0 obsidian-agent run research_digest && obsidian-agent promote
```

---

## 15. Directory and Package Structure

```
obsidian-agent/
    pyproject.toml
    config/
        config.yaml

    obsidian_agent/
        cli.py
        config.py
        context.py
        logging_utils.py
        outputs.py              # VaultArtifact, Notification dataclasses

        vault/
            __init__.py
            reader.py           # walks vault, reads files
            parser.py           # extracts structure from note content

        index/
            __init__.py
            store.py            # DuckDB connection and schema init
            build_index.py      # incremental structural indexing logic
            queries.py          # structural query helpers
            chunker.py          # paragraph/section-aware note splitter
            semantic.py         # incremental semantic index build (embedding + intelligence)
            semantic_queries.py # semantic query helpers (similarity, concepts, entities)

        mcp/
            __init__.py
            server.py           # MCP server entrypoint
            tools.py            # tool implementations (search, get_note, etc.)

        embeddings/
            __init__.py
            base.py             # Embedder ABC
            local.py            # LocalEmbedder using sentence-transformers

        agent/
            __init__.py
            worker.py           # launches Claude Code with MCP server configured

        jobs/
            __init__.py
            registry.py
            task_notification.py
            research_digest.py

        promote/
            __init__.py
            promoter.py

        delivery/
            __init__.py
            base.py             # Delivery protocol
            smtp.py

    tests/
    scripts/
```

---

## 16. Dependency Direction

```
cli
 ├── config
 ├── logging_utils
 ├── context
 ├── index
 ├── jobs
 ├── promote
 ├── delivery
 └── agent

jobs
 ├── context
 ├── outputs
 ├── index
 ├── vault (Class A jobs; for index query helpers)
 ├── agent (Class B/C jobs only)
 └── delivery

agent
 └── stdlib only (subprocess, tempfile, pathlib)

mcp
 ├── vault
 └── index

promote
 └── stdlib only

delivery
 └── stdlib only (smtplib)

index
 ├── vault
 └── duckdb

vault
 └── stdlib only
```

`promote`, `delivery`, and `agent` do not depend on each other. `vault` knows nothing about
the index. `mcp` depends on vault and index but not on jobs or agent. These boundaries keep
each component independently testable.

---

## 17. Development Milestones

### Milestone 1 — Foundation
- Config loading and validation
- Logging setup
- Vault reader + parser (tasks, headings, links, tags, frontmatter, daily note detection,
  due date parsing from `📅 YYYY-MM-DD` format)
- DuckDB schema and store
- Incremental index builder
- CLI: `index`, `status`

### Milestone 2 — Task Notification
- `outputs.py` (VaultArtifact, Notification)
- SMTP delivery
- `task_notification` job
- Job registry and runner
- CLI: `run task_notification`
- Tests: parser (task and due date extraction), SMTP delivery (mocked), job logic

### Milestone 3 — Promoter
- Promoter implementation
- CLI: `promote`
- Tests: safety cases (no overwrite, symlink rejection, traversal rejection, extension check)

### Milestone 4 — MCP Server
- MCP server with full tool set
- CLI: `mcp` (starts the server; also useful for registering in Claude Desktop manually)
- Tests: each tool against a temp vault and index

### Milestone 5 — Claude Code Worker + Research Digest
- `agent/worker.py` (launches Claude Code with MCP server registered)
- CLI: `agent test`
- `research_digest` job
- Output validation (non-empty, valid markdown)
- CLI: `run research_digest`
- Tests: worker with dummy command; research digest with mocked worker

### Milestone 6 — Semantic Vault Intelligence

Adds a second indexing pipeline and richer MCP tools so Claude has ambient understanding
of the vault's conceptual landscape, not just its file structure.

- **6-1**: Embedding infrastructure (`Embedder` ABC, `LocalEmbedder`, chunker, DuckDB schema, VSS)
- **6-2**: Semantic index job — incremental embedding phase (`index-semantic` command)
- **6-3**: Concept and entity extraction — LLM intelligence phase (concepts, entities, implicit items, per-note summaries)
- **6-4**: Concept graph queries — DuckDB views and query helpers over extracted data
- **6-5**: MCP semantic tools — `search_similar`, `get_note_summary`, `find_related_notes`, `list_concepts`, `search_by_concept`, `get_entity_context`, `get_implicit_items`

**Key decisions**:
- Embeddings: `all-MiniLM-L6-v2` local model (384-dim, ~80MB); abstracted behind `Embedder` ABC
- Chunking: paragraph-level, section-aware (note-level is too coarse for diverse notes)
- Concept/entity extraction: per-chunk via Claude Code worker (note content injected directly; no MCP round-trip)
- Incremental: only changed notes reprocessed; staleness tracked via `content_sha256`
- Schedule: `index-semantic` runs daily, independent of per-job `index` runs

### Milestone 7 — Resurface and Hygiene

Builds the first jobs that make the semantic layer's value tangible to the user. See `docs/use_cases.md`
for the full use-case rationale.

- **7-1**: `vault_connections_report` (Class B) — weekly; surfaces old notes/ideas that connect
  to what the user has been writing about recently. Corrects recency bias and lossy memory.
- **7-2**: `vault_hygiene_report` (Class B) — bi-weekly; compares inferred implicit structure
  against explicit vault structure; suggests implied tasks to formalize, ideas to promote to
  standalone notes, and missing wikilinks. Suggestions only — no automated edits.

### Milestone 8 and beyond
- `stale_task_report` (Class A)
- `learning_aid` (Class B) — spaced retrieval practice inferred from reading notes
- `idea_expander` (Class B) — expands implicit items into draft notes
- `project_seeder` (Class B/C, separate design document when ready)

See `docs/use_cases.md` for the full catalog of imagined use cases and their infrastructure
dependencies.

---

## 18. Anti-Patterns to Avoid

- Giving Claude Code direct filesystem access to the vault path.
- Pre-fetching and injecting large context blobs when MCP tools let Claude Code pull what it
  needs. Keep prompts as task descriptions, not data dumps.
- Promoting output without basic validation (non-empty, `.md`, no obvious error text).
- Storing credentials in the config file.
- Putting vault write logic anywhere except `promoter.py`.
- Making the promoter smart. It copies files and enforces rules. That is all.
- Building Class B/C jobs before the MCP server is working and tested.
- Letting jobs depend on `cli.py` or `promote`.
