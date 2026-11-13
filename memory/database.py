"""
memory/database.py

PostgreSQL connection and table definitions for Flux.
Uses SQLAlchemy Core (no ORM) with psycopg2 and the pgvector extension.
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.engine import Engine

from config import DATABASE_URL

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True)
metadata = MetaData()

# ---------------------------------------------------------------------------
# Table definitions
# ---------------------------------------------------------------------------

market_snapshots = Table(
    "market_snapshots",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", TIMESTAMP(timezone=True), nullable=False),
    Column("eth_price_usd", Float),
    Column("market_cap", Float),
    Column("volume_24h", Float),
    Column("price_change_24h_pct", Float),
    Column("top_news_headlines", Text),
    # embedding column is managed separately as vector(3072) — see _create_embedding_column()
)

trade_log = Table(
    "trade_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", TIMESTAMP(timezone=True), nullable=False),
    Column("action", String(10), nullable=False),   # BUY | SELL | HOLD
    Column("amount_eth", Float, nullable=True),
    Column("price_at_trade", Float, nullable=False),
    Column("tx_hash", String(66), nullable=True),
    Column("reasoning", Text),
    Column("skill_used", String(128)),
)

agent_decisions = Table(
    "agent_decisions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("timestamp", TIMESTAMP(timezone=True), nullable=False),
    Column("cycle_number", Integer, nullable=False),
    Column("tool_calls_json", Text),               # JSON string
    Column("final_decision", String(10)),           # BUY | SELL | HOLD
    Column("full_reasoning", Text),
    Column("pnl_snapshot", Float),
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _enable_pgvector(conn) -> None:
    """Enable the pgvector extension if it isn't already present."""
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def _create_embedding_column(conn) -> None:
    """
    Ensure market_snapshots.embedding is a vector(3072) column.

    SQLAlchemy's create_all() doesn't understand the pgvector type, so the
    column is omitted from the Table definition and managed here instead.
    If a stale varchar placeholder column exists from a previous run it is
    dropped first, then the proper vector column is added.
    """
    conn.execute(
        text(
            """
            DO $$
            BEGIN
                -- Drop if it exists as the wrong type (e.g. varchar placeholder)
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name  = 'market_snapshots'
                      AND column_name = 'embedding'
                      AND udt_name   != 'vector'
                ) THEN
                    ALTER TABLE market_snapshots DROP COLUMN embedding;
                END IF;

                -- Add as proper vector type if not present
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name  = 'market_snapshots'
                      AND column_name = 'embedding'
                ) THEN
                    ALTER TABLE market_snapshots
                    ADD COLUMN embedding vector(3072);
                END IF;
            END
            $$;
            """
        )
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db() -> None:
    """
    Enable pgvector, create all tables (if they don't exist), and verify
    the connection.  Call once at application startup.
    """
    with engine.begin() as conn:
        # 1. pgvector extension
        _enable_pgvector(conn)

        # 2. Create tables (embedding column is a plain TEXT placeholder here;
        #    it will be converted / replaced by the ALTER below)
        metadata.create_all(conn)

        # 3. Replace the placeholder column with the real vector(768) type
        _create_embedding_column(conn)

    print("Database initialized successfully")


@contextmanager
def get_session() -> Generator:
    """
    Context manager that yields a SQLAlchemy connection.

    Usage::

        with get_session() as conn:
            result = conn.execute(select(market_snapshots))
    """
    with engine.begin() as conn:
        yield conn
