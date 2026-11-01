"""Структури блокчейну AidChain та правила («смарт-контракт») обліку допомоги.

Життєвий цикл допомоги — кожен крок є підписаною транзакцією:

  REGISTER  учасник реєструє свій публічний ключ і роль
  CAMPAIGN  фонд відкриває збір: мета, сума, отримувач
  DONATION  донор робить внесок у збір
  PURCHASE  фонд купує товари в постачальника (≤ зібраних і ще не витрачених коштів)
  SHIPMENT  постачальник відвантажує закупівлю отримувачу збору
  RECEIPT   отримувач підтверджує отримання (з хешем фото/акту)

Стан системи (баланси зборів, статуси закупівель) ніде не зберігається окремо —
він щоразу детерміновано відтворюється з ланцюжка блоків (event sourcing).
"""
from __future__ import annotations

import copy
import time
from dataclasses import asdict, dataclass, field

from . import crypto
from .merkle import merkle_root

DIFFICULTY = 4  # кількість нулів (hex) на початку хешу блоку
GENESIS_PREV = "0" * 64

ROLES = {
    "FUND": "Благодійний фонд",
    "DONOR": "Донор",
    "SUPPLIER": "Постачальник",
    "RECIPIENT": "Отримувач допомоги",
}
TX_TYPES = ("REGISTER", "CAMPAIGN", "DONATION", "PURCHASE", "SHIPMENT", "RECEIPT")
DOCUMENT_FIELDS = ("invoice_hash", "waybill_hash", "photo_hash")


class RuleViolation(ValueError):
    """Транзакція суперечить правилам системи."""


# ─────────────────────────────── Транзакція ───────────────────────────────

@dataclass
class Transaction:
    type: str
    sender: str
    public_key: str
    payload: dict
    timestamp: float = field(default_factory=lambda: round(time.time(), 3))
    signature: str = ""

    def body(self) -> dict:
        return {"type": self.type, "sender": self.sender, "public_key": self.public_key,
                "payload": self.payload, "timestamp": self.timestamp}

    @property
    def txid(self) -> str:
        return crypto.sha256(crypto.canonical(self.body()))

    def sign(self, keys: crypto.KeyPair) -> "Transaction":
        self.signature = keys.sign(self.txid)
        return self

    def signature_ok(self) -> bool:
        return crypto.address(self.public_key) == self.sender and crypto.verify(self.public_key, self.txid, self.signature)

    def to_dict(self) -> dict:
        return {**asdict(self), "txid": self.txid}

    @classmethod
    def from_dict(cls, d: dict) -> "Transaction":
        return cls(**{k: d[k] for k in ("type", "sender", "public_key", "payload", "timestamp", "signature")})

    @classmethod
    def create(cls, keys: crypto.KeyPair, tx_type: str, payload: dict) -> "Transaction":
        return cls(type=tx_type, sender=keys.address, public_key=keys.public_hex, payload=payload).sign(keys)


# ──────────────────────────────── Блок ────────────────────────────────

@dataclass
class Block:
    index: int
    timestamp: float
    prev_hash: str
    merkle_root: str
    difficulty: int
    miner: str
    miner_key: str
    transactions: list[Transaction]
    nonce: int = 0
    hash: str = ""
    miner_signature: str = ""
    mining_ms: float = 0.0

    def header_prefix(self) -> str:
        return "|".join(str(v) for v in (self.index, self.timestamp, self.prev_hash, self.merkle_root,
                                         self.difficulty, self.miner, self.miner_key)) + "|"

    def compute_hash(self) -> str:
        return crypto.sha256(self.header_prefix() + str(self.nonce))

    def compute_merkle(self) -> str:
        return merkle_root([tx.txid for tx in self.transactions])

    def mine(self, keys: crypto.KeyPair) -> "Block":
        """Proof-of-Work: перебір nonce, доки хеш не почнеться з `difficulty` нулів."""
        prefix, target = self.header_prefix(), "0" * self.difficulty
        started = time.perf_counter()
        nonce = 0
        while not (h := crypto.sha256(prefix + str(nonce))).startswith(target):
            nonce += 1
        self.nonce, self.hash = nonce, h
        self.mining_ms = round((time.perf_counter() - started) * 1000, 1)
        self.miner_signature = keys.sign(self.hash)
        return self

    @property
    def work(self) -> int:
        return 16 ** self.difficulty

    def to_dict(self) -> dict:
        d = asdict(self)
        d["transactions"] = [tx.to_dict() for tx in self.transactions]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Block":
        d = dict(d)
        d["transactions"] = [Transaction.from_dict(t) for t in d["transactions"]]
        return cls(**d)

    @classmethod
    def genesis(cls) -> "Block":
        block = cls(index=0, timestamp=1767225600.0, prev_hash=GENESIS_PREV, merkle_root=merkle_root([]),
                    difficulty=0, miner="genesis", miner_key="", transactions=[])
        block.hash = block.compute_hash()
        return block


