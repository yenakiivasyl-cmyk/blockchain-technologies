"""Діаграми для звітів (matplotlib -> PNG)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

IMG = Path(__file__).resolve().parent / "img"
IMG.mkdir(exist_ok=True)

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
INK, MUTED, BLUE, GOLD, GREEN, RED, VIOLET = "#1f2937", "#6b7280", "#2f6fdb", "#d99a00", "#1f9d6b", "#d64545", "#7c5cd6"


def _canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h), dpi=170)
    ax.set_xlim(0, w * 10)
    ax.set_ylim(0, h * 10)
    ax.axis("off")
    return fig, ax


def _save(fig, name):
    path = IMG / name
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def box(ax, x, y, w, h, title, lines=(), color=BLUE, title_size=10.5, line_size=8.6):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.2",
                                fc="white", ec=color, lw=1.6))
    ax.add_patch(FancyBboxPatch((x, y + h - 5), w, 5, boxstyle="round,pad=0.3,rounding_size=1.2",
                                fc=color, ec=color, lw=1.6))
    ax.text(x + w / 2, y + h - 2.5, title, ha="center", va="center", color="white", fontsize=title_size, weight="bold")
    for i, line in enumerate(lines):
        weight = "bold" if line.startswith("🔑") or line.startswith("PK") else "normal"
        ax.text(x + 1.5, y + h - 8.5 - i * 3.6, line.replace("🔑", "PK"), va="center", fontsize=line_size,
                color=INK, family="DejaVu Sans Mono", weight=weight)


def pill(ax, x, y, w, h, text, color=BLUE, fc=None, size=9.5, text_color=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=2",
                                fc=fc or "white", ec=color, lw=1.6))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, color=text_color or INK,
            wrap=True)


def arrow(ax, x1, y1, x2, y2, color=MUTED, text=None, style="-|>", rad=0.0, size=8.5, lw=1.4):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=13, color=color, lw=lw,
                                 connectionstyle=f"arc3,rad={rad}"))
    if text:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 1.6, text, ha="center", fontsize=size, color=color,
                bbox=dict(fc="white", ec="none", pad=0.6))


# ─────────────────────────── CNUCoin ───────────────────────────

def cnucoin_er():
    fig, ax = _canvas(15, 8.6)
    box(ax, 2, 50, 38, 32, "CnuCoinMembersTable", [
        "PK CNUCoinID   TEXT  SHA-256(PK)", "   Alias        TEXT", "   PublicKey    TEXT  UNIQUE",
        "   IsMiner      INT   0/1", "   RegDate      TEXT"], BLUE)
    box(ax, 2, 18, 38, 22, "PrivateTable  (приватна)", [
        "PK,FK CNUCoinID  TEXT", "   PrivateKey    TEXT  PEM", "   PublicKey     TEXT  PEM"], RED)
    box(ax, 2, -22, 38, 33, "EWalletTable  (гаманець)", [
        "PK EntryID     INT", "FK CNUCoinID   TEXT", "   TADate      TEXT", "   TAFrom/TATo TEXT",
        "   TASum       INT  ±cent", "   Kind  GENESIS|TRANSFER|REWARD", "FK TAID, BlockID"], GOLD)
    box(ax, 55, 18, 40, 64, "TransactionsTable", [
        "PK TAID          INT", "FK CNUCoinID     TEXT  автор", "   TADate        TEXT",
        "FK TAFrom        TEXT", "FK TATo          TEXT", "   TASum         INT   cent",
        "   PrevBlockHash TEXT", "   PrevNonce     INT", "   TAHash        TEXT  UNIQUE",
        "   Nonce         INT   (майнер)", "   TAApproved    INT   0/1", "   TASign        TEXT  ECDSA"], GREEN)
    box(ax, 108, 18, 40, 64, "BlockChainTable", [
        "PK BlockID       INT  0=генезис", "FK TAID          INT  UNIQUE", "FK MinerID       TEXT",
        "   DateTime      TEXT", "   PrevHash      TEXT", "   TAHash        TEXT",
        "   BlockChainHash TEXT", "   Nonce         INT", "   Difficulty    INT",
        "   Attempts      INT", "   MiningTimeMs  REAL", "   Reward        INT", "   BlockAssign   TEXT ECDSA",
        "   IsMined       INT  0/1"], VIOLET, line_size=8.2)
    arrow(ax, 21, 50, 21, 40.6, BLUE, "1 : 1")
    arrow(ax, 1.6, 66, 1.6, 0, BLUE, "1 : N", rad=0.45)
    arrow(ax, 40.3, 70, 54.7, 70, BLUE, "1 : N")
    arrow(ax, 95.3, 70, 107.7, 70, GREEN, "1 : 1")
    arrow(ax, 128, 82.5, 30, 82.5, VIOLET, "MinerID → CNUCoinID  (N : 1)", style="-|>", rad=0.12)
    arrow(ax, 75, 18, 40.3, 2, GOLD, "TAID", rad=-0.15)
    ax.text(75, -27, "Публічні таблиці доступні всім учасникам; PrivateTable — лише власнику ідентифікатора.",
            ha="center", fontsize=9, color=MUTED, style="italic")
    ax.set_xlim(-14, 150)
    ax.set_ylim(-30, 90)
    return _save(fig, "cnu_er.png")


def cnucoin_tx_flow():
    fig, ax = _canvas(15, 3.6)
    steps = [("Поля транзакції\nавтор, дата, TAID,\nFrom, To, TASum", BLUE),
             ("+ BlockChainHash\nі Nonce останнього\nблоку (0 для 1-ї)", VIOLET),
             ("Конкатенація\nчерез «|»", MUTED),
             ("TAHash =\nSHA-256(…)", GOLD),
             ("TASign =\nECDSA(priv, TAHash)", RED),
             ("Запис у\nTransactionsTable +\nBlockChainTable", GREEN)]
    w, gap = 21, 4.2
    for i, (text, color) in enumerate(steps):
        x = 2 + i * (w + gap)
        pill(ax, x, 6, w, 22, text, color, size=9)
        if i:
            arrow(ax, x - gap + 0.2, 17, x - 0.2, 17, INK)
    return _save(fig, "cnu_tx_flow.png")


def mining_flowchart():
    fig, ax = _canvas(9, 12)
    cx = 45
    items = [
        (108, "Майнер IsMiner = 1 ?", RED, "ні → відмова"),
        (94, "Взяти першу непідтверджену\nтранзакцію (за TADate)", BLUE, None),
        (80, "Перевірити TAHash та ЕЦП відправника", BLUE, None),
        (66, "Nonce := 0", MUTED, None),
        (52, "H := SHA-256(TAHash ∥ PrevHash ∥ Nonce)", GOLD, None),
        (38, "H починається з «0» × difficulty ?", RED, None),
        (24, "Записати BlockChainHash, Nonce;\nTAApproved := 1; ЕЦП майнера", GREEN, None),
        (10, "Зарахувати кошти + винагороду 5 %;\nпопередній блок підтверджено", GREEN, None),
    ]
    for y, text, color, note in items:
        pill(ax, cx - 30, y, 60, 9, text, color, size=9.2)
        if note:
            ax.text(cx + 32, y + 4.5, note, fontsize=8.5, color=RED, va="center")
    for (y1, *_), (y2, *_) in zip(items, items[1:]):
        arrow(ax, cx, y1 - 0.4, cx, y2 + 9.4, INK)
    ax.text(cx + 2, 33.5, "так", fontsize=8.5, color=GREEN)
    arrow(ax, cx + 30.4, 42.5, cx + 30.4, 56.5, RED, rad=0.6)
    ax.text(cx + 37, 49, "ні:\nNonce += 1", fontsize=8.5, color=RED, va="center")
    return _save(fig, "cnu_mining_flow.png")


def difficulty_chart(rows):
    fig, ax1 = plt.subplots(figsize=(8, 4.2), dpi=170)
    d = [r["difficulty"] for r in rows]
    ax1.bar(d, [r["avg_attempts"] for r in rows], color=BLUE, alpha=.85, label="Середня кількість спроб")
    ax1.plot(d, [r["expected"] for r in rows], "o--", color=GOLD, label="Теоретично 16^d")
    ax1.set_yscale("log")
    ax1.set_xlabel("Difficulty — кількість нулів на початку хешу")
    ax1.set_ylabel("Спроб (лог. шкала)")
    ax1.set_xticks(d)
    ax2 = ax1.twinx()
    ax2.plot(d, [r["avg_ms"] for r in rows], "s-", color=RED, label="Середній час, мс")
    ax2.set_yscale("log")
    ax2.set_ylabel("Час, мс (лог. шкала)")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", frameon=False)
    ax1.spines[["top"]].set_visible(False)
    ax2.spines[["top"]].set_visible(False)
    ax1.set_title("Вплив складності на майнінг CNUCoin", weight="bold")
    return _save(fig, "cnu_difficulty.png")


def chain_diagram(blocks):
    fig, ax = _canvas(15, 3.4)
    w, gap = 30, 6.5
    for i, b in enumerate(blocks):
        x = 2 + i * (w + gap)
        color = MUTED if b["BlockID"] == 0 else BLUE
        title = "Блок #0 (генезис)" if b["BlockID"] == 0 else f"Блок #{b['BlockID']}"
        lines = [f"hash {b['BlockChainHash'][:14]}…", f"prev {(b['PrevHash'] or '')[:14]}…", f"Nonce {b['Nonce']}"]
        if b["BlockID"]:
            lines.append(f"{b.get('FromAlias')}→{b.get('ToAlias')}")
        box(ax, x, 2, w, 28, title, lines, color, line_size=7.6)
        if i:
            arrow(ax, x - gap + 0.3, 16, x - 0.3, 16, GOLD, lw=2)
    return _save(fig, "cnu_chain.png")


# ─────────────────────────── AidChain ───────────────────────────

def aid_architecture():
    fig, ax = _canvas(15, 8.5)
    pill(ax, 4, 70, 140, 10, "Браузер · односторінковий інтерфейс (HTML + CSS + JavaScript, Web Crypto для SHA-256 файлів)", BLUE, size=10)
    pill(ax, 4, 54, 140, 10, "Flask REST API  ·  /api/state  /api/tx  /api/mine  /api/consensus  /api/tamper  /api/trace  /api/proof  /api/verify", VIOLET, size=9.5)
    arrow(ax, 74, 69.6, 74, 64.4, INK, "JSON / multipart")
    for i, (name, city) in enumerate([("Вузол Київ", "ланцюжок + mempool"), ("Вузол Львів", "ланцюжок + mempool"),
                                      ("Вузол Чернівці", "ланцюжок + mempool")]):
        x = 6 + i * 48
        box(ax, x, 22, 40, 24, name, [city, "незалежна валідація", "майнінг PoW", "ключ Ed25519 вузла"], GREEN)
        arrow(ax, 74, 53.6, x + 20, 46.6, MUTED)
    arrow(ax, 46.4, 34, 53.6, 34, GOLD, style="<|-|>")
    arrow(ax, 94.4, 34, 101.6, 34, GOLD, style="<|-|>")
    ax.text(74, 18, "P2P: розсилання транзакцій і блоків · консенсус Накамото (максимальна сумарна робота)",
            ha="center", fontsize=9, color=GOLD)
    for i, (name, desc) in enumerate([("crypto.py", "SHA-256, Ed25519, адреси"), ("merkle.py", "корінь, доведення"),
                                      ("ledger.py", "Tx, Block, правила, аудит"), ("network.py", "вузли, консенсус"),
                                      ("views.py", "трасування, документи")]):
        pill(ax, 4 + i * 29, 2, 26, 10, f"{name}\n{desc}", MUTED, size=8.3)
    return _save(fig, "aid_architecture.png")


def aid_lifecycle():
    fig, ax = _canvas(15, 4.6)
    steps = [("REGISTER", "учасник +\nпублічний ключ", MUTED), ("CAMPAIGN", "фонд відкриває\nзбір", BLUE),
             ("DONATION", "донор робить\nвнесок", GOLD), ("PURCHASE", "фонд купує\n≤ залишку збору", VIOLET),
             ("SHIPMENT", "постачальник\nвідвантажує", RED), ("RECEIPT", "отримувач\nпідтверджує", GREEN)]
    w, gap = 21, 4.2
    for i, (t, d, color) in enumerate(steps):
        x = 2 + i * (w + gap)
        pill(ax, x, 18, w, 9, t, color, fc=color, size=10, text_color="white")
        ax.text(x + w / 2, 11, d, ha="center", va="center", fontsize=8.8, color=INK)
        if i:
            arrow(ax, x - gap + 0.2, 22.5, x - 0.2, 22.5, INK)
    ax.text(77, 37, "Кожен крок — транзакція, підписана ключем Ed25519 відповідної ролі; хеші документів (рахунок, ТТН, акт) закріплюються в ній",
            ha="center", fontsize=9, color=MUTED, style="italic")
    return _save(fig, "aid_lifecycle.png")


def aid_sequence():
    fig, ax = _canvas(15, 8)
    cols = [("Донор\n(гаманець)", 14), ("API", 40), ("Вузол Київ", 68), ("Вузол Львів", 96), ("Вузол Чернівці", 124)]
    for name, x in cols:
        pill(ax, x - 11, 70, 22, 8, name, BLUE, size=8.8)
        ax.plot([x, x], [2, 69.6], color="#cbd5e1", lw=1.2, ls="--")
    msgs = [
        (14, 40, 63, "DONATION + ЕЦП Ed25519", GOLD),
        (40, 68, 56, "receive_tx: перевірка ЕЦП і правил", INK),
        (40, 96, 51, "receive_tx", INK),
        (40, 124, 46, "receive_tx", INK),
        (68, 68, 38, "mine(): Merkle + PoW (0000…) + ЕЦП вузла", GREEN),
        (68, 96, 28, "блок #N → validate_block (7 перевірок)", VIOLET),
        (68, 124, 21, "блок #N → validate_block", VIOLET),
        (124, 68, 11, "форк? → consensus(): найбільша сумарна робота", RED),
    ]
    for x1, x2, y, text, color in msgs:
        if x1 == x2:
            ax.add_patch(FancyBboxPatch((x1 - 1, y - 3), 2, 6, boxstyle="round,pad=0.2", fc=color, ec=color))
            ax.text(x1 + 3, y, text, fontsize=8.6, color=color, va="center")
        else:
            arrow(ax, x1, y, x2, y, color, text, size=8.3)
    return _save(fig, "aid_sequence.png")


def aid_block_structure():
    fig, ax = _canvas(15, 6.2)
    box(ax, 2, 6, 60, 50, "Заголовок блоку", [
        "index        номер блоку", "timestamp    час створення", "prev_hash    хеш попереднього",
        "merkle_root  корінь дерева tx", "difficulty   4 (0000…)", "miner        адреса вузла",
        "miner_key    публ. ключ вузла", "nonce        «сіль» PoW",
        "", "hash = SHA-256(index|…|miner_key|nonce)", "miner_signature = Ed25519(hash)"], BLUE, line_size=8.4)
    # дерево Меркла
    ax.text(110, 57, "Дерево Меркла", ha="center", fontsize=10.5, weight="bold", color=INK)
    pill(ax, 100, 44, 20, 6, "root", GOLD, size=8.5)
    for i, x in enumerate([84, 116]):
        pill(ax, x, 30, 20, 6, f"H{i * 2}{i * 2 + 1}", VIOLET, size=8.5)
        arrow(ax, x + 10, 36.4, 110, 43.6, MUTED, style="-")
    for i, x in enumerate([76, 92, 108, 124]):
        pill(ax, x, 14, 14, 6, f"tx{i}", GREEN, size=8.5)
        arrow(ax, x + 7, 20.4, (94 if i < 2 else 126), 29.6, MUTED, style="-")
    ax.text(110, 6, "txid = SHA-256(канонічний JSON тіла транзакції)", ha="center", fontsize=8.6, color=MUTED)
    arrow(ax, 62.5, 40, 99.5, 47, GOLD, "merkle_root", rad=-0.1)
    return _save(fig, "aid_block_struct.png")


def aid_usecase():
    fig, ax = _canvas(15, 6.4)
    actors = [("Донор", 6, 50, ["зробити донат", "простежити свій внесок", "перевірити документ"]),
              ("Благодійний фонд", 6, 14, ["відкрити збір", "оформити закупівлю", "закріпити рахунок"]),
              ("Постачальник", 128, 50, ["відвантажити товар", "закріпити ТТН"]),
              ("Отримувач", 128, 14, ["підтвердити отримання", "закріпити фото/акт"])]
    for name, x, y, cases in actors:
        ax.add_patch(plt.Circle((x + 4, y + 6), 2.2, fc="white", ec=INK, lw=1.4))
        ax.plot([x + 4, x + 4], [y + 3.8, y - 2], color=INK, lw=1.4)
        ax.plot([x, x + 8], [y + 1.5, y + 1.5], color=INK, lw=1.4)
        ax.text(x + 4, y - 6, name, ha="center", fontsize=9.5, weight="bold")
        for i, c in enumerate(cases):
            cx = 30 if x < 50 else 76
            cy = y + 8 - i * 7
            ax.add_patch(matplotlib.patches.Ellipse((cx + 21, cy), 40, 6, fc="#eef4ff", ec=BLUE, lw=1.2))
            ax.text(cx + 21, cy, c, ha="center", va="center", fontsize=8.6)
            arrow(ax, x + 9 if x < 50 else x - 1, y + 3, cx + (1 if x < 50 else 41), cy, MUTED, style="-")
    ax.add_patch(FancyBboxPatch((28, 2), 92, 60, boxstyle="round,pad=0.3", fc="none", ec="#94a3b8", lw=1.2, ls="--"))
    ax.text(74, 63.5, "Система AidChain", ha="center", fontsize=10, color=MUTED, weight="bold")
    return _save(fig, "aid_usecase.png")
