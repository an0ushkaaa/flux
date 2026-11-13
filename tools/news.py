"""
tools/news.py

Crypto news and sentiment for Flux.

Sources (both 100% free, no API key required):
  - RSS feeds: CoinDesk + Cointelegraph  (news headlines)
  - Alternative.me Fear & Greed Index    (sentiment score)
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import requests

_TIMEOUT = 15  # seconds

# RSS feeds — add or swap any standard RSS URL here
_RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
]

_FNG_URL = "https://api.alternative.me/fng/"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_rss(url: str) -> list[dict]:
    """
    Fetch and parse one RSS feed. Returns a list of article dicts.
    Silently skips malformed items rather than aborting the whole feed.
    """
    try:
        response = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": "Flux/1.0"})
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except requests.exceptions.RequestException as exc:
        print(f"[news] RSS fetch failed ({url}): {exc}")
        return []
    except ET.ParseError as exc:
        print(f"[news] RSS parse error ({url}): {exc}")
        return []

    articles: list[dict] = []
    for item in root.iter("item"):
        try:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            pub   = item.findtext("pubDate") or ""

            # Parse RFC-2822 date → ISO-8601 UTC string
            try:
                dt = parsedate_to_datetime(pub).astimezone(timezone.utc)
                published_at = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                published_at = ""

            # Derive source name from URL hostname
            from urllib.parse import urlparse
            source = urlparse(url).hostname or url

            if title and link:
                articles.append({
                    "title":        title,
                    "url":          link,
                    "published_at": published_at,
                    "source":       source,
                })
        except Exception:
            continue

    return articles


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_crypto_news(
    currencies: str = "ETH",
    num_articles: int = 10,
) -> list[dict]:
    """
    Fetch recent crypto news from CoinDesk and Cointelegraph RSS feeds.

    Parameters
    ----------
    currencies:
        Keyword(s) to filter headlines by (case-insensitive).
        Defaults to "ETH" — only returns articles mentioning Ethereum/ETH.
        Pass an empty string to return all headlines regardless of coin.
    num_articles:
        Maximum number of articles to return.

    Returns
    -------
    [{"title": str, "url": str, "published_at": str, "source": str}, ...]
    Empty list on failure.
    """
    # Collect from all feeds
    all_articles: list[dict] = []
    for feed_url in _RSS_FEEDS:
        all_articles.extend(_fetch_rss(feed_url))

    # Filter by keyword if provided
    keywords = [kw.strip().lower() for kw in currencies.split(",") if kw.strip()]
    if keywords:
        all_articles = [
            a for a in all_articles
            if any(kw in a["title"].lower() for kw in keywords)
        ]

    # Sort newest-first and cap
    all_articles.sort(key=lambda a: a["published_at"], reverse=True)
    return all_articles[:num_articles]


def get_news_sentiment_summary(currencies: str = "ETH") -> dict:
    """
    Fetch the Alternative.me Crypto Fear & Greed Index.

    Score ranges:
      0–24  Extreme Fear  → BEARISH
      25–44 Fear          → BEARISH
      45–55 Neutral       → NEUTRAL
      56–74 Greed         → BULLISH
      75–100 Extreme Greed → BULLISH

    Returns
    -------
    {
        "fear_greed_value": int,
        "fear_greed_label": str,
        "sentiment": "BULLISH" | "BEARISH" | "NEUTRAL",
    }
    Returns neutral defaults on failure so the agent can still run.
    """
    try:
        response = requests.get(_FNG_URL, params={"limit": 1}, timeout=_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        entry = data["data"][0]
        value = int(entry["value"])
        label = entry["value_classification"]

        if value <= 44:
            sentiment = "BEARISH"
        elif value <= 55:
            sentiment = "NEUTRAL"
        else:
            sentiment = "BULLISH"

        return {
            "fear_greed_value": value,
            "fear_greed_label": label,
            "sentiment":        sentiment,
        }

    except requests.exceptions.RequestException as exc:
        print(f"[news] Fear & Greed fetch failed: {exc}")
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        print(f"[news] Fear & Greed parse error: {exc}")

    # Safe fallback — neutral so the agent isn't blocked
    return {"fear_greed_value": 50, "fear_greed_label": "Neutral", "sentiment": "NEUTRAL"}


def format_headlines_string(articles: list[dict]) -> str:
    """
    Join article titles into a pipe-delimited string for embedding /
    storage in market_snapshots.top_news_headlines.

    Returns empty string if articles is empty or None.
    """
    if not articles:
        return ""
    return " | ".join(a["title"] for a in articles if a.get("title"))


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("RSS News — ETH (top 10)")
    print("=" * 60)
    articles = get_crypto_news(currencies="ETH", num_articles=10)
    if articles:
        for i, a in enumerate(articles, start=1):
            print(f"\n  {i}. {a['title']}")
            print(f"     Source    : {a['source']}")
            print(f"     Published : {a['published_at']}")
    else:
        print("  No ETH articles found (try empty string for all articles).")

    print()
    print("=" * 60)
    print("Alternative.me Fear & Greed Index")
    print("=" * 60)
    s = get_news_sentiment_summary()
    print(f"  Value     : {s['fear_greed_value']} / 100")
    print(f"  Label     : {s['fear_greed_label']}")
    print(f"  Sentiment : {s['sentiment']}")

    print()
    print("=" * 60)
    print("Formatted Headlines String")
    print("=" * 60)
    hl = format_headlines_string(articles)
    if hl:
        import textwrap
        print(textwrap.fill(hl, width=80, subsequent_indent="  "))
    else:
        print("  (empty — try broader filter)")
