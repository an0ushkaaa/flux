"""
agent/tool_dispatcher.py

Maps Claude's tool_use block requests to real Python function calls
and returns formatted human-readable strings for Claude to reason over.
"""

from memory.store import build_memory_context_string
from tools.coingecko import get_eth_market_data
from tools.etherscan import get_portfolio_summary
from tools.news import get_crypto_news, get_news_sentiment_summary
from tools.trader import execute_buy, execute_hold, execute_sell

# ---------------------------------------------------------------------------
# Individual formatters
# ---------------------------------------------------------------------------

def _fmt_market_data(tool_input: dict) -> str:
    data = get_eth_market_data()
    if data is None:
        return "Market data unavailable — CoinGecko request failed."

    return (
        f"ETH MARKET DATA\n"
        f"  Price          : ${data['price_usd']:>12,.2f}\n"
        f"  Market cap     : ${data['market_cap']:>18,.0f}\n"
        f"  24h volume     : ${data['volume_24h']:>18,.0f}\n"
        f"  24h change     : {data['price_change_24h_pct']:>+.2f}%\n"
        f"  24h high       : ${data['high_24h']:>12,.2f}\n"
        f"  24h low        : ${data['low_24h']:>12,.2f}"
    )


def _fmt_crypto_news(tool_input: dict) -> str:
    num_articles = int(tool_input.get("num_articles", 8))
    articles = get_crypto_news(currencies="ETH", num_articles=num_articles)
    sentiment = get_news_sentiment_summary(currencies="ETH")

    lines = ["ETH NEWS & SENTIMENT"]

    # Sentiment block
    lines.append(
        f"  Fear & Greed      : {sentiment.get('fear_greed_value', '?')}/100"
        f"  — {sentiment.get('fear_greed_label', 'N/A')}"
        f"  → {sentiment.get('sentiment', 'N/A')}"
    )

    # Headlines block
    if articles:
        lines.append(f"  Top {len(articles)} headlines:")
        for i, article in enumerate(articles, start=1):
            source = article.get("source", "")
            title = article.get("title", "(no title)")
            published = article.get("published_at", "")[:10]  # YYYY-MM-DD
            lines.append(f"    {i:>2}. [{published}] {title}  ({source})")
    else:
        lines.append("  No headlines returned.")

    return "\n".join(lines)


def _fmt_wallet_status(tool_input: dict) -> str:
    summary = get_portfolio_summary()

    last_tx = summary.get("last_tx_hash") or "none"
    if last_tx and last_tx != "none" and len(last_tx) > 20:
        last_tx = f"{last_tx[:10]}...{last_tx[-8:]}"

    return (
        f"WALLET STATUS (Sepolia)\n"
        f"  Balance         : {summary.get('current_balance_eth', 0):.6f} ETH\n"
        f"  Trades (last 10): {summary.get('total_trades_last_10', 0)}\n"
        f"  OUT (buys)      : {summary.get('buy_count', 0)}\n"
        f"  IN  (sells)     : {summary.get('sell_count', 0)}\n"
        f"  Last tx hash    : {last_tx}"
    )


def _fmt_search_memory(tool_input: dict) -> str:
    query = tool_input.get("query", "")
    if not query:
        return "Error: search_memory requires a non-empty 'query' parameter."
    return build_memory_context_string(query)


def _fmt_execute_trade(tool_input: dict) -> str:
    action = tool_input.get("action", "").upper()
    reasoning = tool_input.get("reasoning", "(no reasoning provided)")
    amount_eth = tool_input.get("amount_eth")

    if action == "BUY":
        if amount_eth is None:
            return "Error: execute_trade with action=BUY requires 'amount_eth'."
        result = execute_buy(float(amount_eth))

    elif action == "SELL":
        if amount_eth is None:
            return "Error: execute_trade with action=SELL requires 'amount_eth'."
        result = execute_sell(float(amount_eth))

    elif action == "HOLD":
        result = execute_hold()

    else:
        return f"Error: unknown trade action '{action}'. Must be BUY, SELL, or HOLD."

    # Format result
    if not result.get("success"):
        return (
            f"TRADE FAILED\n"
            f"  Action  : {action}\n"
            f"  Error   : {result.get('error', 'unknown error')}"
        )

    tx_hash = result.get("tx_hash") or "N/A (HOLD)"
    amount = result.get("amount_eth")
    amount_str = f"{float(amount):.6f} ETH" if amount is not None else "N/A"
    gas_used = result.get("gas_used", "N/A")

    return (
        f"TRADE EXECUTED\n"
        f"  Action    : {action}\n"
        f"  Amount    : {amount_str}\n"
        f"  Tx hash   : {tx_hash}\n"
        f"  Gas used  : {gas_used}\n"
        f"  Reasoning : {reasoning}"
    )


# ---------------------------------------------------------------------------
# Dispatcher registry
# ---------------------------------------------------------------------------

_DISPATCH_TABLE: dict = {
    "get_market_data":  _fmt_market_data,
    "get_crypto_news":  _fmt_crypto_news,
    "get_wallet_status": _fmt_wallet_status,
    "search_memory":    _fmt_search_memory,
    "execute_trade":    _fmt_execute_trade,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def dispatch_tool(tool_name: str, tool_input: dict) -> str:
    """
    Route a Claude tool_use request to the correct Python function and
    return a formatted string result for Claude to read.

    Parameters
    ----------
    tool_name:
        The ``name`` field from Claude's tool_use content block.
    tool_input:
        The ``input`` dict from Claude's tool_use content block.

    Returns
    -------
    A human-readable string. Never raises — exceptions are caught and
    returned as error strings so Claude can reason about the failure.
    """
    handler = _DISPATCH_TABLE.get(tool_name)

    if handler is None:
        return f"Error: unknown tool '{tool_name}'."

    try:
        return handler(tool_input)
    except Exception as exc:
        return f"Tool '{tool_name}' failed: {exc}"
