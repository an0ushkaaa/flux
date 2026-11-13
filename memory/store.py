"""
memory/store.py

RAG memory system for Flux.
Handles saving market snapshots with embeddings and retrieving
similar historical contexts to inject into agent prompts.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, text

from memory.database import agent_decisions, get_session, market_snapshots
from memory.embeddings import generate_embedding, generate_query_embedding

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _snapshot_to_text(snapshot: dict) -> str:
    """
    Convert a market snapshot dict into a natural-language summary suitable
    for embedding. Consistent phrasing improves vector space alignment.
    """
    return (
        f"ETH price: ${snapshot.get('eth_price_usd', 0):,.2f}. "
        f"Market cap: ${snapshot.get('market_cap', 0):,.0f}. "
        f"24h volume: ${snapshot.get('volume_24h', 0):,.0f}. "
        f"24h change: {snapshot.get('price_change_24h_pct', 0):.2f}%. "
        f"News: {snapshot.get('top_news_headlines', '')}"
    )


def _row_to_dict(row) -> dict:
    """Convert a SQLAlchemy Row to a plain dict."""
    return dict(row._mapping)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def save_market_snapshot(snapshot: dict) -> Optional[int]:
    """
    Embed and persist a market snapshot to the database.

    Parameters
    ----------
    snapshot:
        Dict with keys: eth_price_usd, market_cap, volume_24h,
        price_change_24h_pct, top_news_headlines.

    Returns
    -------
    The inserted row id, or None on failure.
    """
    summary_text = _snapshot_to_text(snapshot)
    embedding = generate_embedding(summary_text)

    if embedding is None:
        print("[store] save_market_snapshot: embedding generation failed — aborting save.")
        return None

    # Format the vector as a Postgres literal: '[0.1, 0.2, ...]'
    embedding_literal = "[" + ",".join(str(v) for v in embedding) + "]"

    try:
        with get_session() as conn:
            result = conn.execute(
                text(
                    """
                    INSERT INTO market_snapshots
                        (timestamp, eth_price_usd, market_cap, volume_24h,
                         price_change_24h_pct, top_news_headlines, embedding)
                    VALUES
                        (:ts, :price, :mcap, :vol, :chg, :headlines,
                         CAST(:vec AS vector))
                    RETURNING id
                    """
                ),
                {
                    "ts": _now_utc(),
                    "price": snapshot.get("eth_price_usd"),
                    "mcap": snapshot.get("market_cap"),
                    "vol": snapshot.get("volume_24h"),
                    "chg": snapshot.get("price_change_24h_pct"),
                    "headlines": snapshot.get("top_news_headlines", ""),
                    "vec": embedding_literal,
                },
            )
            row_id: int = result.scalar_one()
            print(f"[store] Snapshot saved — id={row_id}")
            return row_id

    except Exception as exc:
        print(f"[store] save_market_snapshot DB error: {exc}")
        return None


def retrieve_similar_contexts(
    query_text: str,
    top_k: int = 5,
) -> list[dict]:
    """
    Find the most semantically similar past market snapshots using
    pgvector cosine distance (<=>).

    Parameters
    ----------
    query_text:
        Free-form description of the current market state or question.
    top_k:
        Number of nearest neighbours to return.

    Returns
    -------
    List of snapshot dicts sorted by ascending cosine distance (most
    similar first), each with an extra "similarity_score" key in [0, 1].
    Empty list on failure.
    """
    query_vec = generate_query_embedding(query_text)
    if query_vec is None:
        print("[store] retrieve_similar_contexts: query embedding failed.")
        return []

    query_literal = "[" + ",".join(str(v) for v in query_vec) + "]"

    try:
        with get_session() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        id,
                        timestamp,
                        eth_price_usd,
                        market_cap,
                        volume_24h,
                        price_change_24h_pct,
                        top_news_headlines,
                        (embedding <=> CAST(:vec AS vector)) AS distance
                    FROM market_snapshots
                    WHERE embedding IS NOT NULL
                    ORDER BY distance ASC
                    LIMIT :k
                    """
                ),
                {"vec": query_literal, "k": top_k},
            ).fetchall()

        contexts: list[dict] = []
        for row in rows:
            entry = _row_to_dict(row)
            distance = float(entry.pop("distance", 1.0))
            # Cosine distance ∈ [0, 2] → similarity ∈ [-1, 1]; clamp to [0, 1]
            entry["similarity_score"] = round(max(0.0, 1.0 - distance), 4)
            contexts.append(entry)

        return contexts

    except Exception as exc:
        print(f"[store] retrieve_similar_contexts DB error: {exc}")
        return []


