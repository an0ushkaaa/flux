"""
tools/trader.py

Ethereum trade executor for Flux — Sepolia testnet ONLY.

WARNING: This module is configured exclusively for the Sepolia testnet.
         Never point ETH_RPC_URL at a mainnet endpoint.
"""

from typing import Optional

from web3 import Web3
from web3.exceptions import ContractLogicError, TimeExhausted, Web3Exception

from config import ETH_RPC_URL, WALLET_ADDRESS, WALLET_PRIVATE_KEY

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _checksum_address(address: str) -> str:
    """Return the EIP-55 checksum form of an address."""
    return Web3.to_checksum_address(address)


def _build_tx(w3: Web3, amount_eth: float) -> dict:
    """
    Build a self-transfer transaction dict.
    Gas price is fetched fresh each time to avoid stale values.
    """
    checksum_addr = _checksum_address(WALLET_ADDRESS)
    return {
        "from": checksum_addr,
        "to": checksum_addr,
        "value": w3.to_wei(amount_eth, "ether"),
        "gas": 21_000,
        "gasPrice": w3.eth.gas_price,
        "nonce": w3.eth.get_transaction_count(checksum_addr),
        "chainId": w3.eth.chain_id,   # prevents replay across networks
    }


def _sign_and_send(w3: Web3, tx: dict) -> dict:
    """
    Sign a raw transaction with WALLET_PRIVATE_KEY and broadcast it.
    Waits up to 120 s for the receipt and returns a result dict.
    Returns {"success": False, "error": ...} on any failure.
    """
    try:
        signed = w3.eth.account.sign_transaction(tx, private_key=WALLET_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        return {
            "success": True,
            "tx_hash": tx_hash.hex(),
            "amount_eth": w3.from_wei(tx["value"], "ether"),
            "gas_used": receipt.gasUsed,
        }
    except TimeExhausted as exc:
        return {"success": False, "error": f"Transaction timed out waiting for receipt: {exc}"}
    except ContractLogicError as exc:
        return {"success": False, "error": f"Contract logic error: {exc}"}
    except Web3Exception as exc:
        return {"success": False, "error": f"Web3 error: {exc}"}
    except Exception as exc:
        return {"success": False, "error": f"Unexpected error: {exc}"}


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def get_web3_connection() -> Web3:
    """
    Create and verify a Web3 connection to ETH_RPC_URL (Sepolia).

    Returns
    -------
    A connected Web3 instance.

    Raises
    ------
    ConnectionError
        If the node is unreachable or does not respond to is_connected().
    """
    w3 = Web3(Web3.HTTPProvider(ETH_RPC_URL))
    if not w3.is_connected():
        raise ConnectionError(
            f"Could not connect to Ethereum node at '{ETH_RPC_URL}'. "
            "Check that ETH_RPC_URL is set correctly and the node is reachable."
        )
    return w3


def get_current_balance() -> Optional[float]:
    """
    Return the current ETH balance of WALLET_ADDRESS in ETH.

    Returns
    -------
    Balance as a float (e.g. 0.5 for 0.5 ETH), or None on failure.
    """
    try:
        w3 = get_web3_connection()
        checksum_addr = _checksum_address(WALLET_ADDRESS)
        balance_wei = w3.eth.get_balance(checksum_addr)
        return float(w3.from_wei(balance_wei, "ether"))
    except ConnectionError as exc:
        print(f"[trader] get_current_balance: {exc}")
        return None
    except Web3Exception as exc:
        print(f"[trader] get_current_balance Web3 error: {exc}")
        return None
    except Exception as exc:
        print(f"[trader] get_current_balance unexpected error: {exc}")
        return None


def execute_buy(amount_eth: float) -> dict:
    """
    Simulate a BUY on Sepolia by sending a self-transfer of `amount_eth`.

    The trade is recorded on-chain via the transaction hash; the BUY label
    is a logical distinction logged by Flux, not enforced on-chain.

    Parameters
    ----------
    amount_eth:
        Amount of ETH to "buy" (self-transfer value).

    Returns
    -------
    {
        "success": True,
        "tx_hash": str,
        "amount_eth": float,
        "action": "BUY",
        "gas_used": int,
    }
    or {"success": False, "error": str} on failure.
    """
    try:
        w3 = get_web3_connection()
        tx = _build_tx(w3, amount_eth)
        result = _sign_and_send(w3, tx)
        if result["success"]:
            result["action"] = "BUY"
        return result
    except ConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error": f"Unexpected error in execute_buy: {exc}"}


def execute_sell(amount_eth: float) -> dict:
    """
    Simulate a SELL on Sepolia by sending a self-transfer of `amount_eth`.

    Identical to execute_buy at the transaction level — the SELL label
    is a logical distinction logged by Flux, not enforced on-chain.

    Parameters
    ----------
    amount_eth:
        Amount of ETH to "sell" (self-transfer value).

    Returns
    -------
    {
        "success": True,
        "tx_hash": str,
        "amount_eth": float,
        "action": "SELL",
        "gas_used": int,
    }
    or {"success": False, "error": str} on failure.
    """
    try:
        w3 = get_web3_connection()
        tx = _build_tx(w3, amount_eth)
        result = _sign_and_send(w3, tx)
        if result["success"]:
            result["action"] = "SELL"
        return result
    except ConnectionError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "error": f"Unexpected error in execute_sell: {exc}"}


def execute_hold() -> dict:
    """
    Record a HOLD decision — no transaction is broadcast.

    Returns
    -------
    {"success": True, "tx_hash": None, "amount_eth": None, "action": "HOLD"}
    """
    return {
        "success": True,
        "tx_hash": None,
        "amount_eth": None,
        "action": "HOLD",
    }


# ---------------------------------------------------------------------------
# Standalone test  — balance check only, no transactions sent
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 55)
    print("Flux trader — Sepolia testnet connection check")
    print("=" * 55)

    # 1. Verify connectivity
    try:
        w3 = get_web3_connection()
        chain_id = w3.eth.chain_id
        block = w3.eth.block_number
        print(f"  Connected   : yes")
        print(f"  Chain ID    : {chain_id}  (Sepolia = 11155111)")
        print(f"  Latest block: {block:,}")
    except ConnectionError as exc:
        print(f"  Connected   : NO — {exc}")

    print()

    # 2. Wallet balance
    print(f"  Wallet      : {WALLET_ADDRESS}")
    balance = get_current_balance()
    if balance is not None:
        print(f"  Balance     : {balance:.6f} ETH")
    else:
        print("  Balance     : failed to fetch")

    print()
    print("  execute_hold() preview:")
    print(" ", execute_hold())
