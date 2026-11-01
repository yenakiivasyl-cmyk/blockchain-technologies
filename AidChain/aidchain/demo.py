"""Демонстраційний сценарій: три вузли, вигадані фонд, донори, постачальники та отримувачі.

Усі організації та люди вигадані. Документи (рахунки, ТТН, акти) лежать у samples/
і «закріплюються» в блокчейні своїми SHA-256 хешами.
"""
from __future__ import annotations

from pathlib import Path

from .crypto import sha256
from .network import Network

SAMPLES = Path(__file__).resolve().parents[1] / "samples"

DOCUMENTS = {
    "invoice_generators.txt": """РАХУНОК-ФАКТУРА № ЕН-2026/117
Постачальник: ТОВ «ЕнергоБуд» (умовна компанія)
Покупець: БФ «Світанок» (умовний фонд)
1. Генератор інверторний 7.5 кВт      × 3  =  162 000 ₴
2. Блок автоматичного вводу резерву  × 3  =   27 000 ₴
РАЗОМ: 189 000 ₴
""",
    "invoice_drones.txt": """РАХУНОК-ФАКТУРА № ДТ-0931
Постачальник: ТОВ «ДронТех» (умовна компанія)
Покупець: БФ «Світанок» (умовний фонд)
1. FPV-дрон 10" з комплектом батарей   × 20 =  240 000 ₴
2. Тепловізійний монокуляр             × 2  =  110 000 ₴
РАЗОМ: 350 000 ₴
""",
    "waybill_generators.txt": """ТОВАРНО-ТРАНСПОРТНА НАКЛАДНА № 20450011223344
Відправник: ТОВ «ЕнергоБуд»   Отримувач: МЦ «Надія» (умовний)
Вантаж: генератори 3 шт., блоки АВР 3 шт.   Вага: 312 кг
""",
    "act_generators.txt": """АКТ ПРИЙМАННЯ-ПЕРЕДАЧІ № 14
Медичний центр «Надія» (умовний) отримав від БФ «Світанок»:
генератори інверторні 7.5 кВт — 3 шт., блоки АВР — 3 шт.
Претензій до кількості та якості немає.
""",
}


def doc_hash(filename: str) -> str:
    return sha256((SAMPLES / filename).read_bytes())


def write_samples() -> None:
    SAMPLES.mkdir(exist_ok=True)
    for filename, text in DOCUMENTS.items():
        (SAMPLES / filename).write_text(text, encoding="utf-8", newline="\n")
    forged = DOCUMENTS["invoice_drones.txt"].replace("240 000", "340 000").replace("350 000", "450 000")
    (SAMPLES / "invoice_drones_FORGED.txt").write_text(forged, encoding="utf-8", newline="\n")


def build_demo(path: Path | None = None) -> Network:
    write_samples()
    net = Network(path)
    kyiv = net.add_node("kyiv", "Вузол Київ", "Київ").id
    lviv = net.add_node("lviv", "Вузол Львів", "Львів").id
    cv = net.add_node("cv", "Вузол Чернівці", "Чернівці").id

    def actor(name: str, role: str) -> str:
        addr = net.new_wallet().address
        net.submit(addr, "REGISTER", {"name": name, "role": role})
        return addr

    fund = actor("БФ «Світанок»", "FUND")
    olena = actor("Олена Коваль", "DONOR")
    andrii = actor("Андрій Мельник", "DONOR")
    it = actor("IT-компанія «Карпати Софт»", "DONOR")
    maria = actor("Марія Савчук", "DONOR")
    energo = actor("ТОВ «ЕнергоБуд»", "SUPPLIER")
    drone = actor("ТОВ «ДронТех»", "SUPPLIER")
    med = actor("ТОВ «МедПостач»", "SUPPLIER")
    hospital = actor("МЦ «Надія»", "RECIPIENT")
    unit = actor("Добровольчий підрозділ «Буковина»", "RECIPIENT")
    net.mine(kyiv)

    gens = net.submit(fund, "CAMPAIGN", {"title": "Генератори для медичного центру", "goal": 200_000,
                                          "recipient": hospital, "description": "Безперебійне живлення операційних"}).txid
    drones = net.submit(fund, "CAMPAIGN", {"title": "FPV-дрони та тепловізори", "goal": 400_000,
                                            "recipient": unit, "description": "Посилення аеророзвідки"}).txid
    ifak = net.submit(fund, "CAMPAIGN", {"title": "Тактичні аптечки IFAK", "goal": 120_000,
                                          "recipient": unit, "description": "100 укомплектованих аптечок"}).txid
    net.mine(lviv)

    for donor, campaign, amount, msg in [
        (olena, gens, 15_000, "Світла лікарям!"), (it, gens, 150_000, "Від команди Карпати Софт"),
        (andrii, gens, 30_000, ""), (it, drones, 250_000, ""), (maria, drones, 20_000, "Слава Україні"),
        (andrii, drones, 95_000, "За Буковину"), (olena, ifak, 10_000, ""), (maria, ifak, 8_000, ""),
    ]:
        net.submit(donor, "DONATION", {"campaign": campaign, "amount": amount, "message": msg})
    net.mine(cv)

    p1 = net.submit(fund, "PURCHASE", {"campaign": gens, "supplier": energo, "invoice_hash": doc_hash("invoice_generators.txt"),
                                       "items": [{"name": "Генератор 7.5 кВт", "qty": 3, "price": 54_000},
                                                 {"name": "Блок АВР", "qty": 3, "price": 9_000}]}).txid
    p2 = net.submit(fund, "PURCHASE", {"campaign": drones, "supplier": drone, "invoice_hash": doc_hash("invoice_drones.txt"),
                                       "items": [{"name": "FPV-дрон 10\"", "qty": 20, "price": 12_000},
                                                 {"name": "Тепловізор", "qty": 2, "price": 55_000}]}).txid
    net.submit(fund, "PURCHASE", {"campaign": ifak, "supplier": med,
                                  "items": [{"name": "Аптечка IFAK", "qty": 15, "price": 1_150}]})
    net.mine(kyiv)

    s1 = net.submit(energo, "SHIPMENT", {"purchase": p1, "tracking": "20450011223344",
                                         "waybill_hash": doc_hash("waybill_generators.txt")}).txid
    net.submit(drone, "SHIPMENT", {"purchase": p2, "tracking": "20450099887766"})
    net.mine(lviv)

    net.submit(hospital, "RECEIPT", {"shipment": s1, "status": "OK", "note": "Генератори встановлено в операційному блоці",
                                     "photo_hash": doc_hash("act_generators.txt")})
    net.mine(cv)

    # трохи «живої» роботи для демонстрації: донат у mempool, ще не в блоці
    net.submit(maria, "DONATION", {"campaign": ifak, "amount": 5_000, "message": "На аптечки"})
    net.event("info", "Демо-мережу створено: 3 вузли, 10 учасників, 3 збори")
    net.save()
    return net
