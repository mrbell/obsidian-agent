# Use Cases — Obsidian Agent

A living document capturing what this system is for, organized by use case cluster. Separate
from DESIGN.md (engineering spec) and from issues (implementation tasks). This is the product
vision layer: why each capability matters, what makes it distinctive, and what infrastructure
it depends on.

---

## Core Target Use Case

> **Claude has rich, ambient context about the vault during any session.**

When working with Claude — in chat, a coding session, or via a scheduled job — Claude can
retrieve semantically relevant vault content without the user having to explicitly direct it.
It understands the user's conceptual landscape: recurring themes, active interests, open
questions, past ideas. Not just the file structure.

This is the use case that everything else builds on. It is enabled by:
- The semantic index (embeddings + concept/entity extraction)
- The MCP server exposing that index as queryable tools
- The MCP server being registered in Claude Desktop and Claude Code

---

## The Anti-Goal

This system must **never impose structure** on the vault. The user should be able to write in
any form — stream of consciousness, loose project notes, random essays — and the system infers
meaningful structure from content rather than requiring the user to maintain a rigid taxonomy.

The inferred structure can be surfaced back as *suggestions*, never applied automatically.

---

## The Virtuous Cycle

The more richly the user writes, the better the semantic index. The better the index, the
more value the system returns. The more value, the more motivated the user is to write richly.

This cycle is the design goal. Jobs and tools should be evaluated partly by whether they
reinforce it. The most important reinforcement: if users know their notes will be actively
surfaced and connected later, low-friction behaviors that feel pointless today (logging a paper
with key quotes, capturing a half-formed idea) become worthwhile.

---

## Use Case Clusters

### 1. Vault-Aware Jobs

**What it is**: Any scheduled job that does more than generic analysis because it knows what
the user already thinks, knows, and cares about.

**Examples**:
- `research_digest` finds articles on "agentic coding" — but with semantic context, it
  identifies that several articles relate to specific vault notes the user has written, and
  surfaces that connection explicitly. "This article is relevant to your note on X."
- A future synthesis job avoids re-explaining concepts the user already understands deeply
  (high-salience vault concepts) and focuses on what's genuinely new.
- Topic selection for research jobs could eventually be *inferred* from vault concepts rather
  than statically configured.

**Depends on**: Semantic index (M6), MCP semantic tools (M6-5)

**Status**: Partially enabled by M6. Research digest prompt already queries vault via MCP;
richer semantic tools make the connection more precise and the output more personalized.

---

### 2. Serendipitous Resurface

**What it is**: The system surfaces old concepts, ideas, and questions from the vault when
they become relevant again — either periodically or triggered by recent vault activity.

**Why it's distinctive**: Human memory is recency-biased and lossy. We forget things we've
written, fail to notice when an old idea becomes relevant, and rarely rediscover archived
material unless we actively search for it. This use case corrects all three failures
automatically.

**Examples**:
- "You wrote about the tension between structure and creative flow 8 months ago. You've been
  writing about that again this week — here's what you said then."
- "This question you noted in March is related to the paper you just logged today."
- "Three separate daily notes from the past year express interest in building a second-brain
  tool. Here's a synthesis."

**Job**: `vault_connections_report` (Class B, weekly). See M7.

**Depends on**: Semantic index with temporal awareness (M6), concept graph (M6-4), MCP
semantic tools (M6-5)

**Status**: Planned for M7.

---

### 3. Vault Hygiene Suggestions

**What it is**: A periodic audit that compares the *implicit* structure inferred by the
semantic layer against the *explicit* structure the user has created, and suggests improvements.

**Why it's distinctive**: The system is uniquely positioned to notice the gap between what
the user *thinks* and what their vault *formally captures*. Most note-taking tools only see
the explicit structure. This one sees both.

**Concrete suggestions**:
- **Implied tasks not formally captured**: "You wrote 'I need to follow up with Alice about
  the proposal' in a daily note — this isn't a formal task. Want to add it?"
- **Ideas worth a standalone note**: "This paragraph about latent structure in knowledge
  bases has been referenced in three daily notes and seems like it deserves its own note."
- **Missing wikilinks**: "Your note on 'Second Brain' and your note on 'PKM tools' discuss
  the same concepts but aren't linked."
- **Orphaned threads**: "You expressed strong interest in learning Rust in April and haven't
  mentioned it since. Still relevant?"

**Anti-pattern to avoid**: Automated edits. This is a suggestion report only. The user decides
what to act on. The promoter stays additive-only.

