# Flux — AI Autonomous Trading Agent

## What is Flux?

Flux is an autonomous AI-powered crypto trading agent that runs continuously, observes live Ethereum market conditions, reasons about what to do, and executes trade decisions on the Ethereum Sepolia testnet. It is not a rule-based bot with hardcoded if/else logic — it uses a large language model (Claude by Anthropic) as its brain, meaning it reads market data, news, and its own past memories, then reasons in natural language before deciding to BUY, SELL, or HOLD.

The project demonstrates a full agentic AI system with a real-time dashboard, vector-based memory, pluggable trading strategies, and on-chain transaction execution — all running autonomously on a 30-minute cycle.

---

## The Big Picture — How It Works

```
Every 30 minutes:

  Market Data (CoinGecko)  ──┐
  News Headlines (RSS)     ──┤
  Fear & Greed Index       ──┤──► Claude (claude-opus-4-5) ──► BUY / SELL / HOLD
  Wallet Status (Etherscan)──┤         ▲
  Past Memory (pgvector)   ──┘         │
                                       │
                              Trading Skill (txt file)
                              injected into system prompt
                                       │
                              Decision logged to PostgreSQL
                              Market snapshot embedded (Gemini)
                              and stored as vector in pgvector
                                       │
                              Dashboard updated (FastAPI)
```

---

## Full Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| AI Brain | Claude claude-opus-4-5 (Anthropic) | Reasoning and decision making |
| Embeddings | Gemini gemini-embedding-001 (Google) | Converting text to 3072-dim vectors |
| Vector DB | pgvector (PostgreSQL extension) | Semantic similarity search over past market snapshots |
| Database | PostgreSQL via Neon (serverless) | Storing all decisions, trades, snapshots |
| ORM | SQLAlchemy Core | Database interactions without an ORM |
| Market Data | CoinGecko API | Live ETH price, volume, market cap |
| News | CoinDesk + Cointelegraph RSS | Crypto news headlines |
| Sentiment | Alternative.me Fear & Greed Index | Market sentiment score (0-100) |
| On-chain Data | Etherscan API (V2) | Wallet balance and transaction history |
| Blockchain | Web3.py + Alchemy RPC | Signing and broadcasting Sepolia transactions |
| Scheduler | APScheduler | Running the agent every 30 minutes |
| Backend API | FastAPI | Serving dashboard data as REST endpoints |
| Frontend | Vanilla JS + HTML Canvas | Real-time dashboard, no frameworks |
| Config | python-dotenv | Loading environment variables |
| Language | Python 3.11 | Everything |

---

## Project Structure

```
flux/
  agent/
    __init__.py
    agent.py              ← core agent loop (Claude reasoning)
    tool_definitions.py   ← JSON schemas telling Claude what tools exist
    tool_dispatcher.py    ← maps Claude's tool calls to Python functions

  tools/
    __init__.py
    coingecko.py          ← ETH market data fetching
    news.py               ← RSS news + Fear & Greed sentiment
    etherscan.py          ← wallet balance + transaction history
    trader.py             ← Web3 trade execution on Sepolia
    skills_loader.py      ← loads trading strategy .txt files

  memory/
    __init__.py
    database.py           ← SQLAlchemy tables + pgvector setup
    embeddings.py         ← Gemini embedding generation
    store.py              ← RAG: save snapshots, retrieve similar contexts

  skills/
    aggressive_momentum.txt     ← aggressive trading strategy rules
    conservative_dip_buy.txt    ← conservative trading strategy rules

  dashboard/
    __init__.py
    api.py                ← FastAPI endpoints (/api/summary, /trades, etc.)
    static/
      index.html          ← full dashboard UI (single file, no frameworks)

  main.py                 ← entry point (starts dashboard + scheduler)
  scheduler.py            ← 30-min APScheduler loop
  config.py               ← all environment variables via dotenv
  requirements.txt
  .env.example
  test_tools.py           ← integration test suite
  run_once.py             ← run a single agent cycle manually
```

---

## How Each Component Works

### 1. The Agent Loop (`agent/agent.py`)

This is the core of Flux. Every 30 minutes it:

1. Loads the active trading skill (a `.txt` file) and injects it into Claude's system prompt
2. Sends an initial user message: *"Analyze current ETH market conditions and make a trading decision"*
3. Enters a **while loop** — Claude responds, calls tools, gets results, calls more tools, until it calls `execute_trade` and reaches `end_turn`
4. Every tool call is logged to `tool_calls_log`
5. After the loop ends, the decision is extracted, market snapshot is saved with embedding, and everything is written to the database

This pattern — LLM + tools in a loop — is called an **agentic loop** or **ReAct pattern** (Reason + Act).

### 2. Tool Use (Anthropic Function Calling)

Claude doesn't directly call Python functions. Instead:

