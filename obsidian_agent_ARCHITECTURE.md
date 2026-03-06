# Obsidian Agent — Architecture Guide

This document supplements the engineering PRD and is optimized for autonomous coding agents.
It defines module boundaries, data flow, dependency direction, interface contracts, and the expected
behavior of the first implementation milestones.

---

## 1. Purpose

`obsidian-agent` is a local-first automation framework for running scheduled jobs over an Obsidian vault.

The central architectural constraint is:

- the vault is **read-only** to jobs and agent runners
- all generated outputs go to an **outbox** outside the vault
- a **promoter** is the only component allowed to copy approved artifacts into the vault

This document should guide implementation choices toward safety, simplicity, and extensibility.

---

## 2. Top-Level Architectural Rules

### Rule 1: Jobs never write to the vault
Jobs may:
- read from `vault_readonly`
- read/write to `state_dir`
- write artifacts to `outbox`

Jobs may not:
- edit notes in `vault_real`
- delete files from the vault
- overwrite artifacts already promoted into the vault

### Rule 2: Promotion is narrow and dumb
The promoter should:
- copy only allowlisted file types
- reject symlinks
- reject path traversal
- never overwrite existing files
- only write under `vault_real/BotInbox/YYYY/MM/`

The promoter should not:
- parse LLM output
- do intelligent content inspection
- modify note content

### Rule 3: Agent runners are adapters, not business logic
The headless agent runner should be a small wrapper around a CLI tool.
It should not contain vault-specific logic.
Jobs construct prompts and interpret outputs.

### Rule 4: The DuckDB index is the shared substrate
The index is the reusable context layer for most jobs.
Jobs should prefer querying the index over re-walking the vault unless they have a strong reason not to.

### Rule 5: Prefer additive outputs
The system should generally create new notes rather than modifying existing notes.
The first versions should assume **append-only / create-only** behavior.

---

## 3. Primary Data Flow

```text
vault_real/
   |
   | (OS-enforced read-only mount)
   v
vault_readonly/
   |
   v
index builder ---------------------> DuckDB index
   |                                     |
   |                                     |
   +------------------------------+------+
                                  |
                                  v
                             jobs / agent jobs
                                  |
                                  v
                                outbox/
                                  |
                                  v
                               promoter
                                  |
                                  v
                   vault_real/BotInbox/YYYY/MM/<job>/
```

### Flow phases

#### Phase A — indexing
- Scan markdown notes from `vault_readonly`
- Extract structured metadata
- Persist to DuckDB

#### Phase B — job execution
- Query index and/or read note bodies
- Optionally invoke external headless agent CLI
- Write one or more `OutboxArtifact`s

#### Phase C — promotion
- Copy new artifacts from outbox to BotInbox
- Never overwrite
- Keep destination deterministic and auditable

---

## 4. Module Layout and Responsibilities

Recommended Python package structure:

```text
obsidian_agent/
    cli.py
    config.py
    context.py
    runner.py
    artifacts.py
    logging_utils.py

    vault/
        __init__.py
        reader.py
        parser.py

    index/
        __init__.py
        schema.sql
        store.py
        build_index.py
        queries.py

    jobs/
        __init__.py
        registry.py
        task_digest.py
        weekly_thought_starters.py
        llm_research_digest.py

    promote/
        __init__.py
        promoter.py
```

### `cli.py`
Responsibilities:
- parse CLI args
- load config
- initialize logging
- dispatch commands
- return process exit codes

Should not:
- contain parsing logic
- contain SQL strings except maybe trivial health checks
- contain promotion logic directly

### `config.py`
Responsibilities:
- load YAML config
- resolve paths
- validate required keys
- expose typed config objects

Should validate:
- `vault_readonly` exists
- `outbox` and `state_dir` are writable/creatable
- runner command is configured
- `bot_inbox_rel` is relative, not absolute

### `context.py`
Responsibilities:
- define `JobContext`
- package together config, logger, store, read-only vault path, runner, time helpers if desired

This keeps job signatures minimal.

### `artifacts.py`
Responsibilities:
- define `OutboxArtifact`
- implement atomic writes to outbox
- provide standard dated naming helpers

This is the only common interface jobs need for producing outputs.

### `runner.py`
Responsibilities:
- define runner abstraction
- implement generic subprocess-backed headless runner
- capture stdout/stderr/return code
- enforce timeout

Possible future abstraction:
- `BaseRunner`
- `SubprocessRunner`
- `CodexRunner`
- `ClaudeCodeRunner`