**Job**: `vault_hygiene_report` (Class B, weekly or bi-weekly). See M7.

**Depends on**: Structural index (tasks, links — already built), implicit items extraction
(M6-3), concept graph (M6-4), cross-index queries (M6-4)

**Status**: Planned for M7.

---

### 4. Targeted Learning Resources

**What it is**: Based on what the user is actively thinking about or working on, generate
concrete learning material: a minimal working example of a concept, a set of exercises to
build on it, or a problem set to work through. Delivered as a vault note.

**Why it's distinctive**: Generic tutorials explain concepts in the abstract. This generates
material calibrated to *what the user already knows* (from vault concepts and summaries) and
*what they're currently working on* (from recent note activity). A toy implementation of a
concept they've been writing about in daily notes, with exercises that extend it, is more
useful than anything they'd find by searching.

**Examples**:
- "You've been writing about vector similarity search this week. Here's a 50-line Python
  implementation from scratch, followed by three exercises: add cosine normalization, swap
  in a different distance metric, implement approximate nearest neighbors naively."
- "You noted interest in learning Rust's ownership model. Here's a minimal program that
  demonstrates the borrow checker, with five progressively harder variations to try."
- "You've been reading about dynamic programming. Here's a problem set of five problems
  ordered by difficulty, with the first one solved as a worked example."

**What makes it work**: The vault context tells the job what the user already understands
(avoid re-explaining high-salience concepts) and what's currently active (choose a topic
that's live in their thinking, not one they explored six months ago and moved on from).

**Depends on**: Semantic index (recent concepts, note summaries), Claude Code worker with
web access optional (for pulling in problem ideas), MCP tools

**Status**: Imagined. Composable with the learning aid use case (use case 5) but distinct —
this is generative and practical rather than retrieval-based.

---

### 5. Learning Aid

**What it is**: For topics the user is actively learning (papers read, books studied, concepts
being developed), generate periodic retrieval practice — questions, prompts, summaries — to
reinforce retention without requiring the user to tag material as "learning content."

**Why it's distinctive**: Existing tools (Anki, Readwise) require deliberate curation.
This infers from content that something is worth reinforcing: a note with dense concepts, a
paper summary, a detailed exploration of a new framework. The inference is the novel part.

**Examples**:
- Weekly email: "Here are 3 questions based on the papers you've been reading."
- "You logged key ideas from *How Minds Change* two months ago — here's a quick recall prompt."

**Depends on**: Concept extraction per-chunk (M6-3), note summaries (M6-3), implicit items
(M6-3, type=idea), note content (existing MCP tools)

**Status**: Imagined. High value. Requires careful design of the "what counts as learning
material" inference — do not prematurely classify notes.

---

### 5. Generative Prompts and Idea Expansion

**What it is**: Using the concept graph and implicit items to generate thought-provoking
prompts, brainstorming seeds, or expansions of half-formed ideas.

**Examples**:
- "You have half-formed ideas about distributed cognition and personal productivity. Here are
  3 questions that might connect them."
- "This idea you jotted in a daily note — expanded into a one-page outline."
- "These two concepts in your vault have never been connected but seem related — what would
  a note exploring their relationship look like?"

**Depends on**: Concept graph (M6-4), implicit items (M6-3, type=idea|question), MCP tools

**Status**: Imagined. Composable with the hygiene report (idea expansion could be a section
of it rather than a separate job).

---

### 6. Extended Memory for Reading

**What it is**: The system creates genuine long-term memory for books, papers, and articles
the user has read — surfacing relevant material when a new note touches the same territory.

**Why it matters**: Users currently don't bother to log reading in their vault because they
won't easily find it later. If the semantic index actively surfaces a book's key ideas when
they become relevant again, that calculus changes. A logged quote from a paper becomes
retrievable context for future work.

**This is a behavior change, not just a feature**: The value of the semantic layer creates
an incentive to log more richly. A note about a book with key quotes and reactions is worth
10x more than just a title, because the system can find and use those ideas in context.

**Potential future enhancement**: Import from Readwise, Kindle highlights, or similar — but
not a prerequisite. Plain vault notes work fine.

**Depends on**: Semantic search (M6-5), concept/entity extraction (M6-3, books as entities)

**Status**: Imagined as a behavior pattern, not a specific job. Jobs like serendipitous
resurface and hygiene report both reward and reinforce this behavior.

---

### 7. Conversation Capture (Cross-Surface Memory)

