"""Формування транзакцій CNUCoin (ЛР №1, п. 2 та п. 4 практичної частини).

Алгоритм створення транзакції:
  1. Заповнюються поля транзакції: автор, дата, TAID, From, To, сума.
  2. З BlockChainTable береться BlockChainHash та Nonce останнього видобутого блоку
     (для першої транзакції це нулі генезис-блоку).
  3. Усі поля (крім TAApproved) конкатенуються, причому замість TAHash та Nonce
     підставляються BlockChainHash та Nonce з BlockChainTable.
  4. Від отриманої конструкції обчислюється SHA-256 -> TAHash.
  5. TAHash записується в TransactionsTable та в BlockChainHash нового рядка
     BlockChainTable (кандидат у блок, IsMined = 0).
  6. TAHash підписується ЕЦП відправника -> TASign.
  7. Транзакція чекає на підтвердження майнерами (ЛР №2).
"""
from __future__ import annotations

import sqlite3

from . import crypto, members
from .db import now


class TransactionError(ValueError):
    pass


def transaction_payload(author: str, ta_date: str, taid: int, ta_from: str, ta_to: str,
                        ta_sum: int, chain_hash: str, chain_nonce: int) -> str:
    """Конкатенація полів транзакції у порядку TransactionsTable."""
    return "|".join(str(v) for v in (author, ta_date, taid, ta_from, ta_to, ta_sum, chain_hash, chain_nonce))


def last_mined_block(conn: sqlite3.Connection) -> sqlite3.Row:
    return conn.execute(
        "SELECT * FROM BlockChainTable WHERE IsMined = 1 ORDER BY BlockID DESC LIMIT 1"
    ).fetchone()


def create_transaction(conn: sqlite3.Connection, sender_id: str, recipient_id: str,
                       amount_cents: int) -> dict:
    """Створює, хешує та підписує транзакцію. Повертає всі проміжні значення."""
    if sender_id == recipient_id:
        raise TransactionError("Не можна переказати кошти самому собі")
    if amount_cents <= 0:
        raise TransactionError("Сума має бути додатною")
    if members.get_member(conn, sender_id) is None:
        raise TransactionError("Відправника не зареєстровано")
    if members.get_member(conn, recipient_id) is None:
        raise TransactionError("Отримувача не зареєстровано")

    spendable = members.balances(conn, sender_id)["spendable"]
    if spendable < amount_cents:
        raise TransactionError(
            f"Недостатньо доступних коштів: доступно {spendable / 100:.2f} CNU, потрібно {amount_cents / 100:.2f} CNU"
        )

    with conn:
        chain = last_mined_block(conn)
        taid = conn.execute("SELECT COALESCE(MAX(TAID), 0) + 1 FROM TransactionsTable").fetchone()[0]
        ta_date = now()
        payload = transaction_payload(sender_id, ta_date, taid, sender_id, recipient_id,
                                      amount_cents, chain["BlockChainHash"], chain["Nonce"])
        ta_hash = crypto.sha256(payload)
        ta_sign = crypto.sign(members.private_key(conn, sender_id), ta_hash)

        conn.execute(
            """INSERT INTO TransactionsTable
               (TAID, CNUCoinID, TADate, TAFrom, TATo, TASum, PrevBlockHash, PrevNonce,
                TAHash, Nonce, TAApproved, TASign)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, ?)""",
            (taid, sender_id, ta_date, sender_id, recipient_id, amount_cents,
             chain["BlockChainHash"], chain["Nonce"], ta_hash, ta_sign),
        )
        block_id = conn.execute(
            """INSERT INTO BlockChainTable (TAID, DateTime, TAHash, BlockChainHash, Nonce, IsMined)
               VALUES (?, ?, ?, ?, 0, 0)""",
            (taid, ta_date, ta_hash, ta_hash),
        ).lastrowid

    return {
        "TAID": taid,
        "BlockID": block_id,
        "TADate": ta_date,
        "TAFrom": sender_id,
        "TATo": recipient_id,
        "TASum": amount_cents,
        "ChainHash": chain["BlockChainHash"],
        "ChainNonce": chain["Nonce"],
        "Payload": payload,
        "TAHash": ta_hash,
        "TASign": ta_sign,
    }


def verify_transaction(conn: sqlite3.Connection, tx: sqlite3.Row) -> dict:
    """Перевіряє хеш-образ та ЕЦП транзакції."""
    payload = transaction_payload(tx["CNUCoinID"], tx["TADate"], tx["TAID"], tx["TAFrom"], tx["TATo"],
                                  tx["TASum"], tx["PrevBlockHash"], tx["PrevNonce"])
    sender = members.get_member(conn, tx["TAFrom"])
    return {
        "hash_ok": crypto.sha256(payload) == tx["TAHash"],
        "sign_ok": sender is not None and tx["CNUCoinID"] == tx["TAFrom"]
                   and crypto.verify(sender["PublicKey"], tx["TAHash"], tx["TASign"]),
    }


def pending_transactions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM TransactionsTable WHERE TAApproved = 0 ORDER BY TADate, TAID"
    ).fetchall()


def list_transactions(conn: sqlite3.Connection, limit: int = 100) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT t.*, f.Alias AS FromAlias, r.Alias AS ToAlias, b.BlockID,
                  (SELECT COUNT(*) FROM BlockChainTable n
                   WHERE n.IsMined = 1 AND n.BlockID > b.BlockID) AS Confirmations
           FROM TransactionsTable t
           JOIN CnuCoinMembersTable f ON f.CNUCoinID = t.TAFrom
           JOIN CnuCoinMembersTable r ON r.CNUCoinID = t.TATo
           LEFT JOIN BlockChainTable b ON b.TAID = t.TAID
           ORDER BY t.TAID DESC LIMIT ?""",
        (limit,),
    ).fetchall()
