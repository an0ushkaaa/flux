"""
tools/etherscan.py

Etherscan Sepolia testnet data tool for Flux.
Docs: https://docs.etherscan.io/etherscan-v2
"""

from datetime import datetime, timezone
from typing import Optional

import requests

from config import ETHERSCAN_API_KEY, WALLET_ADDRESS

# ---------------------------------------------------------------------------
# Client setup
# ---------------------------------------------------------------------------

_BASE_URL = "https://api.etherscan.io/v2/api"
_TIMEOUT = 15  # seconds


def _get(params: dict) -> Optional[dict]:
    """
    Shared GET helper. Injects the API key, returns parsed JSON or None.
    Also surfaces Etherscan-level errors (status != "1") as printed warnings.
    """
    params = {"apikey": ETHERSCAN_API_KEY, "chainid": "11155111", **params}
    try:
        response = requests.get(_BASE_URL, params=params, timeout=_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        # Etherscan wraps errors in a 200 response with status "0"
        if str(data.get("status")) != "1":
            message = data.get("message", "unknown")
            result = data.get("result", "")
            # "No transactions found" is a normal empty state, not an error
            if "no transactions" not in str(result).lower():
                print(f"[etherscan] API error — message: {message}, result: {result}")
            return data  # still return so callers can inspect result if needed

        return data

    except requests.exceptions.HTTPError as exc:
        print(f"[etherscan] HTTP error: {exc}")
    except requests.exceptions.ConnectionError as exc:
        print(f"[etherscan] Connection error: {exc}")
    except requests.exceptions.Timeout:
        print("[etherscan] Request timed out")
    except requests.exceptions.RequestException as exc:
        print(f"[etherscan] Unexpected request error: {exc}")
    return None


def _wei_to_eth(wei: int | str) -> float:
    """Convert a wei value (int or numeric string) to ETH."""
    return int(wei) / 1e18


def _unix_to_iso(timestamp: int | str) -> str:
    """Convert a Unix timestamp to an ISO-8601 UTC string."""
    return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_wallet_eth_balance() -> Optional[float]:
    """
    Fetch the current ETH balance of WALLET_ADDRESS on Sepolia.

    Returns
    -------
    Balance in ETH as a float, or None on failure.
    """
    data = _get(
        {
            "module": "account",
            "action": "balance",
            "address": WALLET_ADDRESS,
            "tag": "latest",
        }
    )
    if not data:
        return None

    try:
        return _wei_to_eth(data["result"])
    except (KeyError, TypeError, ValueError) as exc:
        print(f"[etherscan] Failed to parse balance: {exc}")
        return None


def get_recent_transactions(limit: int = 10) -> list[dict]:
    """
    Fetch the most recent normal transactions for WALLET_ADDRESS.

    Parameters
    ----------
    limit:
        Number of transactions to return (max 10 000, Etherscan hard cap).

    Returns
    -------
    [
        {
            "hash": str,
            "timestamp": str,      # ISO-8601 UTC
            "value_eth": float,
            "direction": "IN" | "OUT",
            "status": "success" | "failed",
        },
        ...
    ]
    Empty list on failure or when the wallet has no transactions.
    """
    data = _get(
        {
            "module": "account",
            "action": "txlist",
            "address": WALLET_ADDRESS,
            "sort": "desc",
            "page": 1,
            "offset": limit,
        }
    )
    if not data:
        return []

    raw_txs = data.get("result")
    if not isinstance(raw_txs, list):
        return []

    txs: list[dict] = []
    for tx in raw_txs:
        try:
            direction = (
                "OUT" if tx["from"].lower() == WALLET_ADDRESS.lower() else "IN"
            )
            # isError: "0" = success, "1" = failed / reverted
            status = "failed" if tx.get("isError") == "1" else "success"
            txs.append(
                {
                    "hash": tx["hash"],
                    "timestamp": _unix_to_iso(tx["timeStamp"]),
                    "value_eth": _wei_to_eth(tx["value"]),
                    "direction": direction,
                    "status": status,
                }
            )
        except (KeyError, TypeError, ValueError):
            # Skip malformed entries rather than aborting the batch
            continue

    return txs


def get_portfolio_summary() -> dict:
    """
    Combine balance and recent transaction data into a high-level snapshot.

    Returns
    -------
    {
        "current_balance_eth": float,
        "total_trades_last_10": int,
        "buy_count": int,   # OUT transactions (ETH leaving wallet = a buy)
        "sell_count": int,  # IN transactions  (ETH entering wallet = a sell)
        "last_tx_hash": str,
    }
    Fields default to 0 / "" on partial failure.
    """
    balance = get_wallet_eth_balance()
    txs = get_recent_transactions(limit=10)

    buy_count = sum(1 for tx in txs if tx["direction"] == "OUT")
    sell_count = sum(1 for tx in txs if tx["direction"] == "IN")

    return {
        "current_balance_eth": balance if balance is not None else 0.0,
        "total_trades_last_10": len(txs),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "last_tx_hash": txs[0]["hash"] if txs else "",
    }


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print(f"Wallet: {WALLET_ADDRESS}")
    print("=" * 60)

    print("\n-- ETH Balance --")
    balance = get_wallet_eth_balance()
    if balance is not None:
        print(f"  {balance:.6f} ETH")
    else:
        print("  Failed to fetch balance.")

    print("\n-- Recent Transactions (last 10) --")
    txs = get_recent_transactions(limit=10)
    if txs:
        for tx in txs:
            arrow = "<--" if tx["direction"] == "IN" else "-->"
            flag = " [FAILED]" if tx["status"] == "failed" else ""
            print(
                f"  {arrow}  {tx['value_eth']:.6f} ETH"
                f"  |  {tx['timestamp']}"
                f"  |  {tx['hash'][:18]}...{flag}"
            )
    else:
        print("  No transactions found.")

    print("\n-- Portfolio Summary --")
    summary = get_portfolio_summary()
    for key, value in summary.items():
        print(f"  {key:<25} {value}")
