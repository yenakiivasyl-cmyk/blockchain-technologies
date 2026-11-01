"""ЛР №2. Майнінг CNUCoin.

Запуск:  python lab2_protocol.py   (після python lab1_protocol.py)
Працює з копією БД ЛР №1 (output/cnucoin_lab2.db), тому скрипт можна запускати повторно.
"""
import secrets
import shutil
import statistics

from cnucoin import crypto, db, members, mining, transactions, validator
from cnucoin.db import fmt, to_cents
from lab1_protocol import DB_PATH as LAB1_DB
from protocol import OUTPUT, Protocol, short

DB_PATH = OUTPUT / "cnucoin_lab2.db"
TAMPER_DB = OUTPUT / "cnucoin_tampered.db"
EXPERIMENT = {1: 40, 2: 40, 3: 20, 4: 10, 5: 4}  # складність -> кількість прогонів


def by_alias(conn, alias):
    return conn.execute("SELECT CNUCoinID FROM CnuCoinMembersTable WHERE Alias = ?", (alias,)).fetchone()[0]


def describe_mining(p: Protocol, r: dict) -> None:
    p.kv("Попередній блок", f"#{r['PrevBlockID']}  {r['PrevHash']}")
    p.kv("TAHash транзакції", r["TAHash"])
    p.line("Перебір «солі»: SHA-256(TAHash + BlockChainHash + Nonce)")
    for nonce, h in r["Trace"]:
        mark = "  ← знайдено!" if nonce == r["Nonce"] else ""
        p.line(f"  Nonce = {nonce:<4} => {h}{mark}")
    if r["Nonce"] >= len(r["Trace"]):
        p.line("  …")
        p.line(f"  Nonce = {r['Nonce']:<4} => {r['BlockChainHash']}  ← знайдено!")
    p.kv("BlockChainHash", r["BlockChainHash"])
    p.kv("Nonce («сіль»)", r["Nonce"])
    p.kv("Спроб / час", f"{r['Attempts']} хешів за {r['MiningTimeMs']:.3f} мс")
    p.kv("Винагорода майнеру", f"{fmt(r['Reward'])} CNU ({mining.REWARD_PERCENT}% від суми)")
    p.kv("BlockAssign (ЕЦП)", short(r["BlockAssign"], 40))


def balances_table(p: Protocol, conn) -> dict:
    out = {}
    for m in members.list_members(conn):
        b = members.balances(conn, m["CNUCoinID"])
        out[m["Alias"]] = b
        p.line(f"{m['Alias']:<16} усього {fmt(b['total']):>9}   доступно {fmt(b['spendable']):>9}   "
               f"заблоковано {fmt(b['locked']):>7}")
    return out


def difficulty_experiment(p: Protocol) -> list[dict]:
    rows = []
    for difficulty, runs in EXPERIMENT.items():
        attempts, times = [], []
        for _ in range(runs):
            r = mining.proof_of_work(crypto.sha256(secrets.token_bytes(32)), crypto.sha256(secrets.token_bytes(32)),
                                     difficulty)
            attempts.append(r["attempts"])
            times.append(r["elapsed_ms"])
        row = {
            "difficulty": difficulty,
            "runs": runs,
            "expected": 16 ** difficulty,
            "avg_attempts": statistics.mean(attempts),
            "avg_ms": statistics.mean(times),
            "max_ms": max(times),
        }
        rows.append(row)
        p.line(f"{difficulty:^10} {runs:^8} {row['expected']:>12,} {row['avg_attempts']:>14,.0f} "
               f"{row['avg_ms']:>12.2f} {row['max_ms']:>12.2f}".replace(",", " "))
    return rows


