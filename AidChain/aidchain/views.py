"""Запити до ланцюжка: опис транзакцій, відстеження внеску, Merkle-доведення, перевірка документів."""
from __future__ import annotations

from .ledger import ROLES, Block, State
from .merkle import merkle_proof, tree_levels, verify_proof


def uah(n: int | float) -> str:
    return f"{n:,.0f}".replace(",", " ") + " ₴"


def name(state: State, addr: str | None) -> str:
    actor = state.actors.get(addr or "")
    return actor["name"] if actor else (addr or "—")[:10]


def describe(state: State, tx) -> str:
    p, who = tx.payload, name(state, tx.sender)
    if tx.type == "REGISTER":
        return f"{p.get('name')} зареєструвався як «{ROLES.get(p.get('role'), p.get('role'))}»"
    if tx.type == "CAMPAIGN":
        return f"{who} відкрив збір «{p.get('title')}» на {uah(p.get('goal', 0))} для {name(state, p.get('recipient'))}"
    if tx.type == "DONATION":
        c = state.campaigns.get(p.get("campaign"), {})
        return f"{who} задонатив {uah(p.get('amount', 0))} у збір «{c.get('title', '?')}»"
    if tx.type == "PURCHASE":
        total = sum(i.get("qty", 0) * i.get("price", 0) for i in p.get("items", []))
        items = ", ".join(f"{i['name']} ×{i['qty']}" for i in p.get("items", []))
        return f"{who} закупив у {name(state, p.get('supplier'))}: {items} на {uah(total)}"
    if tx.type == "SHIPMENT":
        purchase = state.purchases.get(p.get("purchase"))
        to = name(state, state.campaigns[purchase["campaign"]]["recipient"]) if purchase else "?"
        return f"{who} відвантажив товар → {to} (ТТН {p.get('tracking')})"
    if tx.type == "RECEIPT":
        status = {"OK": "у повному обсязі", "PARTIAL": "частково", "DAMAGED": "з пошкодженнями"}.get(p.get("status"), "")
        return f"{who} підтвердив отримання {status}"
    return tx.type


def block_view(block: Block, state: State, audit_row: dict | None = None) -> dict:
    d = block.to_dict()
    d["tx_count"] = len(block.transactions)
    d["miner_name"] = block.miner
    for tx, td in zip(block.transactions, d["transactions"]):
        td["text"] = describe(state, tx)
        td["sender_name"] = name(state, tx.sender)
        td["signature_ok"] = tx.signature_ok()
    if audit_row:
        d["audit"] = audit_row
    return d


def campaigns_view(state: State) -> list[dict]:
    out = []
    for c in state.campaigns.values():
        purchases = [state.purchases[p] for p in c["purchases"]]
        shipped = [p for p in purchases if p["shipment"]]
        delivered = [p for p in shipped if state.shipments[p["shipment"]]["receipt"]]
        out.append({
            **c,
            "fund_name": name(state, c["fund"]),
            "recipient_name": name(state, c["recipient"]),
            "donors": len({state.donations[d]["donor"] for d in c["donations"]}),
            "delivered": sum(p["total"] for p in delivered),
            "in_transit": sum(p["total"] for p in shipped if p not in delivered),
            "purchases_view": [{
                "id": p["id"], "total": p["total"], "supplier_name": name(state, p["supplier"]),
                "items": p["items"], "shipment": p["shipment"],
                "receipt": state.shipments[p["shipment"]]["receipt"] if p["shipment"] else None,
            } for p in purchases],
        })
    return sorted(out, key=lambda c: c["timestamp"])


def trace_donation(state: State, donation_id: str) -> dict | None:
    """Куди пішли мої гроші: пропорційна частка внеску в кожній закупівлі збору."""
    donation = state.donations.get(donation_id)
    if donation is None:
        return None
    campaign = state.campaigns[donation["campaign"]]
    share = donation["amount"] / campaign["raised"] if campaign["raised"] else 0
    steps = []
    for pid in campaign["purchases"]:
        p = state.purchases[pid]
        shipment = state.shipments.get(p["shipment"]) if p["shipment"] else None
        receipt = state.receipts.get(shipment["receipt"]) if shipment and shipment["receipt"] else None
        steps.append({
            "purchase": pid, "block": p["block"], "supplier": name(state, p["supplier"]),
            "items": p["items"], "total": p["total"], "your_part": round(p["total"] * share),
            "invoice_hash": p["invoice_hash"],
            "shipment": shipment and {"id": shipment["id"], "block": shipment["block"], "tracking": shipment["tracking"]},
            "receipt": receipt and {"id": receipt["id"], "block": receipt["block"], "status": receipt["status"],
                                    "note": receipt["note"]},
        })
    used = sum(s["your_part"] for s in steps)
    return {
        "donation": {**donation, "donor_name": name(state, donation["donor"])},
        "campaign": {"id": campaign["id"], "title": campaign["title"], "raised": campaign["raised"],
                     "recipient": name(state, campaign["recipient"]), "fund": name(state, campaign["fund"])},
        "share": share, "steps": steps, "used": used, "unused": donation["amount"] - used,
    }


def find_tx(chain: list[Block], txid: str):
    for block in chain:
        for i, tx in enumerate(block.transactions):
            if tx.txid == txid:
                return block, i
    return None, None


def tx_proof(chain: list[Block], txid: str) -> dict | None:
    """Merkle-доведення: транзакція належить блоку, не завантажуючи інших транзакцій."""
    block, i = find_tx(chain, txid)
    if block is None:
        return None
    leaves = [t.txid for t in block.transactions]
    proof = merkle_proof(leaves, i)
    return {
        "txid": txid, "block": block.index, "block_hash": block.hash, "merkle_root": block.merkle_root,
        "position": i, "proof": proof, "levels": tree_levels(leaves),
        "verified": verify_proof(txid, proof, block.merkle_root),
        "confirmations": chain[-1].index - block.index + 1,
    }


def verify_document(chain: list[Block], state: State, doc_hash: str) -> dict:
    txid = state.documents.get(doc_hash)
    if txid is None:
        return {"found": False, "hash": doc_hash}
    block, i = find_tx(chain, txid)
    tx = block.transactions[i]
    field = next(f for f, v in tx.payload.items() if v == doc_hash)
    return {"found": True, "hash": doc_hash, "field": field, "tx": tx.to_dict(), "text": describe(state, tx),
            "signer": name(state, tx.sender), "proof": tx_proof(chain, txid)}
