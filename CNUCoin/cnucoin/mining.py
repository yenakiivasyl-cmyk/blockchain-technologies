"""Майнінг CNUCoin — Proof-of-Work (ЛР №2).

Алгоритм:
  1. Майнер (IsMiner = 1) бере першу за датою/часом непідтверджену транзакцію.
  2. Перевіряє її хеш-образ та ЕЦП відправника.
  3. Конкатенує TAHash + BlockChainHash попереднього блоку + Nonce (Nonce = 0, 1, 2, ...)
     і обчислює SHA-256, доки хеш-образ не почнеться з `difficulty` нулів (Difficulty Target).
  4. Записує BlockChainHash та Nonce у BlockChainTable і в транзакцію, підписує блок ЕЦП.
  5. Транзакція позначається підтвердженою; кошти зараховуються/списуються;
     майнер отримує винагороду — REWARD_PERCENT % від суми (нові монети).
  6. Новий блок одночасно підтверджує попередній (кошти з нього стають доступними).
"""
from __future__ import annotations

import sqlite3
import time

from . import crypto, members
from .db import COINBASE_ADDRESS, now
from .transactions import last_mined_block, pending_transactions, verify_transaction

DEFAULT_DIFFICULTY = 1   # за умовою ЛР №2: блок має починатися з нуля
REWARD_PERCENT = 5       # винагорода майнеру, % від суми транзакції
TRACE_ATTEMPTS = 6       # скільки перших спроб зберігати для протоколу


class MiningError(RuntimeError):
    pass


def block_payload(ta_hash: str, prev_hash: str, nonce: int) -> str:
    return f"{ta_hash}{prev_hash}{nonce}"


def proof_of_work(ta_hash: str, prev_hash: str, difficulty: int) -> dict:
    """Перебирає Nonce, доки SHA-256 не почнеться з `difficulty` нулів."""
    target = "0" * difficulty
    trace = []
    nonce = 0
    started = time.perf_counter()
    while True:
        block_hash = crypto.sha256(block_payload(ta_hash, prev_hash, nonce))
        if nonce < TRACE_ATTEMPTS:
            trace.append((nonce, block_hash))
        if block_hash.startswith(target):
            break
        nonce += 1
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "hash": block_hash,
        "nonce": nonce,
        "attempts": nonce + 1,
        "elapsed_ms": elapsed_ms,
        "trace": trace,
    }


def mine_next(conn: sqlite3.Connection, miner_id: str, difficulty: int = DEFAULT_DIFFICULTY) -> dict | None:
    """Видобуває один блок. Повертає None, якщо черга транзакцій порожня."""
    miner = members.get_member(conn, miner_id)
    if miner is None:
        raise MiningError("Майнера не зареєстровано")
    if not miner["IsMiner"]:
        raise MiningError(f"Учасник «{miner['Alias']}» не має права на майнінг (IsMiner = 0)")

    queue = pending_transactions(conn)
    if not queue:
        return None
    tx = queue[0]

    checks = verify_transaction(conn, tx)
    if not all(checks.values()):
        raise MiningError(f"Транзакцію #{tx['TAID']} відхилено: {checks}")

    prev = last_mined_block(conn)
    pow_result = proof_of_work(tx["TAHash"], prev["BlockChainHash"], difficulty)
    block_hash = pow_result["hash"]
    block_assign = crypto.sign(members.private_key(conn, miner_id), block_hash)
    reward = tx["TASum"] * REWARD_PERCENT // 100
    mined_at = now()

    with conn:
        block_id = conn.execute("SELECT BlockID FROM BlockChainTable WHERE TAID = ?", (tx["TAID"],)).fetchone()[0]
        conn.execute(
            """UPDATE BlockChainTable
               SET MinerID = ?, DateTime = ?, PrevHash = ?, BlockChainHash = ?, Nonce = ?,
                   Difficulty = ?, Attempts = ?, MiningTimeMs = ?, Reward = ?, BlockAssign = ?, IsMined = 1
               WHERE BlockID = ?""",
            (miner_id, mined_at, prev["BlockChainHash"], block_hash, pow_result["nonce"], difficulty,
             pow_result["attempts"], pow_result["elapsed_ms"], reward, block_assign, block_id),
        )
        conn.execute("UPDATE TransactionsTable SET Nonce = ?, TAApproved = 1 WHERE TAID = ?",
                     (pow_result["nonce"], tx["TAID"]))
        wallet_rows = [
            (tx["TAFrom"], tx["TAFrom"], tx["TATo"], -tx["TASum"], "TRANSFER"),
            (tx["TATo"], tx["TAFrom"], tx["TATo"], tx["TASum"], "TRANSFER"),
        ]
        if reward:
            wallet_rows.append((miner_id, COINBASE_ADDRESS, miner_id, reward, "REWARD"))
        conn.executemany(
            """INSERT INTO EWalletTable (CNUCoinID, TADate, TAFrom, TATo, TASum, Kind, TAID, BlockID)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(owner, mined_at, frm, to, amount, kind, tx["TAID"], block_id)
             for owner, frm, to, amount, kind in wallet_rows],
        )

    return {
        "BlockID": block_id,
        "TAID": tx["TAID"],
        "MinerID": miner_id,
        "MinerAlias": miner["Alias"],
        "PrevBlockID": prev["BlockID"],
        "PrevHash": prev["BlockChainHash"],
        "TAHash": tx["TAHash"],
        "BlockChainHash": block_hash,
        "Nonce": pow_result["nonce"],
        "Attempts": pow_result["attempts"],
        "MiningTimeMs": pow_result["elapsed_ms"],
        "Difficulty": difficulty,
        "Reward": reward,
        "BlockAssign": block_assign,
        "Trace": pow_result["trace"],
        "DateTime": mined_at,
        # блок, який цим майнінгом отримав підтвердження (ЛР №2, п. 5)
        "ConfirmedBlockID": prev["BlockID"] if prev["BlockID"] != 0 else None,
    }


def mined_blocks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT b.*, m.Alias AS MinerAlias, t.TASum, t.TAFrom, t.TATo,
                  f.Alias AS FromAlias, r.Alias AS ToAlias
           FROM BlockChainTable b
           LEFT JOIN CnuCoinMembersTable m ON m.CNUCoinID = b.MinerID
           LEFT JOIN TransactionsTable t ON t.TAID = b.TAID
           LEFT JOIN CnuCoinMembersTable f ON f.CNUCoinID = t.TAFrom
           LEFT JOIN CnuCoinMembersTable r ON r.CNUCoinID = t.TATo
           WHERE b.IsMined = 1 ORDER BY b.BlockID"""
    ).fetchall()
