"""Реєстрація учасників CNUCoin та електронний гаманець (ЛР №1, п. 1)."""
from __future__ import annotations

import sqlite3

from . import crypto
from .db import SYSTEM_ADDRESS, now

# Скільки наступних блоків має бути видобуто, щоб отримані кошти можна було витрачати
# (ЛР №2, п. 5: «для підтвердження транзакції та блоку необхідно внести їх до наступного блоку»).
CONFIRMATIONS_REQUIRED = 1


class RegistrationError(ValueError):
    pass


def register(conn: sqlite3.Connection, alias: str, is_miner: bool = False,
             initial_cents: int = 0) -> dict:
    """Реєструє учасника: генерує ключі ЕЦП, адресу та стартовий баланс.

    Після виконання функції учасник має все, що вимагає ЛР №1:
    унікальний ідентифікатор, публічний ключ та електронний гаманець.
    """
    alias = alias.strip()
    if not alias:
        raise RegistrationError("Псевдонім не може бути порожнім")
    if initial_cents < 0:
        raise RegistrationError("Стартова сума не може бути від'ємною")

    private_pem, public_pem = crypto.generate_keypair()
    cnucoin_id = crypto.address_from_public_key(public_pem)
    reg_date = now()

    with conn:
        conn.execute(
            "INSERT INTO CnuCoinMembersTable (CNUCoinID, Alias, PublicKey, IsMiner, RegDate) VALUES (?, ?, ?, ?, ?)",
            (cnucoin_id, alias, public_pem, int(is_miner), reg_date),
        )
        conn.execute(
            "INSERT INTO PrivateTable (CNUCoinID, PrivateKey, PublicKey) VALUES (?, ?, ?)",
            (cnucoin_id, private_pem, public_pem),
        )
        if initial_cents:
            conn.execute(
                """INSERT INTO EWalletTable (CNUCoinID, TADate, TAFrom, TATo, TASum, Kind)
                   VALUES (?, ?, ?, ?, ?, 'GENESIS')""",
                (cnucoin_id, reg_date, SYSTEM_ADDRESS, cnucoin_id, initial_cents),
            )

    return {
        "CNUCoinID": cnucoin_id,
        "Alias": alias,
        "IsMiner": is_miner,
        "PublicKey": public_pem,
        "PrivateKey": private_pem,
        "RegDate": reg_date,
        "InitialCents": initial_cents,
    }


def list_members(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM CnuCoinMembersTable ORDER BY RegDate").fetchall()


def get_member(conn: sqlite3.Connection, cnucoin_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM CnuCoinMembersTable WHERE CNUCoinID = ?", (cnucoin_id,)).fetchone()


def private_key(conn: sqlite3.Connection, cnucoin_id: str) -> str:
    row = conn.execute("SELECT PrivateKey FROM PrivateTable WHERE CNUCoinID = ?", (cnucoin_id,)).fetchone()
    if row is None:
        raise RegistrationError("Приватний ключ не знайдено")
    return row["PrivateKey"]


def balances(conn: sqlite3.Connection, cnucoin_id: str) -> dict:
    """Баланс гаманця у розрізі: усього / доступно / заблоковано / в очікуванні.

    * списання враховуються одразу;
    * надходження стають доступними після CONFIRMATIONS_REQUIRED наступних блоків;
    * суми ще не видобутих вихідних транзакцій резервуються.
    """
    total = conn.execute(
        "SELECT COALESCE(SUM(TASum), 0) FROM EWalletTable WHERE CNUCoinID = ?", (cnucoin_id,)
    ).fetchone()[0]
    unlocked = conn.execute(
        """SELECT COALESCE(SUM(w.TASum), 0) FROM EWalletTable w
           WHERE w.CNUCoinID = ?
             AND (w.TASum < 0 OR w.Kind = 'GENESIS'
                  OR (SELECT COUNT(*) FROM BlockChainTable n
                      WHERE n.IsMined = 1 AND n.BlockID > w.BlockID) >= ?)""",
        (cnucoin_id, CONFIRMATIONS_REQUIRED),
    ).fetchone()[0]
    pending_out = conn.execute(
        "SELECT COALESCE(SUM(TASum), 0) FROM TransactionsTable WHERE TAFrom = ? AND TAApproved = 0",
        (cnucoin_id,),
    ).fetchone()[0]
    return {
        "total": total,
        "locked": total - unlocked,
        "pending_out": pending_out,
        "spendable": unlocked - pending_out,
    }


def wallet_history(conn: sqlite3.Connection, cnucoin_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT w.*,
                  (SELECT COUNT(*) FROM BlockChainTable n
                   WHERE n.IsMined = 1 AND n.BlockID > w.BlockID) AS Confirmations
           FROM EWalletTable w WHERE w.CNUCoinID = ? ORDER BY w.EntryID DESC""",
        (cnucoin_id,),
    ).fetchall()
