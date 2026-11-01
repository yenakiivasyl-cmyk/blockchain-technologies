"""Веб-інтерфейс CNUCoin.

Запуск:  python web/app.py   ->  http://127.0.0.1:5000
БД задається змінною середовища CNUCOIN_DB (за замовчуванням output/cnucoin_web.db).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from flask import Flask, flash, g, redirect, render_template, request, url_for

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cnucoin import crypto, db, members, mining, transactions, validator  # noqa: E402
from cnucoin.db import fmt, to_cents  # noqa: E402

DB_PATH = Path(os.environ.get("CNUCOIN_DB", ROOT / "output" / "cnucoin_web.db"))

app = Flask(__name__)
app.secret_key = "cnucoin-lab-demo"
app.jinja_env.filters["cnu"] = fmt
app.jinja_env.filters["short"] = lambda h, n=10: f"{h[:n]}…{h[-4:]}" if h and len(h) > n + 4 else (h or "—")
app.jinja_env.globals["CHECK_TITLES"] = validator.CHECK_TITLES


def get_conn():
    if "conn" not in g:
        DB_PATH.parent.mkdir(exist_ok=True)
        g.conn = db.init_db(DB_PATH)
    return g.conn


@app.teardown_appcontext
def close_conn(_exc):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()


def aliases(conn) -> dict[str, str]:
    return {m["CNUCoinID"]: m["Alias"] for m in members.list_members(conn)}


@app.route("/")
def index():
    conn = get_conn()
    blocks = mining.mined_blocks(conn)
    stats = {
        "members": len(members.list_members(conn)),
        "miners": conn.execute("SELECT COUNT(*) FROM CnuCoinMembersTable WHERE IsMiner = 1").fetchone()[0],
        "blocks": len(blocks) - 1,
        "pending": len(transactions.pending_transactions(conn)),
        "supply": conn.execute("SELECT COALESCE(SUM(TASum), 0) FROM EWalletTable").fetchone()[0],
    }
    miners = conn.execute("SELECT * FROM CnuCoinMembersTable WHERE IsMiner = 1").fetchall()
    return render_template("index.html", stats=stats, blocks=blocks[-8:], miners=miners,
                           pending=transactions.pending_transactions(conn), names=aliases(conn),
                           audit=validator.validate_chain(conn), crypto=crypto)


@app.route("/members", methods=["GET", "POST"])
def members_page():
    conn = get_conn()
    if request.method == "POST":
        try:
            m = members.register(conn, request.form["alias"], is_miner="is_miner" in request.form,
                                 initial_cents=to_cents(request.form.get("initial") or 0))
            flash(f"Учасника «{m['Alias']}» зареєстровано. Адреса: {m['CNUCoinID']}", "ok")
            return redirect(url_for("wallet", cnucoin_id=m["CNUCoinID"]))
        except (ValueError, members.RegistrationError) as e:
            flash(str(e), "error")
    rows = [(m, members.balances(conn, m["CNUCoinID"])) for m in members.list_members(conn)]
    return render_template("members.html", rows=rows)


@app.route("/wallet/<cnucoin_id>")
def wallet(cnucoin_id):
    conn = get_conn()
    member = members.get_member(conn, cnucoin_id)
    if member is None:
        flash("Учасника не знайдено", "error")
        return redirect(url_for("members_page"))
    others = [m for m in members.list_members(conn) if m["CNUCoinID"] != cnucoin_id]
    return render_template("wallet.html", m=member, bal=members.balances(conn, cnucoin_id),
                           history=members.wallet_history(conn, cnucoin_id), others=others,
                           names=aliases(conn), private_key=members.private_key(conn, cnucoin_id))


@app.post("/send")
def send():
    conn = get_conn()
    sender = request.form["sender"]
    try:
        tx = transactions.create_transaction(conn, sender, request.form["recipient"],
                                             to_cents(request.form["amount"]))
        flash(f"Транзакцію #{tx['TAID']} підписано та надіслано. TAHash = {tx['TAHash']}. "
              f"Очікує на майнінг.", "ok")
    except (ValueError, transactions.TransactionError) as e:
        flash(str(e), "error")
    return redirect(url_for("wallet", cnucoin_id=sender))


@app.post("/mine")
def mine():
    conn = get_conn()
    try:
        result = mining.mine_next(conn, request.form["miner"], int(request.form.get("difficulty", 1)))
        if result is None:
            flash("Черга транзакцій порожня — нічого майнити", "error")
        else:
            flash(f"Блок #{result['BlockID']} видобуто: Nonce = {result['Nonce']}, "
                  f"{result['Attempts']} спроб за {result['MiningTimeMs']:.2f} мс. "
                  f"Хеш {result['BlockChainHash']}. Винагорода {fmt(result['Reward'])} CNU.", "ok")
    except mining.MiningError as e:
        flash(str(e), "error")
    return redirect(request.referrer or url_for("index"))


@app.route("/explorer")
def explorer():
    conn = get_conn()
    return render_template("explorer.html", blocks=list(reversed(mining.mined_blocks(conn))),
                           txs=transactions.list_transactions(conn), audit=validator.validate_chain(conn),
                           names=aliases(conn))


@app.post("/seed")
def seed():
    conn = get_conn()
    if members.list_members(conn):
        flash("База вже містить учасників", "error")
        return redirect(url_for("index"))
    people = {alias: members.register(conn, alias, is_miner=miner, initial_cents=to_cents(amount))["CNUCoinID"]
              for alias, miner, amount in [("Олена", False, 1000), ("Андрій", False, 500), ("Марія", False, 750),
                                           ("Тарас", True, 50), ("Ірина", True, 50)]}
    transactions.create_transaction(conn, people["Олена"], people["Андрій"], to_cents(125.5))
    mining.mine_next(conn, people["Тарас"])
    transactions.create_transaction(conn, people["Андрій"], people["Марія"], to_cents(200))
    mining.mine_next(conn, people["Ірина"], difficulty=2)
    transactions.create_transaction(conn, people["Марія"], people["Олена"], to_cents(300))
    flash("Демо-дані створено: 5 учасників, 2 блоки, 1 транзакція в черзі на майнінг", "ok")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