But v1 can start with a generic subprocess runner.

### `vault/reader.py`
Responsibilities:
- walk vault markdown files
- read files safely
- expose helpers like `iter_markdown_files()`

### `vault/parser.py`
Responsibilities:
- parse note content into structured features:
  - title
  - headings
  - tasks
  - tags
  - wikilinks
  - markdown links

Keep parsing deterministic and regex/lightweight.
Do not overcomplicate first version with full Markdown AST parsing.

### `index/store.py`
Responsibilities:
- connect to DuckDB
- initialize schema
- maybe version schema / migrations later

### `index/build_index.py`
Responsibilities:
- incremental indexing
- detect changed files via mtime/size/hash
- update normalized tables
- remove records for deleted notes

### `index/queries.py`
Responsibilities:
- contain reusable SQL queries used by jobs
- hide SQL from job modules where helpful

### `jobs/registry.py`
Responsibilities:
- register job names -> functions
- expose lookup
- optionally expose job metadata later

### `jobs/*.py`
Responsibilities:
- implement a single job each
- query index and/or read note content
- optionally call agent runner
- return artifacts

### `promote/promoter.py`
Responsibilities:
- scan outbox
- validate promote-eligible files
- copy into BotInbox/YYYY/MM/
- never overwrite
- produce structured result summary

---

## 5. Dependency Direction

Use this dependency rule:

```text
cli
 ├── config
 ├── logging_utils
 ├── context
 ├── index
 ├── jobs
 ├── promote
 └── runner

jobs
 ├── context
 ├── artifacts
 ├── index
 ├── vault
 └── runner

promote
 └── stdlib only (ideally)

index
 ├── vault
 └── duckdb

vault
 └── stdlib only
```

Important constraints:
- `promote` should not depend on `jobs`
- `vault` should not depend on `index`
- `runner` should not depend on vault-specific code
- `jobs` may depend on everything except `cli`

This keeps the package understandable and testable.

---

## 6. Core Interfaces

### `JobContext`

Recommended shape:

```python
@dataclass(frozen=True)
class JobContext:
    cfg: Config
    vault_ro: Path
    store: IndexStore
    runner: HeadlessRunner | None
    logger: logging.Logger
```

Notes:
- `runner` may be optional for non-LLM jobs
- this object should be created in `cli.py`

### `OutboxArtifact`

Recommended shape:

```python
@dataclass(frozen=True)
class OutboxArtifact:
    relpath: str
    content: str

    def write_to_outbox(self, outbox_root: Path) -> Path:
        ...
```

Constraints:
- `relpath` must be relative
- writing must be atomic
- `..` path traversal must be rejected

### `RunnerResult`

```python
@dataclass(frozen=True)
class RunnerResult:
    returncode: int
    stdout: str
    stderr: str
```

### job function

```python
def run(ctx: JobContext) -> list[OutboxArtifact]:
    ...
```

---

## 7. DuckDB Schema Guidance

Minimum normalized schema:

### `notes`
```sql
CREATE TABLE IF NOT EXISTS notes (
  note_relpath TEXT PRIMARY KEY,
  title TEXT,
  mtime_ns BIGINT,
  size_bytes BIGINT,
  content_sha256 TEXT,
  word_count INTEGER
);
```

### `tasks`
```sql
CREATE TABLE IF NOT EXISTS tasks (
  note_relpath TEXT,
  line_no INTEGER,
  checked BOOLEAN,
  text TEXT
);
```

### `links`
```sql
CREATE TABLE IF NOT EXISTS links (
  note_relpath TEXT,
  target TEXT,
  kind TEXT
);
```

### `tags`
```sql
CREATE TABLE IF NOT EXISTS tags (
  note_relpath TEXT,
  tag TEXT
);
```

### `headings`
```sql
CREATE TABLE IF NOT EXISTS headings (
  note_relpath TEXT,
  heading TEXT
);
```

### Recommended future tables
```sql
CREATE TABLE IF NOT EXISTS note_stats (
  note_relpath TEXT PRIMARY KEY,
  open_task_count INTEGER,
  outgoing_link_count INTEGER,
  tag_count INTEGER
);

CREATE TABLE IF NOT EXISTS topic_candidates (
  topic TEXT,
  note_relpath TEXT,
  score DOUBLE
);
```

### Why normalized tables?
Normalized tables make it easy to:
- query open tasks
- identify tag neighborhoods
- count backlinks/outgoing links
- support downstream clustering or graph heuristics

