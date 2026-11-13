"""
flux/main.py

Single entry point for the Flux autonomous trading agent.

Starts:
  - FastAPI dashboard server (background thread, port 8000)
  - APScheduler agent loop      (main thread, every 30 minutes)

Usage:
    python main.py
"""

import threading

from config import ACTIVE_SKILL
from dashboard.api import run_dashboard
from scheduler import main as run_scheduler


def _print_banner() -> None:
    print("=" * 50)
    print("FLUX - AI Trading Agent")
    print("Dashboard: http://localhost:8000")
    print("Scheduler: every 30 minutes")
    print("Active Skill:", ACTIVE_SKILL)
    print("=" * 50)


def main() -> None:
    _print_banner()

    # Start the FastAPI dashboard in a daemon background thread so it exits
    # automatically when the main thread (scheduler) is stopped.
    dashboard_thread = threading.Thread(
        target=run_dashboard,
        kwargs={"host": "0.0.0.0", "port": 8000},
        name="flux-dashboard",
        daemon=True,
    )
    dashboard_thread.start()

    # Run the scheduler on the main thread — blocks until Ctrl-C.
    run_scheduler()


if __name__ == "__main__":
    main()