def get_recent_decisions(limit: int = 5) -> list[dict]:
    """
    Fetch the most recent agent decisions from the database.

    Parameters
    ----------
    limit:
        Maximum number of rows to return.

    Returns
    -------
    List of dicts with keys: timestamp, final_decision, full_reasoning,
    pnl_snapshot. Empty list on failure.
    """
    try:
        with get_session() as conn:
            rows = conn.execute(
                select(
                    agent_decisions.c.timestamp,
                    agent_decisions.c.final_decision,
                    agent_decisions.c.full_reasoning,
                    agent_decisions.c.pnl_snapshot,
                )
                .order_by(agent_decisions.c.timestamp.desc())
                .limit(limit)
            ).fetchall()

        return [_row_to_dict(row) for row in rows]

    except Exception as exc:
        print(f"[store] get_recent_decisions DB error: {exc}")
        return []


def build_memory_context_string(query: str) -> str:
    """
    Build a formatted memory block to inject into the agent's system prompt.

    Retrieves similar historical market conditions via vector search and the
    most recent agent decisions, then formats them as readable text.

    Parameters
    ----------
    query:
        Description of the current market state used to drive the
        similarity search.

    Returns
    -------
    A multi-line string ready to be prepended to an LLM prompt.
    """
    similar = retrieve_similar_contexts(query, top_k=5)
    decisions = get_recent_decisions(limit=5)

    # --- Similar market conditions block ---
    if similar:
        context_lines = []
        for i, ctx in enumerate(similar, start=1):
            ts = ctx.get("timestamp", "unknown time")
            score = ctx.get("similarity_score", 0.0)
            price = ctx.get("eth_price_usd", 0)
            chg = ctx.get("price_change_24h_pct", 0)
            headlines = ctx.get("top_news_headlines", "")
            context_lines.append(
                f"  [{i}] {ts}  (similarity: {score:.2%})\n"
                f"      ETH ${price:,.2f} | 24h change: {chg:.2f}%\n"
                f"      News: {headlines[:120]}{'...' if len(headlines) > 120 else ''}"
            )
        contexts_block = "\n".join(context_lines)
    else:
        contexts_block = "  No similar past conditions found."

    # --- Recent decisions block ---
    if decisions:
        decision_lines = []
        for d in decisions:
            ts = d.get("timestamp", "unknown time")
            decision = d.get("final_decision", "N/A")
            pnl = d.get("pnl_snapshot")
            pnl_str = f"${pnl:,.4f}" if pnl is not None else "N/A"
            reasoning = d.get("full_reasoning", "")
            decision_lines.append(
                f"  {ts}  →  {decision}  (PnL snapshot: {pnl_str})\n"
                f"    Reasoning: {reasoning[:160]}{'...' if len(reasoning) > 160 else ''}"
            )
        decisions_block = "\n".join(decision_lines)
    else:
        decisions_block = "  No past decisions recorded yet."

    return (
        "SIMILAR PAST MARKET CONDITIONS:\n"
        f"{contexts_block}\n\n"
        "RECENT DECISIONS:\n"
        f"{decisions_block}"
    )


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from memory.database import init_db

    print("Initialising database...")
    init_db()

    fake_snapshot = {
        "eth_price_usd": 3_241.55,
        "market_cap": 389_500_000_000.0,
        "volume_24h": 14_200_000_000.0,
        "price_change_24h_pct": 3.74,
        "top_news_headlines": (
            "Ethereum ETF inflows hit record high | "
            "Layer-2 TVL surpasses $40B | "
            "Fed signals rate pause — risk assets rally"
        ),
    }

    print("\n-- Saving fake snapshot --")
    row_id = save_market_snapshot(fake_snapshot)
    print(f"   Inserted id: {row_id}")

    print("\n-- Retrieving similar contexts --")
    query = "ETH price rising, positive market sentiment, strong volume"
    results = retrieve_similar_contexts(query, top_k=3)
    for r in results:
        print(
            f"   id={r['id']}  score={r['similarity_score']:.4f}"
            f"  price=${r['eth_price_usd']:,.2f}"
        )

    print("\n-- Memory context string (preview) --")
    ctx_str = build_memory_context_string(query)
    print(ctx_str)