---

## 8. Indexing Strategy

### First-pass indexing algorithm
For each markdown file in `vault_readonly`:

1. get relative path
2. inspect `mtime_ns` and file size
3. compare to previously indexed metadata
4. if changed, read content and hash
5. parse note
6. update `notes`
7. delete+replace derived rows in `tasks`, `links`, `tags`, `headings`

### Deletion handling
After scanning all current files:
- delete records for notes no longer present on disk

### Incremental behavior
Use a layered check:
- unchanged `mtime_ns` and `size_bytes` -> skip
- otherwise compute hash
- unchanged hash -> update metadata only
- changed hash -> full parse + replace derived records

This is robust and simple.

---

## 9. Job Design Patterns

There should be two broad classes of jobs.

### Class A — deterministic jobs
These do not need an agent runner.
They operate only from the index and filesystem.

Examples:
- task digest
- stale thread detection
- orphan note detection
- weekly thought starters based on tags/links

### Class B — LLM-assisted jobs
These use deterministic selection + agent generation.

Recommended pattern:
1. use SQL / heuristics to select source material
2. construct a bounded prompt
3. call runner
4. transform runner output into markdown artifact
5. write to outbox

Examples:
- research digests
- note synthesis
- project pitch generation

### Guideline
Do **not** hand the entire vault to the agent.
Use the index to narrow context first.

---

## 10. Initial Job Specs

### Job: `task_digest`

#### Purpose
Produce a daily markdown digest of incomplete tasks.

#### Inputs
- `tasks` table
- optional config filter for tags

#### Output
One markdown file:
```text
outbox/task_digest/YYYY-MM-DD_task-digest.md
```

#### Example sections
- Open tasks
- Tasks grouped by note
- Optional “attention” section for notes with many open tasks

#### Useful SQL
```sql
SELECT note_relpath, line_no, text
FROM tasks
WHERE checked = false
ORDER BY note_relpath, line_no
LIMIT ?;
```

Optional tag-filtered version:
```sql
SELECT t.note_relpath, t.line_no, t.text
FROM tasks t
JOIN tags g ON g.note_relpath = t.note_relpath
WHERE t.checked = false
  AND g.tag IN (...)
ORDER BY t.note_relpath, t.line_no;
```

---

### Job: `weekly_thought_starters`

#### Purpose
Generate prompts that combine distant or weakly connected concepts.

#### Initial heuristic
- sample distinct tags
- pair tags with low apparent overlap
- generate prompt templates without LLM

#### Output
One markdown file:
```text
outbox/weekly_thought_starters/YYYY-MM-DD_thought-starters.md
```

#### Future improvement ideas
- use link graph distance
- use note co-occurrence
- use embeddings once implemented

---

### Job: `llm_research_digest` (future)
#### Purpose
Take a set of curated research items and synthesize a concise weekly note.

#### Inputs
- selected note excerpts and/or external research results
- topic hints from tags or note clusters

#### Flow
1. build source bundle
2. prompt runner with strict response format
3. emit markdown artifact

#### Suggested prompt style
- short task statement
- explicit output format
- no conversational fluff
- require markdown

---

## 11. Prompt Construction Guidance for Headless Agents

Because the external runner is an autonomous coding/agent CLI, prompts should be explicit and bounded.

### Good prompt properties
- clearly state role
- clearly state input materials
- define exact output format
- avoid asking questions
- forbid interactive behavior
- require final answer only

### Example pattern
```text
You are generating a markdown note for an Obsidian vault.

Task:
Summarize the following source notes into a concise weekly digest.

Requirements:
- Output markdown only
- Use a top-level H1 title
- Include sections: Summary, Key Threads, Follow-up Ideas
- Do not ask clarifying questions
- Do not include commentary about the process

Sources:
...
```

### Important
Jobs should treat runner output as text generation, not privileged code execution.

---

## 12. Promoter Design Details

### Allowed behavior
For each eligible outbox file:
- verify file extension is allowlisted
- ensure file is inside outbox root
- ensure file is not a symlink
- construct destination under `BotInbox/YYYY/MM/<relative path>`
- skip if destination exists
- copy into destination atomically

### Suggested destination policy
Preserve relative job folder structure under a dated prefix.

Example:
```text
outbox/task_digest/2026-03-05_task-digest.md
-> vault/BotInbox/2026/03/task_digest/2026-03-05_task-digest.md
```