- `tool_definitions.py` defines JSON schemas describing what tools exist and what parameters they take
- These schemas are passed to `client.messages.create(tools=FLUX_TOOLS)`
- Claude responds with a `tool_use` block when it wants to call a tool
- `tool_dispatcher.py` receives `(tool_name, tool_input)` and calls the right Python function
- The result is sent back to Claude as a `tool_result` message
- Claude reads the result and decides what to do next

This loop continues until Claude calls `execute_trade` and returns `stop_reason = "end_turn"`.

### 3. RAG Memory (`memory/store.py`)

RAG = Retrieval Augmented Generation. Flux uses it to give Claude long-term memory:

**Saving:** After each cycle, the market snapshot (price, volume, change, headlines) is converted to a natural language summary, embedded into a 3072-dimensional vector using Gemini, and stored in PostgreSQL with pgvector.

**Retrieving:** At the start of each cycle, Claude calls `search_memory` with a description of current conditions. This generates a query embedding, then runs a cosine similarity search (`<=>` operator) against all stored snapshots, returning the most similar past market conditions.

**Why this matters:** Claude can see what the market looked like 2 weeks ago when conditions were similar, what decision was made, and implicitly learn from that history.

### 4. Trading Skills (`skills/`)

Skills are plain `.txt` files that define trading strategy rules in natural language. They are injected directly into Claude's system prompt at the start of every cycle.

```
ACTIVE_SKILL=conservative_dip_buy  → only buys dips of -2% to -5%
ACTIVE_SKILL=aggressive_momentum   → buys breakouts with strong volume
```

Because the skill is in the system prompt, Claude's entire reasoning process is shaped by it. Switching strategies requires only changing one env var and restarting — no code changes.

### 5. Trade Execution (`tools/trader.py`)

Since Flux runs on the **Sepolia testnet** (not mainnet), actual BUY/SELL trades are simulated as **self-transfers** — the wallet sends ETH to itself. This creates a real on-chain transaction with a tx hash that proves the decision was made at a specific time, without any real money moving.

The transaction is signed locally with the private key using Web3.py and broadcast through the Alchemy RPC endpoint.

HOLD decisions create no transaction — just a log entry.

### 6. Dashboard (`dashboard/`)

FastAPI serves REST endpoints that the frontend polls:

- `GET /api/summary` — ETH price, trade counts, latest P&L
- `GET /api/decisions` — recent agent decisions with reasoning
- `GET /api/trades` — trade log
- `GET /api/pnl-chart` — time series for the chart

The frontend is a single `index.html` file with inline CSS and JS. The P&L chart is drawn on an HTML `<canvas>` element using the 2D Canvas API — no Chart.js or any library. Everything auto-refreshes every 60 seconds.

---

## Data Flow — One Complete Cycle

```
1. APScheduler triggers job() every 30 min
2. run_agent_cycle(n) starts
3. Load conservative_dip_buy.txt → inject into system prompt
4. Claude receives: "Analyze ETH and make a trading decision"
5. Claude calls get_market_data → CoinGecko returns price/volume/change
6. Claude calls get_crypto_news → RSS feeds + Fear & Greed index
7. Claude calls get_wallet_status → Etherscan returns balance + tx history
8. Claude calls search_memory("ETH dipping 3%, bearish sentiment")
   → Gemini embeds the query → pgvector finds similar past snapshots
   → Claude sees what it did last time conditions were similar
9. Claude reasons: "Conditions match dip buy criteria, wallet has ETH, memory
   shows similar dip recovered → BUY 0.02 ETH"
10. Claude calls execute_trade(action="BUY", amount_eth=0.02, reasoning="...")
    → Web3.py signs tx → Alchemy broadcasts to Sepolia → receipt returned
11. Market snapshot embedded and saved to pgvector
12. Decision logged to agent_decisions table
13. Trade logged to trade_log table
14. Dashboard updates on next poll
```

---

## Database Schema

**market_snapshots** — one row per cycle, stores market state + embedding
```
id | timestamp | eth_price_usd | market_cap | volume_24h | 
price_change_24h_pct | top_news_headlines | embedding (vector 3072)
```

**trade_log** — one row per trade decision
```
id | timestamp | action (BUY/SELL/HOLD) | amount_eth | price_at_trade |
tx_hash | reasoning | skill_used
```

