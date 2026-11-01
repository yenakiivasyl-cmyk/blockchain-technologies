"""Аудит цілісності ланцюжка блоків CNUCoin.

Для кожного видобутого блоку незалежно перераховується все, що можна перерахувати:
  * адреси учасників   — CNUCoinID == SHA-256(PublicKey);
  * хеш транзакції     — SHA-256(конкатенація полів) == TAHash;
  * ЕЦП відправника    — над TAHash;
  * зв'язок блоків     — PrevHash == BlockChainHash попереднього блоку;
  * Proof-of-Work      — SHA-256(TAHash + PrevHash + Nonce) == BlockChainHash і має Difficulty нулів;
  * ЕЦП майнера        — над BlockChainHash.
Будь-яка зміна даних «заднім числом» ламає хоча б одну перевірку.
"""
from __future__ import annotations

import sqlite3

from . import crypto
from .mining import block_payload
from .transactions import verify_transaction

CHECK_TITLES = {
    "tx_hash": "Хеш транзакції",
    "tx_sign": "ЕЦП відправника",
    "link": "Зв'язок з попереднім блоком",
    "pow": "Proof-of-Work",
    "miner_sign": "ЕЦП майнера",
}


def validate_chain(conn: sqlite3.Connection) -> dict:
    bad_members = [
        row["Alias"] for row in conn.execute("SELECT * FROM CnuCoinMembersTable")
        if crypto.address_from_public_key(row["PublicKey"]) != row["CNUCoinID"]
    ]

    blocks = conn.execute("SELECT * FROM BlockChainTable WHERE IsMined = 1 ORDER BY BlockID").fetchall()
    report = []
    prev = blocks[0]  # генезис
    for block in blocks[1:]:
        tx = conn.execute("SELECT * FROM TransactionsTable WHERE TAID = ?", (block["TAID"],)).fetchone()
        miner = conn.execute("SELECT PublicKey FROM CnuCoinMembersTable WHERE CNUCoinID = ?",
                             (block["MinerID"],)).fetchone()
        tx_checks = verify_transaction(conn, tx) if tx else {"hash_ok": False, "sign_ok": False}
        recomputed = crypto.sha256(block_payload(block["TAHash"], block["PrevHash"], block["Nonce"]))
        checks = {
            "tx_hash": tx_checks["hash_ok"] and tx["TAHash"] == block["TAHash"],
            "tx_sign": tx_checks["sign_ok"],
            "link": block["PrevHash"] == prev["BlockChainHash"],
            "pow": recomputed == block["BlockChainHash"]
                   and block["BlockChainHash"].startswith("0" * (block["Difficulty"] or 0)),
            "miner_sign": miner is not None
                          and crypto.verify(miner["PublicKey"], block["BlockChainHash"], block["BlockAssign"]),
        }
        report.append({"BlockID": block["BlockID"], "checks": checks, "ok": all(checks.values())})
        prev = block

    return {
        "ok": not bad_members and all(b["ok"] for b in report),
        "blocks": report,
        "bad_members": bad_members,
    }