**What it is**: A mechanism to extract key ideas, decisions, concepts, and open questions
from Claude sessions — both Claude Code interactive sessions and Claude.ai conversations —
and deposit them into the vault so they become part of the permanent, searchable knowledge
base.

**The problem**: The user's thinking is distributed across multiple surfaces that don't talk
to each other:
- **Vault** — what this system indexes and reasons over
- **Claude Code sessions** — interactive sessions where design decisions, ideas, and plans
  emerge (like the conversation that produced M6 and M7)
- **Claude.ai conversations** — longer exploratory conversations; no programmatic access today
- **Codebases** — ideas that make it into code, comments, and design docs

Good ideas raised in a session often don't make it back to the vault. Some get manually
re-phrased into notes; many don't. The result is a fragmented intellectual record.

**Why it's different from other use cases**: Everything else in this system flows from the
vault outward (vault → index → jobs → output → vault). This use case requires a new
*input* path: conversation transcript → extract → vault. It's not a scheduled job; it's an
on-demand ingestion tool.

**Proposed approach**: An `obsidian-agent capture-session` CLI command (and possibly a Claude
Code slash command shortcut). At the end of a meaningful session, invoke it to:
1. Read the session transcript (Claude Code session JSONL from `~/.claude/projects/`, or
   raw text piped from a Claude.ai export)
2. Extract key ideas, decisions, open questions, and anything worth persisting
3. Produce a structured vault note deposited via the promoter to `BotInbox/session_notes/`

**The intentionality question**: Automatic capture of every session would produce noise. A
deliberate "capture this session" action means the user is filtering for what matters. Some
friction here may be a feature, not a bug.

**Accessibility constraints**:
- Claude Code sessions: transcript JSONL files exist on disk at `~/.claude/projects/` —
  readable programmatically
- Claude.ai conversations: no API access today; requires manual export as a bridge until
  Anthropic provides programmatic access

**Depends on**: Claude Code worker (M5, already built), promoter (M3, already built).
The extraction prompt is similar to M6-3 concept extraction but operates on conversation
transcripts rather than notes. Does not require the semantic index.

**Status**: Imagined. Architecturally distinct from scheduled jobs — separate CLI command,
new input source. Design when M7 is closer to complete.

---

## Infrastructure Dependency Map

```
Structural index (Milestones 1-5)
  └── task_notification (built)
  └── research_digest (built)
  └── All future jobs have access to tasks, links, tags, headings

Semantic index (Milestone 6)
  ├── Embeddings + chunker (6-1, 6-2)
  │     └── search_similar MCP tool
  │     └── find_related_notes MCP tool
  ├── Concept/entity/implicit-item extraction (6-3)
  │     └── list_concepts, search_by_concept, get_entity_context,
  │         get_implicit_items MCP tools
  │     └── get_note_summary MCP tool
  └── Cross-index query layer (6-4)
        └── temporal-aware similarity (recent vs old)
        └── implicit-vs-explicit structure comparison
        └── Powers: vault_connections_report, vault_hygiene_report

Milestone 7 jobs
  ├── vault_connections_report — serendipitous resurface
  └── vault_hygiene_report    — close the loop, suggest improvements

Future jobs (not yet planned)
  ├── targeted_learning       — toy code + exercises + problem sets for active topics
  ├── learning_aid            — spaced retrieval practice
  ├── idea_expander           — expand implicit items into drafts
  └── concept_prompt_generator — brainstorming seeds

On-demand tools (not scheduled jobs)
  └── capture-session         — extract key ideas from Claude sessions into vault
        ├── Input: Claude Code session JSONL or piped transcript text
        ├── Depends on: worker (M5), promoter (M3) — no semantic index needed
        └── Constraint: Claude.ai sessions require manual export until API access exists
```

---

## What Makes This System Distinctive

Most tools that interact with a knowledge base either:
- Require rigid structure the user must maintain (tags, folders, templates)
- Read the whole vault at query time (expensive, context-limited, not incremental)

This system does neither. It builds and maintains an inferred semantic layer continuously,
incrementally, and without requiring the user to do anything differently than they already do.

The MCP server means any Claude session — not just scheduled jobs — can benefit. The user
doesn't have to invoke a tool or run a query; Claude can proactively pull vault context
that's relevant to whatever the conversation is about.

The scheduled jobs close the loop by *returning* inferred structure to the user in actionable
form: connections they didn't know existed, tasks that were implied but never captured, ideas
worth developing.