**agent_decisions** — full audit log of every cycle
```
id | timestamp | cycle_number | tool_calls_json | final_decision |
full_reasoning | pnl_snapshot
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Dashboard UI |
| GET | `/api/health` | Liveness check |
| GET | `/api/summary` | ETH price, trade counts, P&L |
| GET | `/api/decisions?limit=20` | Recent agent decisions |
| GET | `/api/trades?limit=20` | Trade log |
| GET | `/api/pnl-chart` | P&L time series data |

---

## Interview Questions & Answers

### "Tell me about this project in one sentence"
Flux is an autonomous AI trading agent that uses Claude as its reasoning engine, pgvector for long-term memory, and a full-stack Python backend to observe live crypto market conditions and make trade decisions every 30 minutes on Ethereum's Sepolia testnet.

---

### "What is an agentic loop and how does Flux use it?"
An agentic loop is a pattern where an LLM runs in a while loop — it receives information, decides to call a tool, gets the result, and continues reasoning until it's ready to give a final answer. Flux implements this with Anthropic's tool use API: Claude calls tools like `get_market_data`, `search_memory`, and finally `execute_trade`, with each tool result feeding back into the conversation until Claude reaches `end_turn`.

---

### "What is RAG and why did you use it here?"
RAG stands for Retrieval Augmented Generation. Instead of relying only on what Claude knows from training, we give it access to a database of past market snapshots. Each snapshot is embedded as a vector using Gemini, stored in PostgreSQL with pgvector, and retrieved via cosine similarity search. This gives the agent long-term memory — it can recall what happened last time ETH dropped 4% with bearish sentiment, and use that context in its current decision.

---

### "What is pgvector?"
pgvector is a PostgreSQL extension that adds a `vector` data type and similarity search operators. The `<=>` operator computes cosine distance between two vectors. This lets us do nearest-neighbour search directly in SQL — no separate vector database like Pinecone needed. We store 3072-dimensional Gemini embeddings in a `vector(3072)` column and query the most similar past market conditions in a single SQL query.

---

### "Why did you use SQLAlchemy Core instead of an ORM?"
For this project, the database interactions are straightforward inserts and selects. SQLAlchemy Core gives full control over SQL without the overhead of ORM mapping, session management, and model classes. It's also more transparent — you can see exactly what SQL is being generated, which matters when debugging pgvector queries that use raw operators like `<=>`.

---

### "How does the trading skill system work?"
Trading skills are plain text files that describe strategy rules in natural language. They're injected directly into Claude's system prompt at the start of each cycle. Because Claude is an LLM, it can read and follow natural language rules — no parsing or code needed. Switching from conservative to aggressive trading is just changing one environment variable. This design separates strategy from code, making the system easily extensible.

---

### "How does trade execution work on testnet?"
Since Flux runs on Sepolia (Ethereum's testnet), actual BUY and SELL trades are simulated as self-transfers — the wallet sends a small amount of ETH back to itself. This creates a real on-chain transaction with a transaction hash, timestamp, and block confirmation, providing an immutable audit trail of every decision. Web3.py handles transaction construction, signing with the private key, and broadcasting through the Alchemy RPC endpoint.

---

### "What would it take to run this on mainnet?"
Three things: (1) point `ETH_RPC_URL` at a mainnet endpoint, (2) replace the self-transfer logic in `trader.py` with real DEX interactions (Uniswap, 1inch), and (3) add proper risk management — position sizing, circuit breakers, max loss limits. The rest of the architecture — agent loop, memory, dashboard, scheduler — works identically on mainnet.

---

### "What are the limitations of this system?"
- **No real alpha**: Market data from CoinGecko and RSS news is public and already priced in. Real edge requires proprietary data or faster execution.
- **LLM latency**: Claude takes 10-30 seconds per cycle. High-frequency trading is not possible with this architecture.
- **Hallucination risk**: Claude could reason incorrectly about market conditions. There are no hard guardrails preventing bad trades beyond the skill rules in the prompt.
- **Single asset**: Currently only tracks ETH. Extending to a portfolio requires significant changes to the data model and prompting.
- **No backtesting**: The system has no way to test strategy performance on historical data before running live.

---

### "How would you scale this?"
- Replace APScheduler with a proper job queue (Celery + Redis) for parallel multi-asset processing
- Add a Redis cache layer in front of CoinGecko/news APIs to reduce latency
- Use streaming responses from Claude to reduce time-to-first-decision
- Add a proper backtesting framework (Backtrader or Vectorbt) to validate strategies before live deployment
- Containerise with Docker and deploy to a cloud VM for 24/7 uptime

---

## Key Concepts to Know for Interviews

**Agentic AI** — AI systems that take actions in a loop, not just answer questions once

**Tool Use / Function Calling** — giving LLMs the ability to call external functions and use the results in their reasoning

**RAG (Retrieval Augmented Generation)** — augmenting LLM context with retrieved documents/data from a database

**Vector Embeddings** — converting text to high-dimensional numerical vectors that capture semantic meaning, so similar texts have similar vectors

**Cosine Similarity** — a measure of similarity between two vectors based on the angle between them (1.0 = identical direction, 0.0 = unrelated)

**pgvector** — PostgreSQL extension for storing and querying vector embeddings

**Sepolia** — Ethereum's test network, identical to mainnet but with fake ETH, used for development

**Web3.py** — Python library for interacting with the Ethereum blockchain

**APScheduler** — Python library for scheduling recurring jobs

**FastAPI** — modern Python web framework for building APIs, with automatic OpenAPI docs
