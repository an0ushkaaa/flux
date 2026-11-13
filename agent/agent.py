"""
agent/agent.py

Core Flux trading agent powered by Claude claude-opus-4-5.
Each call to run_agent_cycle() is one complete observe → reason → act loop.
"""

import json
from datetime import datetime, timezone
from typing import Optional

import anthropic

from agent.tool_definitions import FLUX_TOOLS
from agent.tool_dispatcher import dispatch_tool
from config import ACTIVE_SKILL, ANTHROPIC_API_KEY
from memory.database import agent_decisions, get_session, trade_log
from memory.store import save_market_snapshot
from tools.coingecko import get_eth_market_data
from tools.news import format_headlines_string, get_crypto_news
from tools.skills_loader import load_skill

# ---------------------------------------------------------------------------
# Anthropic client (module-level singleton)
# ---------------------------------------------------------------------------

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_MODEL = "claude-opus-4-5"
_MAX_TOKENS = 4096

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_system_prompt(skill_text: str, cycle_number: int) -> str:
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return (
        "You are Flux, an autonomous AI crypto trading agent operating on "
        "Ethereum Sepolia testnet.\n\n"
        f"{skill_text}\n\n"
        "INSTRUCTIONS:\n"
        "- Start by gathering current market data and news\n"
        "- Search your memory for similar past market conditions\n"
        "- Check your current wallet balance\n"
        "- Make ONE trade decision: BUY, SELL, or HOLD\n"
        "- You MUST call execute_trade exactly once before finishing\n"
        "- Always provide detailed reasoning in the execute_trade call\n"
        "- Be disciplined. Do not overtrade.\n\n"
        f"Today's date and time: {now}\n"
        f"Cycle number: {cycle_number}"
    )


def _extract_final_text(content: list) -> str:
    """Pull the last text block from an assistant response."""
    for block in reversed(content):
        if hasattr(block, "type") and block.type == "text":
            return block.text
    return ""


def _extract_trade_decision(tool_calls_log: list[dict]) -> dict:
    """
    Find the execute_trade entry in the tool call log and return its key fields.
    Falls back to HOLD with empty values if no trade call is found.
    """
    for entry in reversed(tool_calls_log):
        if entry["tool"] == "execute_trade":
            inp = entry["input"]
            return {
                "action": inp.get("action", "HOLD"),
                "amount_eth": inp.get("amount_eth"),
                "reasoning": inp.get("reasoning", ""),
                "tx_hash": _parse_tx_hash(entry["result"]),
            }
    return {"action": "HOLD", "amount_eth": None, "reasoning": "", "tx_hash": None}


def _parse_tx_hash(result_str: str) -> Optional[str]:
    """Extract the tx hash line from a formatted execute_trade result string."""
    for line in result_str.splitlines():
        if "tx hash" in line.lower():
            value = line.split(":", 1)[-1].strip()
            if value and value.lower() not in ("n/a", "n/a (hold)", ""):
                return value
    return None


def _log_agent_decision(
    cycle_number: int,
    tool_calls_log: list[dict],
    action: str,
    reasoning: str,
    pnl_snapshot: Optional[float],
) -> None:
    """Persist one agent_decisions row."""
    try:
        with get_session() as conn:
            conn.execute(
                agent_decisions.insert().values(
                    timestamp=datetime.now(tz=timezone.utc),
                    cycle_number=cycle_number,
                    tool_calls_json=json.dumps(tool_calls_log),
                    final_decision=action,
                    full_reasoning=reasoning,
                    pnl_snapshot=pnl_snapshot,
                )
            )
        print(f"  [agent] Decision logged to agent_decisions.")
    except Exception as exc:
        print(f"  [agent] WARNING: failed to log agent decision: {exc}")


def _log_trade(
    action: str,
    amount_eth: Optional[float],
    price: Optional[float],
    tx_hash: Optional[str],
    reasoning: str,
) -> None:
    """Persist one trade_log row (skipped for HOLD with no tx)."""
    try:
        with get_session() as conn:
            conn.execute(
                trade_log.insert().values(
                    timestamp=datetime.now(tz=timezone.utc),
                    action=action,
                    amount_eth=amount_eth,
                    price_at_trade=price or 0.0,
                    tx_hash=tx_hash,
                    reasoning=reasoning,
                    skill_used=ACTIVE_SKILL,
                )
            )
        print(f"  [agent] Trade logged to trade_log.")
    except Exception as exc:
        print(f"  [agent] WARNING: failed to log trade: {exc}")


def _compute_pnl_snapshot(market_data: Optional[dict], balance_eth: Optional[float]) -> Optional[float]:
    """Portfolio value in USD = ETH balance × current price."""
    if market_data and balance_eth is not None:
        return round(balance_eth * market_data.get("price_usd", 0.0), 4)
    return None


# ---------------------------------------------------------------------------
# Core agent cycle
# ---------------------------------------------------------------------------