This is simple and audit-friendly.

### Promoter return object
Recommended:
```python
@dataclass(frozen=True)
class PromoteResult:
    promoted: int
    skipped: int
    errors: int
```

### Promoter test cases
At minimum test:
- promotes a new markdown file
- skips existing destination
- skips symlink
- skips disallowed extension
- rejects traversal attempts

---

## 13. Suggested Config Schema

```yaml
paths:
  vault_readonly: /mnt/vault_ro
  vault_real: ~/ObsidianVault
  bot_inbox_rel: BotInbox
  outbox: ~/agent_outbox
  state_dir: ~/.local/share/obsidian-agent

cache:
  duckdb_path: ~/.local/share/obsidian-agent/cache.duckdb

runner:
  command: codex
  args: ["run", "--non-interactive"]
  timeout_seconds: 900

jobs:
  task_digest:
    include_tags: []
    max_items: 30

  weekly_thought_starters:
    max_pairs: 6
```

Validation rules:
- `bot_inbox_rel` must be relative
- `vault_readonly` must exist
- `outbox` must not be inside `vault_real`
- `state_dir` should be outside `vault_real`
- runner config is required if LLM-assisted jobs are enabled

---

## 14. Observability and Logging

Log to:
```text
state_dir/logs/
```

Each command should log:
- start/end
- key config paths
- counts (files indexed, tasks found, artifacts written, promotions completed)
- runner command used
- runner stdout/stderr snippets if useful
- errors with stack traces in failure cases

### Recommended logging philosophy
- INFO for normal operational steps
- WARNING for skipped files / unsupported cases
- ERROR for failed promotions or failed runner invocations

---

## 15. Testing Strategy

### Unit tests
Focus on:
- parser extraction
- artifact write safety
- promoter behavior
- config validation
- runner subprocess handling (with a dummy command)

### Integration tests
Use temp directories to simulate:
- vault_readonly
- outbox
- vault_real/BotInbox
- DuckDB index file

Recommended integration scenarios:
1. index a few notes
2. run `task_digest`
3. confirm outbox artifact exists
4. promote
5. confirm promoted file exists in BotInbox path

### Do not require a real agent CLI for most tests
Runner tests should use a fake executable or simple shell command.

---

## 16. Implementation Order for Coding Agents

Recommended order:

### Milestone 1
- config loading
- logging setup
- vault reader/parser
- DuckDB schema/store
- index builder
- CLI `index`

### Milestone 2
- `OutboxArtifact`
- job registry
- `task_digest`
- CLI `run job`

### Milestone 3
- promoter
- CLI `promote`
- promoter tests

### Milestone 4
- generic headless runner
- CLI `runner test`
- `weekly_thought_starters`

### Milestone 5
- first LLM-assisted job
- reusable query helpers
- improved prompt templates

This sequencing gets to a useful system quickly while keeping the risky parts late.

---

## 17. Anti-Patterns to Avoid

Do not:
- give the agent direct write access to the vault
- use the runner to perform file mutation in the vault
- store the entire note bodies in every table unless needed
- put business logic into `cli.py`
- let jobs shell out directly without going through runner abstraction
- make the promoter “smart”

The whole system works because the boundaries stay crisp.

---

## 18. Suggested First Coding-Agent Prompt

A good initial prompt for Codex/Claude Code might be:

```text
Implement the obsidian-agent project described in the attached PRD and ARCHITECTURE documents.

Requirements:
- Python 3.11+
- use uv for project management
- use DuckDB for the cache
- implement the package structure exactly
- implement CLI commands:
  - index
  - run job <job_name>
  - promote
  - runner test
- implement jobs:
  - task_digest
  - weekly_thought_starters
- implement a safe promoter
- add tests for parser and promoter
- do not add direct vault write paths outside the promoter
- keep code simple, typed, and well commented
```

---

## 19. Long-Term Extension Points

Once the foundation is stable, likely additions include:
- embeddings table(s)
- inferred topic clusters
- external research ingestion pipeline
- idea ranking / stale thread ranking
- email delivery module
- daily/weekly schedule presets
- richer artifact types (images, JSON metadata, etc.)

These should all build on the same foundation:
read-only vault, shared index, outbox, promoter.

---

## 20. Final Guiding Principle

The most important architectural property is not “agent power.”
It is **vault integrity**.

Every design decision should preserve this invariant:

> No agent job can directly alter the user's Obsidian vault.
> All outputs are staged first and promoted through a narrow, auditable path.
