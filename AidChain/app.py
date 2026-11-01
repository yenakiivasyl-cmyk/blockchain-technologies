"""AidChain — веб-застосунок (Flask REST API + односторінковий інтерфейс).

Запуск:  python app.py   ->  http://127.0.0.1:8000
Стан мережі зберігається в data/state.json; кнопка «Скинути демо» відтворює сценарій заново.
"""
from __future__ import annotations

import os
import threading
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from aidchain import views
from aidchain.crypto import sha256
from aidchain.demo import SAMPLES, build_demo
from aidchain.ledger import CHECKS, DIFFICULTY, ROLES, RuleViolation
from aidchain.network import Network

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "data" / "state.json"

app = Flask(__name__, static_folder="static", static_url_path="/static")
lock = threading.Lock()
net = Network.load(STATE_PATH) if STATE_PATH.exists() else build_demo(STATE_PATH)


def api(fn):
    """Серіалізує доступ до мережі, зберігає стан і перетворює порушення правил на HTTP 400."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        with lock:
            try:
                result = fn(*args, **kwargs)
                if request.method == "POST":
                    net.save()
                return jsonify(result)
            except (RuleViolation, KeyError, ValueError, TypeError) as e:
                return jsonify({"error": str(e)}), 400
    return wrapper


def node_arg():
    node_id = request.args.get("node")
    return net.nodes[node_id] if node_id in net.nodes else net.reference_node()


@app.get("/")
def index():
    return send_from_directory(ROOT / "static", "index.html")


@app.get("/samples/<path:name>")
def samples(name):
    return send_from_directory(SAMPLES, name, as_attachment=True)


@app.get("/api/state")
@api
def state():
    node = node_arg()
    audit = node.audit()
    st = audit["state"]
    rows = {r["index"]: r for r in audit["blocks"]}
    campaigns = views.campaigns_view(st)
    return {
        "difficulty": DIFFICULTY,
        "roles": ROLES,
        "checks": CHECKS,
        "viewing": node.id,
        "reference": net.reference_node().id,
        "nodes": [n.summary() for n in net.nodes.values()],
        "node_names": {n.keys.address: n.name for n in net.nodes.values()},
        "chain": [views.block_view(b, st, rows.get(b.index)) for b in node.chain],
        "mempool": [{**tx.to_dict(), "text": views.describe(st, tx)} for tx in node.mempool.values()],
        "actors": sorted(st.actors.values(), key=lambda a: (a["role"], a["name"])),
        "campaigns": campaigns,
        "donations": [{**d, "donor_name": views.name(st, d["donor"]),
                       "campaign_title": st.campaigns[d["campaign"]]["title"]} for d in st.donations.values()],
        "open_purchases": [{"id": p["id"], "supplier": p["supplier"], "total": p["total"],
                            "label": ", ".join(i["name"] for i in p["items"])}
                           for p in st.purchases.values() if not p["shipment"]],
        "open_shipments": [{"id": s["id"], "recipient": s["recipient"], "tracking": s["tracking"],
                            "label": ", ".join(i["name"] for i in st.purchases[s["purchase"]]["items"])}
                           for s in st.shipments.values() if not s["receipt"]],
        "stats": {
            "raised": sum(c["raised"] for c in campaigns),
            "spent": sum(c["spent"] for c in campaigns),
            "delivered": sum(c["delivered"] for c in campaigns),
            "blocks": node.tip.index,
            "txs": sum(len(b.transactions) for b in node.chain),
            "actors": len(st.actors),
        },
        "events": list(reversed(net.events[-60:])),
    }


@app.post("/api/tx")
@api
def submit_tx():
    body = request.get_json()
    payload = body.get("payload", {})
    for key in ("amount", "goal"):
        if key in payload:
            payload[key] = int(payload[key])
    for item in payload.get("items", []):
        item["qty"], item["price"] = int(item["qty"]), int(item["price"])
    if body["type"] == "REGISTER":
        sender = net.new_wallet().address
    else:
        sender = body["sender"]
    tx = net.submit(sender, body["type"], payload)
    return {"txid": tx.txid}


@app.post("/api/mine")
@api
def mine():
    node_id = request.get_json()["node"]
    block = net.mine(node_id)
    if block is None:
        raise RuleViolation("Mempool вузла порожній — немає що майнити")
    return {"index": block.index, "hash": block.hash, "nonce": block.nonce, "ms": block.mining_ms}


@app.post("/api/consensus")
@api
def consensus():
    node_id = request.get_json()["node"]
    changed = net.consensus(node_id)
    if not changed:
        net.event("consensus", f"{net.nodes[node_id].name}: власний ланцюжок уже найкращий", node_id)
    return {"changed": changed}


@app.post("/api/online")
@api
def online():
    body = request.get_json()
    net.set_online(body["node"], bool(body["online"]))
    return {"ok": True}


@app.post("/api/tamper")
@api
def tamper():
    body = request.get_json()
    return {"what": net.tamper(body["node"], int(body["block"]), bool(body.get("remine")))}


@app.get("/api/trace/<donation_id>")
@api
def trace(donation_id):
    result = views.trace_donation(node_arg().audit()["state"], donation_id)
    if result is None:
        raise KeyError("Внесок не знайдено")
    return result


@app.get("/api/proof/<txid>")
@api
def proof(txid):
    result = views.tx_proof(node_arg().chain, txid)
    if result is None:
        raise KeyError("Транзакцію не знайдено в ланцюжку")
    return result


@app.post("/api/verify")
@api
def verify():
    upload = request.files.get("file")
    doc_hash = sha256(upload.read()) if upload else request.form["hash"].strip().lower()
    node = net.reference_node()
    result = views.verify_document(node.chain, node.audit()["state"], doc_hash)
    result["filename"] = upload.filename if upload else None
    return result


@app.post("/api/reset")
@api
def reset():
    global net
    net = build_demo(STATE_PATH)
    return {"ok": True}


if __name__ == "__main__":
    app.run(debug=False, port=int(os.environ.get("PORT", 8000)), threaded=True)
