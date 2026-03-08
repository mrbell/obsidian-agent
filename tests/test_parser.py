from datetime import date

import pytest

from obsidian_agent.vault.parser import (
    Heading,
    Link,
    ParsedNote,
    Tag,
    Task,
    parse_note,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _note(content: str, filename: str = "note.md") -> ParsedNote:
    return parse_note(content, filename)


# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------

class TestTitle:
    def test_title_from_first_h1(self):
        note = _note("# My Title\n\nSome text.")
        assert note.title == "My Title"

    def test_title_from_filename_when_no_h1(self):
        note = _note("## Not a title\n\nSome text.", filename="my-note.md")
        assert note.title == "my-note"

    def test_title_uses_first_h1_only(self):
        note = _note("# First\n\n# Second\n")
        assert note.title == "First"

    def test_title_from_filename_empty_note(self):
        note = _note("", filename="empty.md")
        assert note.title == "empty"


# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

class TestFrontmatter:
    def test_parses_frontmatter(self):
        content = "---\ntitle: Hello\nauthor: Alice\n---\n\n# Body"
        note = _note(content)
        assert note.frontmatter == {"title": "Hello", "author": "Alice"}

    def test_no_frontmatter(self):
        note = _note("# Just a heading\n")
        assert note.frontmatter == {}

    def test_empty_frontmatter_block(self):
        note = _note("---\n---\n\n# Body")
        assert note.frontmatter == {}

    def test_frontmatter_does_not_appear_in_headings(self):
        content = "---\ntitle: FM Title\n---\n\n# Real Heading\n"
        note = _note(content)
        assert len(note.headings) == 1
        assert note.headings[0].text == "Real Heading"

    def test_unclosed_frontmatter_treated_as_body(self):
        content = "---\ntitle: Oops\n\n# Heading\n"
        note = _note(content)
        assert note.frontmatter == {}
        assert note.headings[0].text == "Heading"


# ---------------------------------------------------------------------------
# Daily note detection
# ---------------------------------------------------------------------------

class TestDailyNote:
    def test_daily_note_detected(self):
        note = _note("", filename="2026-03-07.md")
        assert note.is_daily_note is True

    def test_non_daily_note(self):
        note = _note("", filename="my-note.md")
        assert note.is_daily_note is False

    def test_almost_daily_note_not_detected(self):
        note = _note("", filename="2026-3-7.md")
        assert note.is_daily_note is False


# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------

class TestHeadings:
    def test_heading_levels(self):
        content = "# H1\n## H2\n### H3\n"
        note = _note(content)
        assert [(h.level, h.text) for h in note.headings] == [
            (1, "H1"), (2, "H2"), (3, "H3")
        ]

    def test_heading_line_numbers(self):
        content = "\n# First\n\n## Second\n"
        note = _note(content)
        assert note.headings[0].line_no == 2
        assert note.headings[1].line_no == 4

    def test_no_headings(self):
        note = _note("Just some text.\n")
        assert note.headings == []


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

class TestTaskStatus:
    def test_open_task(self):
        note = _note("- [ ] Do the thing\n")
        assert note.tasks[0].status == "open"

    def test_done_task_lowercase(self):
        note = _note("- [x] Done it\n")
        assert note.tasks[0].status == "done"

    def test_done_task_uppercase(self):
        note = _note("- [X] Also done\n")
        assert note.tasks[0].status == "done"

    def test_in_progress_task(self):
        note = _note("- [/] Working on it\n")
        assert note.tasks[0].status == "in_progress"

    def test_cancelled_task(self):
        note = _note("- [-] Not doing this\n")
        assert note.tasks[0].status == "cancelled"

    def test_unknown_checkbox_defaults_to_open(self):
        note = _note("- [?] Weird status\n")
        assert note.tasks[0].status == "open"


class TestTaskDueDate:
    def test_due_date_extracted(self):
        note = _note("- [ ] Write report 📅 2026-03-10\n")
        assert note.tasks[0].due_date == date(2026, 3, 10)

    def test_no_due_date(self):
        note = _note("- [ ] No date here\n")
        assert note.tasks[0].due_date is None

    def test_due_date_in_middle_of_text(self):
        note = _note("- [ ] Meeting 📅 2026-04-01 with Alice\n")
        assert note.tasks[0].due_date == date(2026, 4, 1)

    def test_task_text_preserved(self):
        note = _note("- [ ] Ship feature 📅 2026-03-15\n")
        assert note.tasks[0].text == "Ship feature 📅 2026-03-15"

    def test_indented_task(self):
        note = _note("  - [ ] Indented task\n")
        assert len(note.tasks) == 1
        assert note.tasks[0].status == "open"


class TestTaskLineNumbers:
    def test_task_line_number(self):
        content = "# Heading\n\n- [ ] First task\n- [x] Second task\n"
        note = _note(content)
        assert note.tasks[0].line_no == 3
        assert note.tasks[1].line_no == 4


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------

class TestWikilinks:
    def test_wikilink(self):
        note = _note("See [[Target Note]] for details.\n")
        wikilinks = [l for l in note.links if l.kind == "wikilink"]
        assert len(wikilinks) == 1
        assert wikilinks[0].target == "Target Note"

    def test_wikilink_with_alias(self):
        note = _note("See [[Target Note|alias]] here.\n")
        wikilinks = [l for l in note.links if l.kind == "wikilink"]
        assert wikilinks[0].target == "Target Note"

    def test_multiple_wikilinks_on_one_line(self):
        note = _note("Links: [[A]] and [[B]].\n")
        wikilinks = [l for l in note.links if l.kind == "wikilink"]
        assert {l.target for l in wikilinks} == {"A", "B"}


class TestMarkdownLinks:
    def test_markdown_link(self):
        note = _note("Visit [example](https://example.com) for more.\n")
        md_links = [l for l in note.links if l.kind == "markdown"]
        assert len(md_links) == 1
        assert md_links[0].target == "https://example.com"

    def test_mixed_links(self):
        content = "See [[Wiki]] and [ext](http://x.com).\n"
        note = _note(content)
        assert any(l.kind == "wikilink" and l.target == "Wiki" for l in note.links)
        assert any(l.kind == "markdown" and l.target == "http://x.com" for l in note.links)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

class TestFrontmatterTags:
    def test_frontmatter_tags_list(self):
        content = "---\ntags:\n  - python\n  - project\n---\n\nBody.\n"
        note = _note(content)
        fm_tags = [t for t in note.tags if t.source == "frontmatter"]
        assert {t.name for t in fm_tags} == {"python", "project"}

    def test_frontmatter_tags_string(self):
        content = "---\ntags: single\n---\n\nBody.\n"
        note = _note(content)
        fm_tags = [t for t in note.tags if t.source == "frontmatter"]
        assert fm_tags[0].name == "single"

    def test_no_frontmatter_tags(self):
        content = "---\ntitle: No tags\n---\n\nBody.\n"
        note = _note(content)
        assert [t for t in note.tags if t.source == "frontmatter"] == []


class TestInlineTags:
    def test_inline_tag(self):
        note = _note("This is #important work.\n")
        inline_tags = [t for t in note.tags if t.source == "inline"]
        assert any(t.name == "important" for t in inline_tags)

    def test_inline_tag_with_slash(self):
        note = _note("Filed under #project/obsidian.\n")
        inline_tags = [t for t in note.tags if t.source == "inline"]
        assert any(t.name == "project/obsidian" for t in inline_tags)

    def test_heading_markers_not_tags(self):
        note = _note("## My Heading\n")
        inline_tags = [t for t in note.tags if t.source == "inline"]
        assert not any(t.name == "My" for t in inline_tags)
        assert not any(t.name == "#" for t in inline_tags)

    def test_inline_tags_deduplicated(self):
        note = _note("#work here and #work there.\n")
        inline_tags = [t for t in note.tags if t.source == "inline" and t.name == "work"]
        assert len(inline_tags) == 1

    def test_inline_tags_not_in_frontmatter_block(self):
        content = "---\ntitle: No inline tags here #notag\n---\n\n#realtag\n"
        note = _note(content)
        inline_tags = [t for t in note.tags if t.source == "inline"]
        assert not any(t.name == "notag" for t in inline_tags)
        assert any(t.name == "realtag" for t in inline_tags)


# ---------------------------------------------------------------------------
# Word count
# ---------------------------------------------------------------------------

class TestWordCount:
    def test_word_count(self):
        note = _note("one two three\n")
        assert note.word_count == 3

    def test_word_count_excludes_frontmatter(self):
        content = "---\ntitle: Not counted\n---\n\nfour words right here\n"
        note = _note(content)
        assert note.word_count == 4

    def test_empty_note_word_count(self):
        note = _note("")
        assert note.word_count == 0


# ---------------------------------------------------------------------------
# Full integration fixture
# ---------------------------------------------------------------------------

class TestFullNote:
    CONTENT = """\
---
title: Project Alpha
tags:
  - work
  - planning
---

# Project Alpha

Some intro text with #urgent tag and a [[Related Note]].

## Tasks

- [ ] Draft proposal 📅 2026-03-15
- [x] Initial meeting
- [/] Research phase
- [-] Old approach

## Links

See [the docs](https://docs.example.com) for reference.
Also see [[Another Note|custom alias]].
"""

    def test_full_note_title(self):
        assert _note(self.CONTENT).title == "Project Alpha"

    def test_full_note_frontmatter(self):
        note = _note(self.CONTENT)
        assert note.frontmatter["title"] == "Project Alpha"
        assert "work" in note.frontmatter["tags"]

    def test_full_note_is_not_daily(self):
        assert _note(self.CONTENT).is_daily_note is False

    def test_full_note_headings(self):
        headings = _note(self.CONTENT).headings
        assert headings[0].text == "Project Alpha"
        assert headings[1].text == "Tasks"
        assert headings[2].text == "Links"

    def test_full_note_tasks(self):
        tasks = _note(self.CONTENT).tasks
        assert tasks[0].status == "open"
        assert tasks[0].due_date == date(2026, 3, 15)
        assert tasks[1].status == "done"
        assert tasks[2].status == "in_progress"
        assert tasks[3].status == "cancelled"

    def test_full_note_links(self):
        links = _note(self.CONTENT).links
        wikilinks = {l.target for l in links if l.kind == "wikilink"}
        md_links = {l.target for l in links if l.kind == "markdown"}
        assert "Related Note" in wikilinks
        assert "Another Note" in wikilinks
        assert "https://docs.example.com" in md_links

    def test_full_note_tags(self):
        tags = _note(self.CONTENT).tags
        fm_names = {t.name for t in tags if t.source == "frontmatter"}
        inline_names = {t.name for t in tags if t.source == "inline"}
        assert fm_names == {"work", "planning"}
        assert "urgent" in inline_names

    def test_full_note_word_count_positive(self):
        assert _note(self.CONTENT).word_count > 0
