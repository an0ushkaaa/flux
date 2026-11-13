# Flux

so I built this AI agent that trades crypto on its own. like fully autonomous — it wakes up every 30 minutes, checks the market, reads the news, thinks about what to do, and either buys, sells, or holds. no human in the loop.

the whole point was to learn how agentic AI actually works in practice, not just theory. and honestly it ended up being one of the most interesting things i've built.

---

## what it actually does

every 30 minutes flux does this on its own:

```
checks ETH price + volume (CoinGecko)
        ↓
reads crypto news + fear & greed index
        ↓
checks wallet balance (Etherscan)
        ↓
searches its own memory for similar past market conditions
        ↓
Claude thinks through everything...
        ↓
BUY / SELL / HOLD
        ↓
logs everything to the database + dashboard updates
```

the cool part is claude doesn't just follow hardcoded rules. it actually reasons through the data, compares it to what happened in the past, and makes a judgment call. the trading strategy (aggressive vs conservative) is just a text file injected into the system prompt — so swapping strategies is literally changing one env variable.

---

## the architecture

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

## the agentic loop (the interesting bit)

this is what i actually learned building this. the agent isn't a chain of function calls — it's claude in a while loop deciding what to do next:

1. claude gets the initial message: *"analyze ETH and make a trading decision"*
2. claude decides it needs market data → calls `get_market_data`
3. gets the result → decides it needs news → calls `get_crypto_news`
4. gets that → searches memory → calls `search_memory`
5. now has enough context → calls `execute_trade`
6. loop ends

claude drives the whole thing. the code just responds to whatever claude asks for. this is the ReAct pattern (reason → act → reason → act) which is basically how every serious AI agent is built right now.

---

## RAG memory

every cycle, flux saves a snapshot of the market to postgres as a vector embedding (3072 dimensions via gemini). before claude makes a decision, it searches those past snapshots for similar market conditions using cosine similarity.

so claude can literally see: *"last time ETH dropped 3% with bearish news, here's what happened"*

this is what gives the agent memory across cycles. without this it would start fresh every 30 minutes with no context.

---

## tech stack

| thing | what it does |
|-------|-------------|
| Claude claude-opus-4-5 | the brain — reasoning and decisions |
| Gemini gemini-embedding-001 | converts market snapshots to vectors |
| pgvector | semantic similarity search in postgres |
| PostgreSQL (Neon) | stores everything |
| CoinGecko API | live ETH price, volume, market cap |
| CoinDesk + Cointelegraph RSS | crypto news headlines |
| Alternative.me | fear & greed index for sentiment |
| Etherscan API | wallet balance + on-chain history |
| Web3.py + Alchemy | signing + broadcasting transactions |
| FastAPI | dashboard REST API |
| APScheduler | runs the agent every 30 min |
| SQLAlchemy Core | database interactions |
| python-dotenv | environment config |

---

## project structure

```
flux/
  agent/
    agent.py              ← the main loop
    tool_definitions.py   ← tells claude what tools exist
    tool_dispatcher.py    ← routes tool calls to python functions

  tools/
    coingecko.py          ← market data
    news.py               ← rss + sentiment
    etherscan.py          ← wallet data
    trader.py             ← web3 trade execution
    skills_loader.py      ← loads strategy files

  memory/
    database.py           ← sqlalchemy tables + pgvector
    embeddings.py         ← gemini embedding calls
    store.py              ← save + retrieve market snapshots

  skills/
    conservative_dip_buy.txt
    aggressive_momentum.txt

  dashboard/
    api.py                ← fastapi endpoints
    static/index.html     ← the whole dashboard UI

  main.py                 ← entry point
  scheduler.py            ← 30 min loop
  config.py               ← env vars
  test_tools.py           ← integration tests
  run_once.py             ← run one cycle manually
```

---

## running it

```bash
# 1. copy env and fill in your keys
cp .env.example .env

# 2. install deps
pip install -r requirements.txt

# 3. test everything works
python test_tools.py

# 4. run one cycle manually first
python run_once.py

# 5. start the full thing
python main.py
```

dashboard runs at `http://localhost:8000`

---

## switching trading strategies

in `.env`:
```
ACTIVE_SKILL=conservative_dip_buy   # cautious, buys dips
ACTIVE_SKILL=aggressive_momentum    # rides uptrends
```

restart and it picks up the new strategy. the strategies are just `.txt` files in `skills/` — you can write your own.

---

## what works / what doesn't

**works:**
- full AI reasoning loop with tool use
- RAG memory across cycles
- live market data + news
- dashboard with P&L chart + decision log
- auto runs every 30 min

**doesn't work yet:**
- actual trade execution (need Sepolia testnet ETH — faucets are annoying)
- only tracks ETH for now
- no backtesting

---

## keys you need

get these and put them in `.env`:

- `ANTHROPIC_API_KEY` → console.anthropic.com
- `GEMINI_API_KEY` → aistudio.google.com
- `COINGECKO_API_KEY` → coingecko.com/api
- `ETHERSCAN_API_KEY` → etherscan.io/apis
- `DATABASE_URL` → neon.tech (free postgres with pgvector)
- `ETH_RPC_URL` → alchemy.com (free, use Sepolia)
- `WALLET_ADDRESS` + `WALLET_PRIVATE_KEY` → MetaMask, new account, Sepolia network
