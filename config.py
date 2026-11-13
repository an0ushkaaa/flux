import os
from dotenv import load_dotenv

load_dotenv()

# Anthropic (Claude) API
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]

# Google Gemini (embeddings)
GEMINI_API_KEY: str = os.environ["GEMINI_API_KEY"]

# Market data
COINGECKO_API_KEY: str = os.environ["COINGECKO_API_KEY"]

# On-chain data
ETHERSCAN_API_KEY: str = os.environ["ETHERSCAN_API_KEY"]

# Crypto news — sourced from free RSS feeds (CoinDesk, Cointelegraph)
# No API key required.

# Database
DATABASE_URL: str = os.environ["DATABASE_URL"]

# Wallet
WALLET_ADDRESS: str = os.environ["WALLET_ADDRESS"]
WALLET_PRIVATE_KEY: str = os.environ["WALLET_PRIVATE_KEY"]

# Blockchain RPC (Sepolia testnet)
ETH_RPC_URL: str = os.environ["ETH_RPC_URL"]

# Active trading skill (must match a filename in skills/ without .txt)
ACTIVE_SKILL: str = os.getenv("ACTIVE_SKILL", "conservative_dip_buy")