# ─────────────────────────── Стан і правила ───────────────────────────

class State:
    """Світовий стан, відтворений з транзакцій. `apply` реалізує правила системи."""

    def __init__(self):
        self.actors: dict[str, dict] = {}
        self.campaigns: dict[str, dict] = {}
        self.donations: dict[str, dict] = {}
        self.purchases: dict[str, dict] = {}
        self.shipments: dict[str, dict] = {}
        self.receipts: dict[str, dict] = {}
        self.documents: dict[str, str] = {}  # хеш документа -> txid

    def clone(self) -> "State":
        return copy.deepcopy(self)

    def _actor(self, addr: str, role: str | None = None) -> dict:
        actor = self.actors.get(addr)
        if actor is None:
            raise RuleViolation("Учасника не зареєстровано в мережі")
        if role and actor["role"] != role:
            raise RuleViolation(f"Дію може виконати лише роль «{ROLES[role]}», а «{actor['name']}» — {ROLES[actor['role']]}")
        return actor

    @staticmethod
    def _positive_int(value, name: str) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise RuleViolation(f"Поле «{name}» має бути додатним цілим числом")
        return value

    def apply(self, tx: Transaction, block_index: int | None = None) -> None:
        if tx.type not in TX_TYPES:
            raise RuleViolation(f"Невідомий тип транзакції {tx.type}")
        if not tx.signature_ok():
            raise RuleViolation("Недійсна ЕЦП або адреса не відповідає публічному ключу")
        p, txid = tx.payload, tx.txid
        meta = {"txid": txid, "timestamp": tx.timestamp, "block": block_index}

        for f in DOCUMENT_FIELDS:
            if p.get(f) is not None and (not isinstance(p[f], str) or len(p[f]) != 64):
                raise RuleViolation(f"{f} має бути SHA-256 (64 hex-символи)")

        if tx.type == "REGISTER":
            if tx.sender in self.actors:
                raise RuleViolation("Учасника вже зареєстровано")
            if p.get("role") not in ROLES or not str(p.get("name", "")).strip():
                raise RuleViolation("Потрібні коректні ім'я та роль")
            self.actors[tx.sender] = {"address": tx.sender, "name": p["name"].strip(), "role": p["role"],
                                      "public_key": tx.public_key, **meta}

        elif tx.type == "CAMPAIGN":
            self._actor(tx.sender, "FUND")
            self._actor(p.get("recipient"), "RECIPIENT")
            goal = self._positive_int(p.get("goal"), "goal")
            if not str(p.get("title", "")).strip():
                raise RuleViolation("Збір повинен мати назву")
            self.campaigns[txid] = {"id": txid, "title": p["title"], "description": p.get("description", ""),
                                    "fund": tx.sender, "recipient": p["recipient"], "goal": goal,
                                    "raised": 0, "spent": 0, "donations": [], "purchases": [], **meta}

        elif tx.type == "DONATION":
            self._actor(tx.sender, "DONOR")
            campaign = self.campaigns.get(p.get("campaign"))
            if campaign is None:
                raise RuleViolation("Збір не знайдено")
            amount = self._positive_int(p.get("amount"), "amount")
            campaign["raised"] += amount
            campaign["donations"].append(txid)
            self.donations[txid] = {"id": txid, "donor": tx.sender, "campaign": campaign["id"], "amount": amount,
                                    "message": p.get("message", ""), **meta}

        elif tx.type == "PURCHASE":
            campaign = self.campaigns.get(p.get("campaign"))
            if campaign is None:
                raise RuleViolation("Збір не знайдено")
            if campaign["fund"] != tx.sender:
                raise RuleViolation("Витрачати кошти збору може лише фонд, що його відкрив")
            self._actor(p.get("supplier"), "SUPPLIER")
            items = p.get("items") or []
            if not items:
                raise RuleViolation("Закупівля має містити хоча б одну позицію")
            total = sum(self._positive_int(i.get("qty"), "qty") * self._positive_int(i.get("price"), "price")
                        for i in items)
            available = campaign["raised"] - campaign["spent"]
            if total > available:
                raise RuleViolation(f"Сума закупівлі {total:,} ₴ перевищує доступні кошти збору {available:,} ₴"
                                    .replace(",", " "))
            campaign["spent"] += total
            campaign["purchases"].append(txid)
            self.purchases[txid] = {"id": txid, "campaign": campaign["id"], "fund": tx.sender,
                                    "supplier": p["supplier"], "items": items, "total": total,
                                    "invoice_hash": p.get("invoice_hash"), "shipment": None, **meta}

        elif tx.type == "SHIPMENT":
            purchase = self.purchases.get(p.get("purchase"))
            if purchase is None:
                raise RuleViolation("Закупівлю не знайдено")
            if purchase["supplier"] != tx.sender:
                raise RuleViolation("Відвантажити товар може лише постачальник цієї закупівлі")
            if purchase["shipment"]:
                raise RuleViolation("Закупівлю вже відвантажено")
            recipient = self.campaigns[purchase["campaign"]]["recipient"]
            purchase["shipment"] = txid
            self.shipments[txid] = {"id": txid, "purchase": purchase["id"], "supplier": tx.sender,
                                    "recipient": recipient, "tracking": p.get("tracking", ""),
                                    "waybill_hash": p.get("waybill_hash"), "receipt": None, **meta}

        elif tx.type == "RECEIPT":
            shipment = self.shipments.get(p.get("shipment"))
            if shipment is None:
                raise RuleViolation("Відвантаження не знайдено")
            if shipment["recipient"] != tx.sender:
                raise RuleViolation("Підтвердити отримання може лише адресат відвантаження")
            if shipment["receipt"]:
                raise RuleViolation("Отримання вже підтверджено")
            if p.get("status") not in ("OK", "PARTIAL", "DAMAGED"):
                raise RuleViolation("Статус має бути OK, PARTIAL або DAMAGED")
            shipment["receipt"] = txid
            self.receipts[txid] = {"id": txid, "shipment": shipment["id"], "recipient": tx.sender,
                                   "status": p["status"], "note": p.get("note", ""),
                                   "photo_hash": p.get("photo_hash"), **meta}

        for f in DOCUMENT_FIELDS:
            if p.get(f):
                self.documents[p[f]] = txid