def run_agent_cycle(cycle_number: int) -> dict:
    """
    Run one complete Flux agent cycle:
      load skill → build prompt → agentic tool loop → persist results.

    Parameters
    ----------
    cycle_number:
        Monotonically increasing integer passed in by the scheduler.

    Returns
    -------
    {
        "cycle": int,
        "decision": "BUY" | "SELL" | "HOLD",
        "tx_hash": str | None,
        "reasoning": str,
        "tool_calls": int,
    }
    """
    print(f"\n{'='*60}")
    print(f"Cycle {cycle_number} starting...")
    print(f"{'='*60}")

    # ------------------------------------------------------------------
    # 1. Load active trading skill
    # ------------------------------------------------------------------
    try:
        skill_text = load_skill(ACTIVE_SKILL)
        print(f"  [agent] Skill loaded: {ACTIVE_SKILL}")
    except FileNotFoundError as exc:
        print(f"  [agent] ERROR loading skill: {exc}")
        return {
            "cycle": cycle_number,
            "decision": "HOLD",
            "tx_hash": None,
            "reasoning": f"Skill load failed: {exc}",
            "tool_calls": 0,
        }

    # ------------------------------------------------------------------
    # 2. Build system prompt
    # ------------------------------------------------------------------
    system_prompt = _build_system_prompt(skill_text, cycle_number)

    # ------------------------------------------------------------------
    # 3. Initialise message history
    # ------------------------------------------------------------------
    messages: list[dict] = [
        {
            "role": "user",
            "content": "Analyze current ETH market conditions and make a trading decision.",
        }
    ]
    tool_calls_log: list[dict] = []

    # ------------------------------------------------------------------
    # 4. Agentic tool loop
    # ------------------------------------------------------------------
    print(f"  [agent] Entering tool loop with model {_MODEL}...")

    while True:
        response = _client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=system_prompt,
            tools=FLUX_TOOLS,
            messages=messages,
        )

        # Append assistant turn to history
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            print("  [agent] Agent reached end_turn — loop complete.")
            break

        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                print(f"  Calling tool: {block.name}...")
                result = dispatch_tool(block.name, block.input)

                tool_calls_log.append(
                    {
                        "tool": block.name,
                        "input": block.input,
                        "result": result,
                    }
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )

            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason — bail safely
        print(f"  [agent] Unexpected stop_reason: {response.stop_reason}. Exiting loop.")
        break

    # ------------------------------------------------------------------
    # 5. Extract final text response
    # ------------------------------------------------------------------
    final_text = _extract_final_text(response.content)

    # ------------------------------------------------------------------
    # 6. Extract trade decision from log
    # ------------------------------------------------------------------
    trade = _extract_trade_decision(tool_calls_log)
    action: str = trade["action"]
    reasoning: str = trade["reasoning"]
    tx_hash: Optional[str] = trade["tx_hash"]
    amount_eth: Optional[float] = trade["amount_eth"]

    print(f"  Decision: {action}")
    if tx_hash:
        print(f"  Tx hash : {tx_hash}")

    # ------------------------------------------------------------------
    # 7. Save market snapshot to memory
    # ------------------------------------------------------------------
    print("  [agent] Saving market snapshot to memory...")
    try:
        market_data = get_eth_market_data()
        news_articles = get_crypto_news(currencies="ETH", num_articles=8)
        if market_data:
            save_market_snapshot(
                {
                    "eth_price_usd": market_data.get("price_usd", 0.0),
                    "market_cap": market_data.get("market_cap", 0.0),
                    "volume_24h": market_data.get("volume_24h", 0.0),
                    "price_change_24h_pct": market_data.get("price_change_24h_pct", 0.0),
                    "top_news_headlines": format_headlines_string(news_articles or []),
                }
            )
    except Exception as exc:
        print(f"  [agent] WARNING: market snapshot save failed: {exc}")

    # ------------------------------------------------------------------
    # 8. Log to agent_decisions and trade_log tables
    # ------------------------------------------------------------------
    pnl = _compute_pnl_snapshot(
        market_data if "market_data" in dir() else None,
        # Wallet balance was fetched inside the tool loop; approximate from
        # tool_calls_log if available, otherwise leave as None
        _extract_wallet_balance(tool_calls_log),
    )

    _log_agent_decision(cycle_number, tool_calls_log, action, reasoning, pnl)
    _log_trade(action, amount_eth, market_data.get("price_usd") if market_data else None, tx_hash, reasoning)

    # ------------------------------------------------------------------
    # 9. Return summary
    # ------------------------------------------------------------------
    result = {
        "cycle": cycle_number,
        "decision": action,
        "tx_hash": tx_hash,
        "reasoning": reasoning,
        "tool_calls": len(tool_calls_log),
    }

    print(f"Cycle {cycle_number} complete.")
    print(f"{'='*60}\n")
    return result


def _extract_wallet_balance(tool_calls_log: list[dict]) -> Optional[float]:
    """
    Parse the wallet balance ETH value from a get_wallet_status result string
    in the tool call log, so we can compute PnL without an extra API call.
    """
    for entry in tool_calls_log:
        if entry["tool"] != "get_wallet_status":
            continue
        for line in entry["result"].splitlines():
            if "balance" in line.lower() and "eth" in line.lower():
                # Line format: "  Balance         : 0.123456 ETH"
                try:
                    value_part = line.split(":", 1)[-1].strip()
                    return float(value_part.replace("ETH", "").strip())
                except ValueError:
                    pass
    return None
