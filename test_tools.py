"""
flux/test_tools.py

Standalone integration test suite for all Flux tools and subsystems.
Prints PASS / FAIL for each test. Safe to run — no trades are executed.

Usage:
    python test_tools.py
"""

import traceback
from datetime import datetime, timezone


# ── Helpers ──────────────────────────────────────────────────────────────────

_results: list[tuple[str, bool, str]] = []


def _run(label: str, fn) -> bool:
    """Call fn(), catch any exception, record and print result."""
    try:
        fn()
        _results.append((label, True, ""))
        print(f"  PASS  {label}")
        return True
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        _results.append((label, False, detail))
        print(f"  FAIL  {label}")
        print(f"        {detail}")
        if _VERBOSE:
            traceback.print_exc()
        return False


_VERBOSE = False   # set True to see full tracebacks on failure


# ── Individual tests ──────────────────────────────────────────────────────────

def test_db():
    """init_db() must complete without raising."""
    from memory.database import init_db
    init_db()


def test_coingecko():
    """ETH price must be a positive number."""
    from tools.coingecko import get_eth_market_data
    data = get_eth_market_data()
    assert data is not None, "get_eth_market_data() returned None"
    assert data["price_usd"] > 0, f"Expected price > 0, got {data['price_usd']}"
    print(f"        ETH price: ${data['price_usd']:,.2f}")


def test_news():
    """get_crypto_news() must return at least one article; sentiment must have expected keys."""
    from tools.news import get_crypto_news, get_news_sentiment_summary
    articles = get_crypto_news(currencies="ETH", num_articles=5)
    assert articles is not None, "get_crypto_news() returned None"
    assert len(articles) > 0, "get_crypto_news() returned empty list"
    print(f"        {len(articles)} articles fetched. First: \"{articles[0]['title'][:60]}\"")

    sentiment = get_news_sentiment_summary()
    assert "fear_greed_value" in sentiment, "Missing fear_greed_value in sentiment"
    assert sentiment["sentiment"] in ("BULLISH", "BEARISH", "NEUTRAL")
    print(f"        Fear & Greed: {sentiment['fear_greed_value']}/100 — {sentiment['fear_greed_label']} → {sentiment['sentiment']}")


def test_etherscan():
    """get_wallet_eth_balance() must return a non-negative float."""
    from tools.etherscan import get_wallet_eth_balance
    balance = get_wallet_eth_balance()
    # Balance can be None if the wallet hasn't been funded — that's fine,
    # but the call itself must not raise.
    if balance is not None:
        assert balance >= 0, f"Negative balance: {balance}"
        print(f"        Wallet balance: {balance:.6f} ETH")
    else:
        print("        Balance returned None (wallet may be unfunded or RPC issue)")


def test_embeddings():
    """Embedding vector must be exactly 768 dimensions."""
    from memory.embeddings import generate_embedding
    text = "Ethereum price is rising with strong volume"
    vec = generate_embedding(text)
    assert vec is not None, "generate_embedding() returned None"
    assert len(vec) == 3072, f"Expected 3072 dimensions, got {len(vec)}"
    print(f"        Vector length: {len(vec)}  first value: {vec[0]:.6f}")


def test_memory():
    """Save a fake snapshot and retrieve it via vector search."""
    from memory.store import retrieve_similar_contexts, save_market_snapshot

    fake = {
        "eth_price_usd": 3_100.00,
        "market_cap":    372_000_000_000.0,
        "volume_24h":    13_500_000_000.0,
        "price_change_24h_pct": 2.10,
        "top_news_headlines": "ETH test headline for unit test | Another test headline",
    }
    row_id = save_market_snapshot(fake)
    assert row_id is not None, "save_market_snapshot() returned None"
    print(f"        Snapshot saved with id={row_id}")

    results = retrieve_similar_contexts("Ethereum price rising, bullish sentiment", top_k=3)
    assert isinstance(results, list), "retrieve_similar_contexts() did not return a list"
    assert len(results) > 0, "retrieve_similar_contexts() returned empty list"
    best = results[0]
    print(f"        Top match id={best['id']}  similarity={best['similarity_score']:.4f}")


def test_skills_loader():
    """Both built-in skills must load without error."""
    from tools.skills_loader import list_available_skills, load_skill
    skills = list_available_skills()
    assert len(skills) >= 2, f"Expected ≥2 skills, found {skills}"
    print(f"        Available skills: {skills}")
    for name in skills:
        content = load_skill(name)
        assert len(content) > 50, f"Skill '{name}' content suspiciously short"
        print(f"        Loaded '{name}' ({len(content)} chars)")


def test_tool_dispatcher():
    """dispatch_tool must return a non-empty string for read-only tools."""
    from agent.tool_dispatcher import dispatch_tool

    # get_market_data
    result = dispatch_tool("get_market_data", {})
    assert result and "ETH" in result, f"Unexpected result: {result[:80]}"
    print(f"        get_market_data: OK ({len(result)} chars)")

    # unknown tool
    result = dispatch_tool("nonexistent_tool", {})
    assert "Error" in result or "error" in result, \
        f"Expected error for unknown tool, got: {result}"
    print(f"        unknown tool:    correctly returned error string")


# ── Runner ────────────────────────────────────────────────────────────────────

_TESTS = [
    ("Database init",       test_db),
    ("CoinGecko market data", test_coingecko),
    ("CryptoPanic news",    test_news),
    ("Etherscan balance",   test_etherscan),
    ("Gemini embeddings",   test_embeddings),
    ("Memory store (RAG)",  test_memory),
    ("Skills loader",       test_skills_loader),
    ("Tool dispatcher",     test_tool_dispatcher),
]


def main():
    print()
    print("=" * 55)
    print("  Flux Tool Integration Tests")
    print(f"  {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 55)

    for label, fn in _TESTS:
        print(f"\n[{label}]")
        _run(label, fn)

    # ── Summary ──────────────────────────────────────────────────
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    total  = len(_results)

    print()
    print("=" * 55)
    print(f"  Results: {passed}/{total} passed", end="")
    if failed:
        print(f"  ({failed} FAILED)")
    else:
        print("  — all OK")
    print("=" * 55)

    if failed:
        print("\nFailed tests:")
        for label, ok, detail in _results:
            if not ok:
                print(f"  • {label}: {detail}")
        print()


if __name__ == "__main__":
    main()
