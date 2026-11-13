"""
dashboard/api.py

FastAPI backend that exposes Flux agent data for the dashboard frontend.
"""

from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from sqlalchemy import func, select, text

from memory.database import agent_decisions, get_session, market_snapshots, trade_log

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Flux Dashboard API",
    description="Real-time data API for the Flux autonomous trading agent.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the static dashboard at /
_STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

@app.get("/", include_in_schema=False)
def root():
    """Serve the dashboard HTML at the root URL."""
    return FileResponse(_STATIC_DIR / "index.html")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row) -> dict:
    """Convert a SQLAlchemy Row to a JSON-serialisable dict."""
    d = dict(row._mapping)
    # Coerce datetime objects to ISO strings so FastAPI can serialise them
    for key, value in d.items():
        if isinstance(value, datetime):
            d[key] = value.isoformat()
    return d


def _db_error(exc: Exception, context: str) -> HTTPException:
    return HTTPException(
        status_code=500,
        detail=f"Database error in {context}: {exc}",
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    """Liveness check — returns ok and the current UTC timestamp."""
    return {
        "status": "ok",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


@app.get("/api/summary")
def summary() -> dict:
    """
    High-level dashboard summary:
    - Latest ETH price from most recent market snapshot
    - Trade counts broken down by action
    - Latest P&L snapshot from the most recent agent decision
    """
    try:
        with get_session() as conn:

            # Latest ETH price
            latest_snapshot = conn.execute(
                select(market_snapshots.c.eth_price_usd, market_snapshots.c.timestamp)
                .order_by(market_snapshots.c.timestamp.desc())
                .limit(1)
            ).fetchone()

            eth_price = float(latest_snapshot.eth_price_usd) if latest_snapshot else None
            price_ts = latest_snapshot.timestamp.isoformat() if latest_snapshot else None

            # Trade counts
            total_trades = conn.execute(
                select(func.count()).select_from(trade_log)
            ).scalar() or 0

            buy_count = conn.execute(
                select(func.count()).select_from(trade_log)
                .where(trade_log.c.action == "BUY")
            ).scalar() or 0

            sell_count = conn.execute(
                select(func.count()).select_from(trade_log)
                .where(trade_log.c.action == "SELL")
            ).scalar() or 0

            hold_count = conn.execute(
                select(func.count()).select_from(trade_log)
                .where(trade_log.c.action == "HOLD")
            ).scalar() or 0

            # Latest P&L
            latest_decision = conn.execute(
                select(agent_decisions.c.pnl_snapshot)
                .order_by(agent_decisions.c.timestamp.desc())
                .limit(1)
            ).fetchone()

            pnl = float(latest_decision.pnl_snapshot) if latest_decision and latest_decision.pnl_snapshot is not None else None

        return {
            "eth_price_usd": eth_price,
            "price_timestamp": price_ts,
            "total_trades": total_trades,
            "buy_count": buy_count,
            "sell_count": sell_count,
            "hold_count": hold_count,
            "latest_pnl_snapshot": pnl,
        }

    except Exception as exc:
        raise _db_error(exc, "/api/summary") from exc


@app.get("/api/decisions")
def decisions(limit: int = Query(default=20, ge=1, le=200)) -> list[dict]:
    """
    Return the most recent agent decisions, newest first.

    Query params
    ------------
    limit : int (1–200, default 20)
    """
    try:
        with get_session() as conn:
            rows = conn.execute(
                select(
                    agent_decisions.c.id,
                    agent_decisions.c.timestamp,
                    agent_decisions.c.cycle_number,
                    agent_decisions.c.final_decision,
                    agent_decisions.c.full_reasoning,
                    agent_decisions.c.pnl_snapshot,
                )
                .order_by(agent_decisions.c.timestamp.desc())
                .limit(limit)
            ).fetchall()

        return [_row_to_dict(row) for row in rows]

    except Exception as exc:
        raise _db_error(exc, "/api/decisions") from exc


@app.get("/api/trades")
def trades(limit: int = Query(default=20, ge=1, le=200)) -> list[dict]:
    """
    Return the most recent trade log entries, newest first.

    Query params
    ------------
    limit : int (1–200, default 20)
    """
    try:
        with get_session() as conn:
            rows = conn.execute(
                select(
                    trade_log.c.id,
                    trade_log.c.timestamp,
                    trade_log.c.action,
                    trade_log.c.amount_eth,
                    trade_log.c.price_at_trade,
                    trade_log.c.tx_hash,
                    trade_log.c.reasoning,
                    trade_log.c.skill_used,
                )
                .order_by(trade_log.c.timestamp.desc())
                .limit(limit)
            ).fetchall()

        return [_row_to_dict(row) for row in rows]

    except Exception as exc:
        raise _db_error(exc, "/api/trades") from exc


@app.get("/api/pnl-chart")
def pnl_chart() -> list[dict]:
    """
    Return the full P&L time series for charting, oldest first.
    Rows where pnl_snapshot is NULL are excluded.
    """
    try:
        with get_session() as conn:
            rows = conn.execute(
                select(
                    agent_decisions.c.timestamp,
                    agent_decisions.c.pnl_snapshot,
                )
                .where(agent_decisions.c.pnl_snapshot.isnot(None))
                .order_by(agent_decisions.c.timestamp.asc())
            ).fetchall()

        return [
            {
                "timestamp": row.timestamp.isoformat(),
                "pnl": float(row.pnl_snapshot),
            }
            for row in rows
        ]

    except Exception as exc:
        raise _db_error(exc, "/api/pnl-chart") from exc


# ---------------------------------------------------------------------------
# Programmatic server launcher
# ---------------------------------------------------------------------------

def run_dashboard(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start the Flux dashboard API server using uvicorn."""
    uvicorn.run(app, host=host, port=port)
