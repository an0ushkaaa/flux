"""
flux/run_once.py

Manually trigger a single Flux agent cycle without starting the scheduler.
Use this to test the full observe → reason → act loop during development.

Usage:
    python run_once.py
    python run_once.py --cycle 5   # specify a cycle number (optional)

No trades will be faked — if the agent decides to BUY or SELL it will
broadcast a real Sepolia testnet transaction.
"""

import argparse
import sys
from datetime import datetime, timezone

from agent.agent import run_agent_cycle
from memory.database import init_db


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a single Flux agent cycle and exit."
    )
    parser.add_argument(
        "--cycle",
        type=int,
        default=0,
        help="Cycle number to pass to the agent (default: 0)",
    )
    args = parser.parse_args()

    print()
    print("=" * 55)
    print("  Flux — Single Cycle Run")
    print(f"  {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"  Cycle number: {args.cycle}")
    print("=" * 55)

    # Ensure tables exist before the agent tries to write to them
    print("\nInitialising database...")
    try:
        init_db()
    except Exception as exc:
        print(f"ERROR: Database initialisation failed: {exc}")
        sys.exit(1)

    # Run one agent cycle
    try:
        result = run_agent_cycle(cycle_number=args.cycle)
    except Exception as exc:
        print(f"\nERROR: Agent cycle raised an unhandled exception: {exc}")
        raise

    # Print final summary
    print()
    print("=" * 55)
    print("  Cycle complete — summary")
    print("=" * 55)
    print(f"  Cycle     : {result['cycle']}")
    print(f"  Decision  : {result['decision']}")
    print(f"  Tx hash   : {result['tx_hash'] or 'N/A (HOLD)'}")
    print(f"  Tool calls: {result['tool_calls']}")
    print(f"  Reasoning :")
    # Wrap reasoning at 70 chars for readability
    reasoning = result.get("reasoning", "")
    for i in range(0, max(len(reasoning), 1), 70):
        print(f"    {reasoning[i:i+70]}")
    print()


if __name__ == "__main__":
    main()