def main() -> None:
    if not LAB1_DB.exists():
        raise SystemExit("Спочатку виконайте: python lab1_protocol.py")
    shutil.copy(LAB1_DB, DB_PATH)
    conn = db.connect(DB_PATH)

    olena, andrii, maria = (by_alias(conn, a) for a in ("Олена", "Андрій", "Марія"))
    taras, iryna = by_alias(conn, "Тарас (майнер)"), by_alias(conn, "Ірина (майнер)")

    p = Protocol("lab2")
    p.title("ЛР №2 · CNUCoin · Майнінг (Proof-of-Work)")

    p.step("Вихідний стан: черга непідтверджених транзакцій з ЛР №1")
    for tx in transactions.pending_transactions(conn):
        p.line(f"TAID {tx['TAID']}  {tx['TADate']}  {fmt(tx['TASum'])} CNU  TAHash {short(tx['TAHash'])}  "
               f"TAApproved={tx['TAApproved']}")
    p.kv("Difficulty Target", f"хеш-образ починається з «{'0' * mining.DEFAULT_DIFFICULTY}»")

    p.step("Спроба майнінгу учасником без права (IsMiner = 0)")
    try:
        mining.mine_next(conn, olena)
    except mining.MiningError as e:
        p.ok(f"Відмовлено: {e}")

    p.step("Майнер «Тарас» видобуває блок для першої транзакції")
    block1 = mining.mine_next(conn, taras)
    describe_mining(p, block1)
    p.ok(f"Блок #{block1['BlockID']} записано в BlockChainTable; транзакцію #{block1['TAID']} внесено до ланцюжка")

    p.step("Стан після першого блоку: кошти отримувача ще заблоковані")
    tx1 = conn.execute("SELECT * FROM TransactionsTable WHERE TAID = 1").fetchone()
    p.kv("TransactionsTable #1", f"TAApproved = {tx1['TAApproved']}, Nonce = {tx1['Nonce']}")
    p.kv("Підтверджень блоку #1", "0 (потрібен наступний блок)")
    balances_after_1 = balances_table(p, conn)
    try:
        transactions.create_transaction(conn, andrii, maria, to_cents(600))
    except transactions.TransactionError as e:
        p.ok(f"Андрій не може витратити ще не підтверджені 125.50 CNU: {e}")

    p.step("Нова транзакція Андрій → Марія (200 CNU) та її майнінг майнером «Ірина»")
    tx2 = transactions.create_transaction(conn, andrii, maria, to_cents(200))
    p.kv("TAID / TAHash", f"{tx2['TAID']} / {tx2['TAHash']}")
    p.kv("Хешувалась з BlockChainHash", f"{short(tx2['ChainHash'])} (блок #1), Nonce {tx2['ChainNonce']}")
    block2 = mining.mine_next(conn, iryna)
    describe_mining(p, block2)
    p.ok(f"Блок #{block2['BlockID']} містить хеш блоку #{block2['ConfirmedBlockID']} → "
         f"транзакцію #{block1['TAID']} ПІДТВЕРДЖЕНО, кошти розблоковано")

    p.step("Третя транзакція Марія → Олена (300 CNU) підтверджує блок #2")
    tx3 = transactions.create_transaction(conn, maria, olena, to_cents(300))
    block3 = mining.mine_next(conn, taras)
    describe_mining(p, block3)

    p.step("Баланси учасників після трьох блоків")
    final_balances = balances_table(p, conn)

    p.step("Ланцюжок блоків")
    chain = [dict(b) for b in mining.mined_blocks(conn)]
    for b in chain:
        conf = conn.execute("SELECT COUNT(*) FROM BlockChainTable WHERE IsMined = 1 AND BlockID > ?",
                            (b["BlockID"],)).fetchone()[0]
        b["Confirmations"] = conf
        who = b["MinerAlias"] or "—"
        p.line(f"#{b['BlockID']}  {short(b['BlockChainHash'], 20)}  Nonce={b['Nonce']:<4} "
               f"prev={short(b['PrevHash'] or '', 10)}  майнер: {who:<16} підтверджень: {conf}")

    p.step("Аудит цілісності ланцюжка")
    audit = validator.validate_chain(conn)
    for blk in audit["blocks"]:
        p.line(f"Блок #{blk['BlockID']}: " + ", ".join(
            f"{validator.CHECK_TITLES[k]} {'✔' if v else '✘'}" for k, v in blk["checks"].items()))
    (p.ok if audit["ok"] else p.fail)("Ланцюжок цілісний" if audit["ok"] else "Ланцюжок пошкоджено")

    p.step("Атака: зловмисник змінює суму транзакції #1 у копії БД (125.50 → 12 550.00 CNU)")
    conn.close()
    shutil.copy(DB_PATH, TAMPER_DB)
    evil = db.connect(TAMPER_DB)
    evil.execute("UPDATE TransactionsTable SET TASum = 1255000 WHERE TAID = 1")
    evil.commit()
    tamper_audit = validator.validate_chain(evil)
    for blk in tamper_audit["blocks"]:
        bad = [validator.CHECK_TITLES[k] for k, v in blk["checks"].items() if not v]
        (p.fail if bad else p.ok)(f"Блок #{blk['BlockID']}: " + ("порушено — " + ", ".join(bad) if bad else "OK"))
    p.ok("Підробку виявлено: змінений вміст не відповідає хеш-образу, підписаному відправником")
    evil.close()

    p.step("Експеримент: як складність (кількість нулів) впливає на час майнінгу")
    p.line(f"{'Нулів':^10} {'Прогонів':^8} {'Очік. спроб':>12} {'Сер. спроб':>14} {'Сер. мс':>12} {'Макс. мс':>12}")
    experiment = difficulty_experiment(p)
    p.line("Кожен додатковий нуль у Difficulty Target збільшує роботу ≈ у 16 разів.")

    p.data = {
        "blocks_mined": [block1, block2, block3],
        "transactions": [dict(tx1), tx2, tx3],
        "balances_after_block1": balances_after_1,
        "final_balances": final_balances,
        "chain": chain,
        "audit": audit,
        "tamper_audit": tamper_audit,
        "experiment": experiment,
        "reward_percent": mining.REWARD_PERCENT,
    }
    p.save()


if __name__ == "__main__":
    main()
