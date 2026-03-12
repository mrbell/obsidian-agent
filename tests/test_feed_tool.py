from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from obsidian_agent.mcp.tools import fetch_feed


RSS_FIXTURE = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>First Article</title>
      <link>https://example.com/first</link>
      <pubDate>Mon, 09 Mar 2026 10:00:00 +0000</pubDate>
      <description>Summary of the first article.</description>
    </item>
    <item>
      <title>Second Article</title>
      <link>https://example.com/second</link>
      <pubDate>Tue, 10 Mar 2026 10:00:00 +0000</pubDate>
      <description>Summary of the second article.</description>
    </item>
  </channel>
</rss>"""

ATOM_FIXTURE = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Test Atom Feed</title>
  <entry>
    <title>First Entry</title>
    <link href="https://example.com/entry1"/>
    <published>2026-03-09T10:00:00Z</published>
    <summary>Summary of entry one.</summary>
  </entry>
  <entry>
    <title>Second Entry</title>
    <link href="https://example.com/entry2"/>
    <published>2026-03-10T10:00:00Z</published>
    <summary>Summary of entry two.</summary>
  </entry>
</feed>"""


def _mock_urlopen(data: bytes) -> MagicMock:
    """Context manager mock that yields a response whose .read() returns data."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = data
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_resp
    mock_ctx.__exit__.return_value = False
    return mock_ctx


# ---------------------------------------------------------------------------
# RSS 2.0
# ---------------------------------------------------------------------------

class TestFetchFeedRSS:
    def test_returns_correct_item_count(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(RSS_FIXTURE)):
            items = fetch_feed("https://feeds.example.com/rss")
        assert len(items) == 2

    def test_first_item_fields(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(RSS_FIXTURE)):
            items = fetch_feed("https://feeds.example.com/rss")
        assert items[0]["title"] == "First Article"
        assert items[0]["link"] == "https://example.com/first"
        assert items[0]["published"] == "Mon, 09 Mar 2026 10:00:00 +0000"
        assert items[0]["summary"] == "Summary of the first article."

    def test_second_item_title(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(RSS_FIXTURE)):
            items = fetch_feed("https://feeds.example.com/rss")
        assert items[1]["title"] == "Second Article"


# ---------------------------------------------------------------------------
# Atom 1.0
# ---------------------------------------------------------------------------

class TestFetchFeedAtom:
    def test_returns_correct_item_count(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(ATOM_FIXTURE)):
            items = fetch_feed("https://feeds.example.com/atom")
        assert len(items) == 2

    def test_first_entry_fields(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(ATOM_FIXTURE)):
            items = fetch_feed("https://feeds.example.com/atom")
        assert items[0]["title"] == "First Entry"
        assert items[0]["link"] == "https://example.com/entry1"
        assert items[0]["published"] == "2026-03-09T10:00:00Z"
        assert items[0]["summary"] == "Summary of entry one."

    def test_second_entry_title(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(ATOM_FIXTURE)):
            items = fetch_feed("https://feeds.example.com/atom")
        assert items[1]["title"] == "Second Entry"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestFetchFeedErrors:
    def test_unreachable_url_raises_valueerror(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            with pytest.raises(ValueError, match="Failed to fetch feed"):
                fetch_feed("https://unreachable.example.com/feed")

    def test_malformed_xml_raises_valueerror(self):
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(b"not xml at all <<")):
            with pytest.raises(ValueError, match="Failed to parse feed"):
                fetch_feed("https://feeds.example.com/bad")

    def test_unrecognised_root_element_raises_valueerror(self):
        with patch(
            "urllib.request.urlopen",
            return_value=_mock_urlopen(b"<html><body>Not a feed</body></html>"),
        ):
            with pytest.raises(ValueError, match="Unrecognised feed format"):
                fetch_feed("https://feeds.example.com/html")


# ---------------------------------------------------------------------------
# Item cap
# ---------------------------------------------------------------------------

class TestFetchFeedCap:
    def test_caps_at_50_items_by_default(self):
        items_xml = "".join(
            f"<item><title>Item {i}</title><link>https://example.com/{i}</link>"
            f"<pubDate></pubDate><description>Desc {i}</description></item>"
            for i in range(60)
        )
        data = (
            f'<?xml version="1.0"?><rss version="2.0"><channel>{items_xml}</channel></rss>'
        ).encode()
        with patch("urllib.request.urlopen", return_value=_mock_urlopen(data)):
            items = fetch_feed("https://feeds.example.com/big")
        assert len(items) == 50
