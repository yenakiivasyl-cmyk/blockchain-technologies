"""Імітація P2P-мережі AidChain: незалежні вузли, mempool, майнінг і консенсус.

* кожен вузол зберігає власну копію ланцюжка та власний mempool;
* транзакції та блоки розсилаються всім вузлам, що перебувають онлайн;
* кожен вузол самостійно перевіряє все, що отримує (нікому не довіряє);
* консенсус — правило Накамото: приймається валідний ланцюжок з найбільшою сумарною роботою.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import crypto
from .ledger import (DIFFICULTY, Block, RuleViolation, Transaction, chain_work, validate_block,
                     validate_chain)
from .merkle import merkle_root

MAX_TX_PER_BLOCK = 8


class Node:
    def __init__(self, node_id: str, name: str, city: str, keys: crypto.KeyPair):
        self.id, self.name, self.city, self.keys = node_id, name, city, keys
        self.chain: list[Block] = [Block.genesis()]
        self.mempool: dict[str, Transaction] = {}
        self.online = True
        self.log: list[str] = []

    @property
    def tip(self) -> Block:
        return self.chain[-1]

    def known_txids(self) -> set[str]:
        return {tx.txid for b in self.chain for tx in b.transactions}

    def _pending_state(self):
        """Стан «ланцюжок + mempool» — щоб не прийняти дві суперечливі транзакції."""
        state = self.audit()["state"]
        for tx in self.mempool.values():
            try:
                state.apply(tx)
            except RuleViolation:
                pass
        return state

    def receive_tx(self, tx: Transaction) -> None:
        if tx.txid in self.mempool or tx.txid in self.known_txids():
            return
        self._pending_state().apply(tx)  # кидає RuleViolation, якщо транзакція недійсна
        self.mempool[tx.txid] = tx

    def mine(self) -> Block | None:
        state = self.audit()["state"]
        selected = []
        for tx in sorted(self.mempool.values(), key=lambda t: t.timestamp):
            try:
                state.apply(tx, self.tip.index + 1)
                selected.append(tx)
            except RuleViolation:
                continue
            if len(selected) == MAX_TX_PER_BLOCK:
                break
        if not selected:
            return None
        block = Block(index=self.tip.index + 1, timestamp=round(time.time(), 3), prev_hash=self.tip.hash,
                      merkle_root=merkle_root([t.txid for t in selected]), difficulty=DIFFICULTY,
                      miner=self.keys.address, miner_key=self.keys.public_hex, transactions=selected)
        block.mine(self.keys)
        self.chain.append(block)
        for tx in selected:
            self.mempool.pop(tx.txid, None)
        return block

    def receive_block(self, block: Block) -> bool:
        """Приєднує блок, якщо він продовжує поточний ланцюжок і проходить усі перевірки."""
        if block.prev_hash != self.tip.hash:
            return False
        if not validate_block(block, self.tip, self.audit()["state"])["ok"]:
            return False
        self.chain.append(block)
        for tx in block.transactions:
            self.mempool.pop(tx.txid, None)
        return True

    def adopt_chain(self, chain: list[Block]) -> list[Transaction]:
        """Замінює ланцюжок; транзакції з відкинутих блоків повертає в mempool."""
        new_ids = {tx.txid for b in chain for tx in b.transactions}
        orphaned = [tx for b in self.chain[1:] for tx in b.transactions if tx.txid not in new_ids]
        self.chain = [Block.from_dict(b.to_dict()) for b in chain]
        self.mempool = {k: v for k, v in self.mempool.items() if k not in new_ids}
        for tx in orphaned:
            try:
                self.receive_tx(tx)
            except RuleViolation:
                pass
        return orphaned

    def audit(self) -> dict:
        return validate_chain(self.chain)

    def summary(self) -> dict:
        audit = self.audit()
        return {
            "id": self.id, "name": self.name, "city": self.city, "address": self.keys.address,
            "online": self.online, "height": self.tip.index, "tip": self.tip.hash,
            "work": chain_work(self.chain), "mempool": len(self.mempool),
            "valid": audit["ok"], "first_bad": audit["first_bad"],
        }


class Network:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.nodes: dict[str, Node] = {}
        self.wallets: dict[str, crypto.KeyPair] = {}  # «гаманці» учасників (імітація клієнтських застосунків)
        self.events: list[dict] = []

    # ── події ──
    def event(self, kind: str, text: str, node: str | None = None) -> None:
        self.events.append({"t": round(time.time(), 3), "kind": kind, "text": text, "node": node})
        self.events = self.events[-200:]

    def add_node(self, node_id: str, name: str, city: str) -> Node:
        node = Node(node_id, name, city, crypto.KeyPair.generate())
        self.nodes[node_id] = node
        return node

    def online_nodes(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.online]

    def reference_node(self) -> Node:
        """Вузол із найкращим валідним ланцюжком — з нього показуємо стан системи."""
        valid = [n for n in self.nodes.values() if n.audit()["ok"]] or list(self.nodes.values())
        return max(valid, key=lambda n: (chain_work(n.chain), n.online))

    # ── транзакції ──
    def new_wallet(self) -> crypto.KeyPair:
        keys = crypto.KeyPair.generate()
        self.wallets[keys.address] = keys
        return keys

    def submit(self, sender: str, tx_type: str, payload: dict) -> Transaction:
        keys = self.wallets.get(sender)
        if keys is None:
            raise RuleViolation("Гаманець відправника не знайдено")
        tx = Transaction.create(keys, tx_type, payload)
        online = self.online_nodes()
        if not online:
            raise RuleViolation("Немає жодного вузла онлайн")
        for node in online:
            node.receive_tx(tx)  # перший же вузол відхилить недійсну транзакцію
        self.event("tx", f"{tx_type} {tx.txid[:10]}… підписано та розіслано на {len(online)} вузл(и)")
        return tx

    # ── майнінг і консенсус ──
    def mine(self, node_id: str) -> Block | None:
        node = self.nodes[node_id]
        if not node.audit()["ok"]:
            raise RuleViolation(f"Ланцюжок вузла {node.name} пошкоджено — спершу виконайте синхронізацію")
        block = node.mine()
        if block is None:
            return None
        self.event("block", f"{node.name} видобув блок #{block.index} ({len(block.transactions)} tx, "
                            f"nonce {block.nonce}, {block.mining_ms} мс): {block.hash[:16]}…", node_id)
        if not node.online:
            self.event("net", f"{node.name} офлайн — блок #{block.index} залишився локальним (форк)", node_id)
            return block
        for peer in self.online_nodes():
            if peer is node:
                continue
            if peer.receive_block(Block.from_dict(block.to_dict())):
                self.event("sync", f"{peer.name} перевірив і прийняв блок #{block.index}", peer.id)
            else:
                self.consensus(peer.id)
        return block

    def consensus(self, node_id: str) -> bool:
        """Правило Накамото: беремо валідний ланцюжок з найбільшою сумарною роботою."""
        node = self.nodes[node_id]
        best, best_work = None, chain_work(node.chain) if node.audit()["ok"] else -1
        for peer in self.online_nodes():
            if peer is node:
                continue
            work = chain_work(peer.chain)
            if work > best_work and validate_chain(peer.chain)["ok"]:
                best, best_work = peer, work
        if best is None:
            return False
        orphaned = node.adopt_chain(best.chain)
        msg = f"{node.name} прийняв ланцюжок вузла {best.name} (висота {best.tip.index})"
        if orphaned:
            msg += f"; {len(orphaned)} tx з відкинутих блоків повернуто в mempool"
        self.event("consensus", msg, node_id)
        return True

    def set_online(self, node_id: str, online: bool) -> None:
        node = self.nodes[node_id]
        node.online = online
        self.event("net", f"{node.name} {'знову онлайн' if online else 'відключено від мережі'}", node_id)
        if online:
            self.consensus(node_id)
            for peer in self.online_nodes():  # ланцюжок вузла міг виявитися довшим — інші теж звіряються
                if peer is not node:
                    self.consensus(peer.id)
            for tx in list(node.mempool.values()):
                for peer in self.online_nodes():
                    try:
                        peer.receive_tx(tx)
                    except RuleViolation:
                        pass

    # ── атака ──
    def tamper(self, node_id: str, block_index: int, remine: bool) -> str:
        """Зловмисник на вузлі змінює суму в історичному блоці.

        remine=False — просто редагує дані (ламається корінь Меркла та ЕЦП);
        remine=True  — ще й перераховує корінь Меркла та PoW для всіх наступних блоків
                       (але ЕЦП донора та майнерів підробити без приватних ключів неможливо).
        """
        node = self.nodes[node_id]
        if not 1 <= block_index <= node.tip.index:
            raise RuleViolation("Немає такого блоку")
        block = node.chain[block_index]
        target = next((t for t in block.transactions if "amount" in t.payload or "items" in t.payload), None)
        if target is None:
            raise RuleViolation("У блоці немає транзакцій із сумами")
        if "amount" in target.payload:
            old = target.payload["amount"]
            target.payload["amount"] = old * 10
            what = f"суму внеску {old} → {old * 10} ₴"
        else:
            item = target.payload["items"][0]
            old = item["price"]
            item["price"] = old // 10 or 1
            what = f"ціну «{item['name']}» {old} → {item['price']} ₴"
        if remine:
            prev = node.chain[block_index - 1]
            for b in node.chain[block_index:]:
                b.prev_hash = prev.hash
                b.merkle_root = b.compute_merkle()
                b.nonce = 0
                prefix, target_zeros = b.header_prefix(), "0" * b.difficulty
                while not (h := crypto.sha256(prefix + str(b.nonce))).startswith(target_zeros):
                    b.nonce += 1
                b.hash = h
                prev = b
        self.event("attack", f"АТАКА на {node.name}: у блоці #{block_index} змінено {what}"
                             + (" і перемайнено ланцюжок" if remine else ""), node_id)
        return what

    # ── збереження ──
    def to_dict(self) -> dict:
        return {
            "nodes": [{"id": n.id, "name": n.name, "city": n.city, "key": n.keys.private_hex, "online": n.online,
                       "chain": [b.to_dict() for b in n.chain],
                       "mempool": [t.to_dict() for t in n.mempool.values()]} for n in self.nodes.values()],
            "wallets": {a: k.private_hex for a, k in self.wallets.items()},
            "events": self.events,
        }

    def save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.to_dict(), ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Network":
        data = json.loads(path.read_text(encoding="utf-8"))
        net = cls(path)
        for nd in data["nodes"]:
            node = Node(nd["id"], nd["name"], nd["city"], crypto.KeyPair.from_hex(nd["key"]))
            node.online = nd["online"]
            node.chain = [Block.from_dict(b) for b in nd["chain"]]
            node.mempool = {t["txid"]: Transaction.from_dict(t) for t in nd["mempool"]}
            net.nodes[node.id] = node
        net.wallets = {a: crypto.KeyPair.from_hex(k) for a, k in data["wallets"].items()}
        net.events = data["events"]
        return net
