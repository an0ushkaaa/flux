"""
flux/scheduler.py

APScheduler-based 30-minute cron loop for the Flux trading agent.
Run directly with:  python scheduler.py
Or via the single entry point:  python main.py
"""

import time
import traceback
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from agent.agent import run_agent_cycle
from memory.database import init_db

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

cycle_counter: int = 1

# ---------------------------------------------------------------------------
# Scheduled job
# ---------------------------------------------------------------------------

def job() -> None:
    """
    One scheduler tick — runs a full agent cycle, prints a summary,
    and increments the cycle counter.

    Never raises: any exception is caught, logged, and swallowed so the
    scheduler thread stays alive for the next tick.
    """
    global cycle_counter

    current_cycle = cycle_counter
    print(
        f"\n[scheduler] *** Tick at "
        f"{datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} "
        f"— starting cycle {current_cycle} ***"
    )

    try:
        result = run_agent_cycle(current_cycle)

        print(
            f"\n[scheduler] Cycle {result['cycle']} summary:\n"
            f"  Decision   : {result['decision']}\n"
            f"  Tx hash    : {result['tx_hash'] or 'N/A'}\n"
            f"  Tool calls : {result['tool_calls']}\n"
            f"  Reasoning  : {result['reasoning'][:200]}"
            f"{'...' if len(result['reasoning']) > 200 else ''}"
        )

    except Exception:
        print(
            f"\n[scheduler] ERROR in cycle {current_cycle} — "
            "agent will retry on next tick.\n"
            + traceback.format_exc()
        )

    finally:
        cycle_counter += 1

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Initialise the database, start the scheduler, run the first cycle
    immediately, then keep the main thread alive until Ctrl-C.
    """
    print("[scheduler] Initialising database...")
    init_db()

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        job,
        trigger="interval",
        minutes=30,
        id="flux_agent_cycle",
        max_instances=1,        # never overlap if a cycle runs long
        coalesce=True,          # skip missed ticks instead of piling up
    )
    scheduler.start()
    print("[scheduler] Scheduler started — agent will run every 30 minutes.")

    # Run the first cycle immediately without waiting 30 minutes
    print("[scheduler] Running first cycle immediately on startup...")
    job()

    print("[scheduler] Entering main loop. Press Ctrl-C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[scheduler] Shutting down...")
        scheduler.shutdown(wait=False)
        print("Flux stopped.")


if __name__ == "__main__":
    main()
