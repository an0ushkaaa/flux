# Flux

Flux is an autonomous AI trading agent built on top of Claude (Anthropic). It runs on a 30-minute cycle — fetching live market data, reading crypto news, searching its own memory for similar past conditions, and making a BUY, SELL, or HOLD decision without any human input. All trades are executed on Ethereum's Sepolia testnet.

The main goal of this project was to understand how agentic AI systems work in practice — specifically the agentic loop, tool use, and RAG memory. It ended up being a full-stack project with a real-time dashboard, vector database, and on-chain transaction execution.

---

## What it does

Every 30 minutes, Flux runs this cycle automatically:

```
Fetches ETH price + volume (CoinGecko)
        ↓
Reads crypto news + fear & greed sentiment
        ↓
Checks wallet balance (Etherscan)
        ↓
Searches memory for similar past market conditions
        ↓
Claude reasons through everything...
        ↓
BUY / SELL / HOLD
        ↓
Logs decision to database → dashboard updates
```

The trading strategy is a plain text file injected into Claude's system prompt. Swapping strategies is just changing one environment variable — no code changes needed.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    python main.py                    │
├──────────────────────┬──────────────────────────────┤
│   FastAPI Dashboard  │      APScheduler (30 min)     │
│   localhost:8000     │                               │
└──────────────────────┴──────────────┬────────────────┘
                                      │
                              ┌───────▼────────┐
                              │  Agent Loop    │
                              │  (Claude)      │
                              └───────┬────────┘
              ┌───────────────────────┼───────────────────────┐
              │                       │                       │
    ┌─────────▼──────┐    ┌──────────▼──────┐    ┌──────────▼──────┐
    │   Tools        │    │    Memory        │    │   Trade         │
    │                │    │                  │    │   Execution     │
    │ • CoinGecko    │    │ • Gemini embeds  │    │                 │
    │ • RSS News     │    │ • pgvector store │    │ • Web3.py       │
    │ • Etherscan    │    │ • similarity     │    │ • Sepolia tx    │
    │ • Fear & Greed │    │   search         │    │                 │
    └────────────────┘    └──────────────────┘    └─────────────────┘
              │                       │                       │
              └───────────────────────┼───────────────────────┘
                                      │
                              ┌───────▼────────┐
                              │  PostgreSQL     │
                              │  (Neon)         │
                              │                 │
                              │ • decisions     │
                              │ • trade log     │
                              │ • snapshots     │
                              └────────────────┘
```

---

## The Agentic Loop

This is the core of the project. Claude runs in a while loop, deciding which tools to call and in what order:

1. Claude receives: *"Analyze ETH and make a trading decision"*
2. Calls `get_market_data` → gets price, volume, 24h change
3. Calls `get_crypto_news` → gets headlines and sentiment score
4. Calls `get_wallet_status` → checks available balance
5. Calls `search_memory` → retrieves similar past market conditions
6. Reasons through everything → calls `execute_trade`
7. Loop ends

Claude decides what to call and when — the code just executes whatever Claude requests and returns the result. This is the ReAct pattern (Reason → Act → Reason → Act) which is the foundation of most production AI agents today.

---

## RAG Memory

After every cycle, Flux saves a snapshot of the market to PostgreSQL as a 3072-dimensional vector embedding (via Gemini). Before each decision, Claude searches those past snapshots for similar market conditions using cosine similarity via pgvector.

This gives the agent persistent memory across cycles — it can reference what happened the last time ETH dropped 3% with bearish sentiment, and factor that into the current decision.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| AI reasoning | Claude claude-opus-4-5 (Anthropic) |
| Embeddings | Gemini gemini-embedding-001 (Google) |
| Vector search | pgvector (PostgreSQL extension) |
| Database | PostgreSQL via Neon |
| Market data | CoinGecko API |
| News | CoinDesk + Cointelegraph RSS |
| Sentiment | Alternative.me Fear & Greed Index |
| On-chain data | Etherscan API |
| Blockchain | Web3.py + Alchemy RPC (Sepolia) |
| Backend API | FastAPI |
| Scheduler | APScheduler |
| ORM | SQLAlchemy Core |
| Config | python-dotenv |

---

## Project Structure

```
flux/
  agent/
    agent.py              ← core agentic loop
    tool_definitions.py   ← Claude tool schemas
    tool_dispatcher.py    ← routes tool calls to Python functions

  tools/
    coingecko.py          ← market data fetching
    news.py               ← RSS news + sentiment
    etherscan.py          ← wallet data
    trader.py             ← Web3 trade execution
    skills_loader.py      ← loads strategy files

  memory/
    database.py           ← SQLAlchemy tables + pgvector setup
    embeddings.py         ← Gemini embedding generation
    store.py              ← save and retrieve market snapshots

  skills/
    conservative_dip_buy.txt
    aggressive_momentum.txt

  dashboard/
    api.py                ← FastAPI endpoints
    static/index.html     ← dashboard UI (single file, no frameworks)

  main.py                 ← entry point
  scheduler.py            ← 30-minute loop
  config.py               ← environment variables
  test_tools.py           ← integration test suite
  run_once.py             ← run a single cycle manually
```

---

## Running It

```bash
# 1. copy env template and fill in your keys
cp .env.example .env

# 2. install dependencies
pip install -r requirements.txt

# 3. verify everything is working
python test_tools.py

# 4. run a single cycle to test
python run_once.py

# 5. start the full system
python main.py
```

Dashboard available at `http://localhost:8000`

---

## Switching Strategies

Change `ACTIVE_SKILL` in `.env`:

```
ACTIVE_SKILL=conservative_dip_buy   # buys dips, preserves capital
ACTIVE_SKILL=aggressive_momentum    # rides uptrends, higher risk
```

Restart and the new strategy takes effect. Strategies are plain `.txt` files in `skills/` — you can write your own without touching any code.

---

## Keys Required

| Key | Where to get it |
|-----|----------------|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `GEMINI_API_KEY` | aistudio.google.com |
| `COINGECKO_API_KEY` | coingecko.com/api |
| `ETHERSCAN_API_KEY` | etherscan.io/apis |
| `DATABASE_URL` | neon.tech |
| `ETH_RPC_URL` | alchemy.com (Sepolia) |
| `WALLET_ADDRESS` | MetaMask, Sepolia network |
| `WALLET_PRIVATE_KEY` | MetaMask → Account Details → Export Private Key |
