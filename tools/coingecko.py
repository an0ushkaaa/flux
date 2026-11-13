"""
tools/coingecko.py

CoinGecko API wrapper for Flux.
Docs: https://docs.coingecko.com/reference/introduction
"""

import json
from datetime import datetime, timezone
from typing import Optional

import requests

from config import COINGECKO_API_KEY

# ---------------------------------------------------------------------------
# Client setup
# ---------------------------------------------------------------------------

_BASE_URL = "https://api.coingecko.com/api/v3"
_HEADERS = {
    "accept": "application/json",
    "x-cg-demo-api-key": COINGECKO_API_KEY,
}
_TIMEOUT = 15  # seconds


def _get(endpoint: str, params: dict) -> Optional[dict | list]:
    """Shared GET helper. Returns parsed JSON or None on any error."""
    url = f"{_BASE_URL}{endpoint}"
    try:
        response = requests.get(url, headers=_HEADERS, params=params, timeout=_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as exc:
        print(f"[coingecko] HTTP error calling {endpoint}: {exc}")
    except requests.exceptions.ConnectionError as exc:
        print(f"[coingecko] Connection error calling {endpoint}: {exc}")
    except requests.exceptions.Timeout:
        print(f"[coingecko] Request timed out calling {endpoint}")
    except requests.exceptions.RequestException as exc:
        print(f"[coingecko] Unexpected request error calling {endpoint}: {exc}")
    return None


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_eth_market_data() -> Optional[dict]:
    """
    Fetch current Ethereum market data.

    Returns
    -------
    {
        "price_usd": float,
        "market_cap": float,
        "volume_24h": float,
        "price_change_24h_pct": float,
        "high_24h": float,
        "low_24h": float,
    }
    or None if the request fails.
    """
    data = _get(
        "/coins/markets",
        params={"vs_currency": "usd", "ids": "ethereum"},
    )
    if not data:
        return None

    try:
        coin = data[0]
        return {
            "price_usd": float(coin["current_price"]),
            "market_cap": float(coin["market_cap"]),
            "volume_24h": float(coin["total_volume"]),
            "price_change_24h_pct": float(coin["price_change_percentage_24h"]),
            "high_24h": float(coin["high_24h"]),
            "low_24h": float(coin["low_24h"]),
        }
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        print(f"[coingecko] Failed to parse market data: {exc}")
        return None


def get_eth_price_history(days: int = 7) -> Optional[list[dict]]:
    """
    Fetch daily ETH/USD closing prices for the last `days` days.

    Returns
    -------
    [{"date": "YYYY-MM-DD", "price": float}, ...]
    or None if the request fails.

    Notes
    -----
    The /market_chart endpoint returns timestamps in milliseconds UTC.
    When days <= 90 the API returns hourly granularity; we deduplicate to
    one entry per calendar day (last price of each day).
    """
    data = _get(
        "/coins/ethereum/market_chart",
        params={"vs_currency": "usd", "days": days},
    )
    if not data:
        return None

    try:
        prices_raw: list[list] = data["prices"]  # [[timestamp_ms, price], ...]

        # Deduplicate: keep the last reading for each calendar day
        daily: dict[str, float] = {}
        for ts_ms, price in prices_raw:
            date_str = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime(
                "%Y-%m-%d"
            )
            daily[date_str] = float(price)  # later entry overwrites earlier

        # Return sorted ascending, capped to `days` entries
        history = [
            {"date": date, "price": price}
            for date, price in sorted(daily.items())
        ]
        return history[-days:]  # guard against off-by-one from API

    except (KeyError, TypeError, ValueError) as exc:
        print(f"[coingecko] Failed to parse price history: {exc}")
        return None


def get_trending_coins() -> Optional[list[str]]:
    """
    Fetch the top 5 trending coins on CoinGecko.

    Returns
    -------
    ["Bitcoin", "Ethereum", ...]   (coin names, not symbols)
    or None if the request fails.
    """
    data = _get("/search/trending", params={})
    if not data:
        return None

    try:
        coins = data["coins"][:5]
        return [entry["item"]["name"] for entry in coins]
    except (KeyError, IndexError, TypeError) as exc:
        print(f"[coingecko] Failed to parse trending coins: {exc}")
        return None


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 55)
    print("ETH Market Data")
    print("=" * 55)
    market = get_eth_market_data()
    if market:
        for key, value in market.items():
            print(f"  {key:<28} {value:,.4f}")

    print()
    print("=" * 55)
    print("ETH Price History (last 7 days)")
    print("=" * 55)
    history = get_eth_price_history(days=7)
    if history:
        for entry in history:
            print(f"  {entry['date']}   ${entry['price']:>12,.2f}")

    print()
    print("=" * 55)
    print("Trending Coins (top 5)")
    print("=" * 55)
    trending = get_trending_coins()
    if trending:
        for i, name in enumerate(trending, start=1):
            print(f"  {i}. {name}")
