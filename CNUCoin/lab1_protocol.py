"""ЛР №1. Генерування користувачів та транзакцій CNUCoin.

Запуск:  python lab1_protocol.py
Створює чисту БД output/cnucoin.db, реєструє учасників і виконує першу транзакцію.
"""
from cnucoin import crypto, db, members, transactions
from cnucoin.db import fmt, to_cents
from protocol import OUTPUT, Protocol, short

DB_PATH = OUTPUT / "cnucoin.db"

PARTICIPANTS = [  # (псевдонім, майнер?, стартова сума CNU)
    ("Олена", False, 1000),
    ("Андрій", False, 500),
    ("Марія", False, 750),
    ("Тарас (майнер)", True, 50),
    ("Ірина (майнер)", True, 50),
]


def main() -> None:
    p = Protocol("lab1")
    p.title("ЛР №1 · CNUCoin · Генерування користувачів та транзакцій")

    p.step("Створення бази даних CNUCoin")
    DB_PATH.unlink(missing_ok=True)
    conn = db.init_db(DB_PATH)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    p.kv("Файл БД", DB_PATH.name)
    p.kv("Таблиці", ", ".join(tables))
    genesis = transactions.last_mined_block(conn)
    p.kv("Генезис-блок #0", f"BlockChainHash = {short(genesis['BlockChainHash'])}, Nonce = {genesis['Nonce']}")

    p.step("Вибір криптографічних засобів")
    p.kv("Функція хешування", crypto.HASH_ALGORITHM)
    p.kv("ЕЦП", crypto.SIGNATURE_ALGORITHM)
    p.kv("Адреса учасника", "CNUCoinID = SHA-256(PublicKey)")

    p.step("Реєстрація учасників та зарахування стартових CNUCoin")
    registered = []
    for alias, is_miner, amount in PARTICIPANTS:
        m = members.register(conn, alias, is_miner=is_miner, initial_cents=to_cents(amount))
        registered.append(m)
        p.line(f"{'⛏' if is_miner else '👤'} {alias:<16} ID {short(m['CNUCoinID'], 20)}  "
               f"IsMiner={int(is_miner)}  +{amount} CNU")
    sample = registered[0]
    p.line()
    p.line(f"Приклад ключів учасника «{sample['Alias']}»:")
    for row in sample["PublicKey"].strip().splitlines():
        p.line(f"  {row}")
    p.kv("SHA-256(PublicKey)", sample["CNUCoinID"])
    p.ok("Усіх учасників зареєстровано: запис у CnuCoinMembersTable + PrivateTable + EWalletTable")

    p.step("Перелік доступних ідентифікаторів (що бачить відправник)")
    for m in members.list_members(conn):
        p.line(f"{m['Alias']:<16} {m['CNUCoinID']}")

    sender, recipient = registered[0], registered[1]
    amount = to_cents(125.50)
    p.step(f"Перша транзакція: {sender['Alias']} → {recipient['Alias']}, {fmt(amount)} CNU")
    tx = transactions.create_transaction(conn, sender["CNUCoinID"], recipient["CNUCoinID"], amount)
    p.kv("TAID", tx["TAID"])
    p.kv("TADate", tx["TADate"])
    p.kv("BlockChainHash (з табл.)", tx["ChainHash"])
    p.kv("Nonce (з табл.)", tx["ChainNonce"])
    p.line("Конкатенація полів (CNUCoinID|TADate|TAID|From|To|TASum|BlockChainHash|Nonce):")
    p.line(f"  {tx['Payload']}")
    p.kv("TAHash = SHA-256(…)", tx["TAHash"])
    p.kv("TASign (ECDSA, DER hex)", short(tx["TASign"], 40))
    p.ok("TAHash записано у TransactionsTable.TAHash та BlockChainTable.BlockChainHash")

    p.step("Перевірка транзакції будь-яким учасником мережі")
    stored = conn.execute("SELECT * FROM TransactionsTable WHERE TAID = ?", (tx["TAID"],)).fetchone()
    checks = transactions.verify_transaction(conn, stored)
    (p.ok if checks["hash_ok"] else p.fail)("Хеш-образ транзакції збігається з перерахованим")
    (p.ok if checks["sign_ok"] else p.fail)("ЕЦП відправника дійсна (перевірено публічним ключем з реєстру)")
    forged = crypto.verify(registered[2]["PublicKey"], tx["TAHash"], tx["TASign"])
    (p.ok if not forged else p.fail)("Підпис НЕ проходить перевірку чужим публічним ключем (захист від підробки)")

    p.step("Стан після транзакції (очікує підтвердження майнерами)")
    p.kv("TAApproved", stored["TAApproved"])
    p.kv("Nonce", "NULL (заповнить майнер у ЛР №2)")
    for m in registered:
        b = members.balances(conn, m["CNUCoinID"])
        p.line(f"{m['Alias']:<16} усього {fmt(b['total']):>9}   доступно {fmt(b['spendable']):>9}   "
               f"зарезервовано {fmt(b['pending_out']):>7}")

    p.data = {
        "db_path": str(DB_PATH),
        "hash": crypto.HASH_ALGORITHM,
        "signature": crypto.SIGNATURE_ALGORITHM,
        "members": [{k: m[k] for k in ("Alias", "CNUCoinID", "IsMiner", "InitialCents", "PublicKey", "RegDate")}
                    for m in registered],
        "transaction": tx,
        "verify": checks,
        "balances": {m["Alias"]: members.balances(conn, m["CNUCoinID"]) for m in registered},
        "tables": {t: [dict(r) for r in conn.execute(f"SELECT * FROM {t}")] for t in tables},
    }
    p.save()
    conn.close()


if __name__ == "__main__":
    main()
