"""База даних CNUCoin (SQLite).

Структура відповідає Додатку до ЛР №1 («Приблизна структура БД CNUCoin»):

  CnuCoinMembersTable  — публічний реєстр учасників (доступний усім)
  PrivateTable         — приватні ключі (доступ лише власнику)
  EWalletTable         — електронний гаманець (рух коштів власника)
  TransactionsTable    — транзакції (з обов'язковим полем Nonce)
  BlockChainTable      — ланцюжок блоків (хеш-образи, Nonce, підпис майнера)

Суми зберігаються цілими числами в «центах» (1 CNU = 100 cent),
щоб уникнути похибок округлення чисел з плаваючою комою.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

GENESIS_HASH = "0" * 64
GENESIS_NONCE = 0
SYSTEM_ADDRESS = "GENESIS"     # джерело стартових коштів при реєстрації
COINBASE_ADDRESS = "COINBASE"  # джерело нових монет (винагорода майнеру)

SCHEMA = """
CREATE TABLE IF NOT EXISTS CnuCoinMembersTable (
    CNUCoinID   TEXT    PRIMARY KEY,                 -- SHA-256(PublicKey): адреса учасника
    Alias       TEXT    NOT NULL,                    -- псевдонім для зручності інтерфейсу
    PublicKey   TEXT    NOT NULL UNIQUE,             -- публічний ключ ЕЦП (PEM)
    IsMiner     INTEGER NOT NULL DEFAULT 0 CHECK (IsMiner IN (0, 1)),
    RegDate     TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS PrivateTable (
    CNUCoinID   TEXT PRIMARY KEY REFERENCES CnuCoinMembersTable(CNUCoinID) ON DELETE CASCADE,
    PrivateKey  TEXT NOT NULL,                       -- приватний ключ ЕЦП (PEM)
    PublicKey   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS TransactionsTable (
    TAID          INTEGER PRIMARY KEY,               -- ідентифікатор транзакції
    CNUCoinID     TEXT    NOT NULL REFERENCES CnuCoinMembersTable(CNUCoinID), -- автор
    TADate        TEXT    NOT NULL,                  -- дата/час транзакції
    TAFrom        TEXT    NOT NULL REFERENCES CnuCoinMembersTable(CNUCoinID), -- адреса платника
    TATo          TEXT    NOT NULL REFERENCES CnuCoinMembersTable(CNUCoinID), -- адреса отримувача
    TASum         INTEGER NOT NULL CHECK (TASum > 0),
    PrevBlockHash TEXT    NOT NULL,                  -- BlockChainHash, що увійшов у TAHash
    PrevNonce     INTEGER NOT NULL,                  -- Nonce, що увійшов у TAHash
    TAHash        TEXT    NOT NULL UNIQUE,           -- хеш-образ транзакції
    Nonce         INTEGER,                           -- «сіль» майнінгу (заповнює майнер, ЛР №2)
    TAApproved    INTEGER NOT NULL DEFAULT 0 CHECK (TAApproved IN (0, 1)),
    TASign        TEXT    NOT NULL                   -- ЕЦП відправника над TAHash
);

CREATE TABLE IF NOT EXISTS BlockChainTable (
    BlockID        INTEGER PRIMARY KEY,              -- 0 = генезис-блок
    TAID           INTEGER UNIQUE REFERENCES TransactionsTable(TAID),
    MinerID        TEXT    REFERENCES CnuCoinMembersTable(CNUCoinID), -- хто видобув блок
    DateTime       TEXT    NOT NULL,                 -- дата останнього хеш-образу
    PrevHash       TEXT,                             -- хеш попереднього блоку
    TAHash         TEXT,                             -- хеш транзакції блоку
    BlockChainHash TEXT    NOT NULL,                 -- хеш-образ блокчейну
    Nonce          INTEGER NOT NULL DEFAULT 0,       -- «сіль», для якої отримано хеш
    Difficulty     INTEGER,                          -- кількість провідних нулів
    Attempts       INTEGER,                          -- скільки хешів обчислено
    MiningTimeMs   REAL,                             -- час майнінгу, мс
    Reward         INTEGER,                          -- винагорода майнеру, cent
    BlockAssign    TEXT,                             -- ЕЦП майнера над BlockChainHash
    IsMined        INTEGER NOT NULL DEFAULT 0 CHECK (IsMined IN (0, 1))
);

CREATE TABLE IF NOT EXISTS EWalletTable (
    EntryID     INTEGER PRIMARY KEY AUTOINCREMENT,
    CNUCoinID   TEXT    NOT NULL REFERENCES CnuCoinMembersTable(CNUCoinID) ON DELETE CASCADE,
    TADate      TEXT    NOT NULL,
    TAFrom      TEXT    NOT NULL,
    TATo        TEXT    NOT NULL,
    TASum       INTEGER NOT NULL,                    -- «+» надходження, «−» списання
    Kind        TEXT    NOT NULL CHECK (Kind IN ('GENESIS', 'TRANSFER', 'REWARD')),
    TAID        INTEGER REFERENCES TransactionsTable(TAID),
    BlockID     INTEGER REFERENCES BlockChainTable(BlockID)
);

CREATE INDEX IF NOT EXISTS idx_tx_pending ON TransactionsTable(TAApproved, TADate);
CREATE INDEX IF NOT EXISTS idx_wallet_owner ON EWalletTable(CNUCoinID);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: str | Path) -> sqlite3.Connection:
    """Створює БД (якщо її немає) разом із генезис-блоком."""
    conn = connect(path)
    conn.executescript(SCHEMA)
    if conn.execute("SELECT 1 FROM BlockChainTable WHERE BlockID = 0").fetchone() is None:
        conn.execute(
            """INSERT INTO BlockChainTable
               (BlockID, DateTime, PrevHash, BlockChainHash, Nonce, Difficulty, Attempts, IsMined)
               VALUES (0, ?, ?, ?, ?, 0, 0, 1)""",
            (now(), GENESIS_HASH, GENESIS_HASH, GENESIS_NONCE),
        )
        conn.commit()
    return conn


def to_cents(amount: float | str) -> int:
    return int(round(float(amount) * 100))


def fmt(cents: int | None) -> str:
    """Форматує суму в CNU: 12345 -> '123.45'."""
    cents = cents or 0
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"
