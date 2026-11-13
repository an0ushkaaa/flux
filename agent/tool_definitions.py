"""
agent/tool_definitions.py

Anthropic tool schema definitions for the Flux trading agent.
Claude uses these schemas to decide which tools to call and with
what arguments during each reasoning cycle.
"""

FLUX_TOOLS: list[dict] = [
    {
        "name": "get_market_data",
        "description": (
            "Fetch current ETH price, market cap, volume and 24h price change "
            "from CoinGecko. Call this at the start of every cycle to get a "
            "fresh market snapshot before making any decision."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_crypto_news",
        "description": (
            "Fetch latest ETH crypto news headlines and overall market sentiment "
            "(BULLISH/BEARISH/NEUTRAL). Use the sentiment alongside price data "
            "to judge market mood before deciding to BUY, SELL, or HOLD."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "num_articles": {
                    "type": "integer",
                    "description": "Number of news articles to fetch.",
                    "default": 8,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_wallet_status",
        "description": (
            "Get current ETH wallet balance and recent transaction history on "
            "Sepolia testnet. Use this to check available funds before placing "
            "a trade and to review recent activity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "search_memory",
        "description": (
            "Search past market snapshots and agent decisions that are "
            "semantically similar to a query. Use this to recall what the agent "
            "did in similar past market conditions and whether those decisions "
            "were profitable. Always search memory before executing a trade."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Description of current market conditions to search for "
                        "similar past contexts. Be specific — include price "
                        "direction, sentiment, and volume signals."
                    ),
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "execute_trade",
        "description": (
            "Execute a trade on Ethereum Sepolia testnet. Use HOLD if the "
            "signals are mixed, weak, or if insufficient funds are available. "
            "Always call get_market_data, get_crypto_news, get_wallet_status, "
            "and search_memory before calling this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["BUY", "SELL", "HOLD"],
                    "description": (
                        "Trade action to execute. BUY and SELL are self-transfers "
                        "on Sepolia that log the decision on-chain. HOLD records "
                        "the decision without sending a transaction."
                    ),
                },
                "amount_eth": {
                    "type": "number",
                    "description": (
                        "Amount of ETH to trade. Required when action is BUY or "
                        "SELL. Must not exceed current wallet balance. Omit or "
                        "set to null when action is HOLD."
                    ),
                },
                "reasoning": {
                    "type": "string",
                    "description": (
                        "Detailed explanation of why this trade decision was made. "
                        "Include the market signals, news sentiment, memory context, "
                        "and skill rules that led to this conclusion. This is stored "
                        "permanently in the agent_decisions table."
                    ),
                },
            },
            "required": ["action", "reasoning"],
        },
    },
]