# ─────────────────────────── Валідація ланцюга ───────────────────────────

CHECKS = {
    "hash": "Хеш заголовка",
    "link": "Зв'язок з попереднім",
    "pow": "Proof-of-Work",
    "merkle": "Корінь Меркла",
    "tx_signatures": "ЕЦП транзакцій",
    "miner_signature": "ЕЦП вузла-майнера",
    "rules": "Правила системи",
}


def validate_block(block: Block, prev: Block, state: State) -> dict:
    """Перевіряє блок відносно попереднього та застосовує його до `state` (на місці)."""
    checks = {
        "hash": block.compute_hash() == block.hash,
        "link": block.prev_hash == prev.hash and block.index == prev.index + 1,
        "pow": block.hash.startswith("0" * block.difficulty) and block.difficulty >= DIFFICULTY,
        "merkle": block.compute_merkle() == block.merkle_root,
        "tx_signatures": all(tx.signature_ok() for tx in block.transactions),
        "miner_signature": crypto.address(block.miner_key) == block.miner
                           and crypto.verify(block.miner_key, block.hash, block.miner_signature),
        "rules": True,
    }
    error = None
    for tx in block.transactions:
        try:
            state.apply(tx, block.index)
        except RuleViolation as e:
            checks["rules"] = False
            error = f"{tx.type} {tx.txid[:10]}…: {e}"
            break
    return {"index": block.index, "hash": block.hash, "checks": checks, "ok": all(checks.values()), "error": error}


def validate_chain(blocks: list[Block]) -> dict:
    """Повний аудит ланцюжка. Повертає звіт по кожному блоку та відтворений стан."""
    state = State()
    report = []
    if not blocks or blocks[0].hash != Block.genesis().hash:
        return {"ok": False, "blocks": [], "state": state, "first_bad": 0}
    for prev, block in zip(blocks, blocks[1:]):
        report.append(validate_block(block, prev, state))
    first_bad = next((r["index"] for r in report if not r["ok"]), None)
    return {"ok": first_bad is None, "blocks": report, "state": state, "first_bad": first_bad}


def replay(blocks: list[Block]) -> State:
    state = State()
    for block in blocks[1:]:
        for tx in block.transactions:
            state.apply(tx, block.index)
    return state


def chain_work(blocks: list[Block]) -> int:
    return sum(b.work for b in blocks)
