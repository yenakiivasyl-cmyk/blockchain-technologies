"""Дерево Меркла: корінь блоку та доведення включення транзакції (SPV-proof)."""
from __future__ import annotations

from .crypto import sha256

EMPTY_ROOT = sha256("")


def _next_level(level: list[str]) -> list[str]:
    if len(level) % 2:
        level = level + [level[-1]]  # непарна кількість — дублюємо останній вузол (як у Bitcoin)
    return [sha256(level[i] + level[i + 1]) for i in range(0, len(level), 2)]


def merkle_root(leaves: list[str]) -> str:
    if not leaves:
        return EMPTY_ROOT
    level = list(leaves)
    while len(level) > 1:
        level = _next_level(level)
    return level[0]


def merkle_proof(leaves: list[str], index: int) -> list[dict]:
    """Список «сусідніх» хешів від листа до кореня."""
    proof, level = [], list(leaves)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        sibling = index ^ 1
        proof.append({"hash": level[sibling], "position": "left" if sibling < index else "right"})
        level = _next_level(level)
        index //= 2
    return proof


def verify_proof(leaf: str, proof: list[dict], root: str) -> bool:
    current = leaf
    for step in proof:
        current = sha256(step["hash"] + current) if step["position"] == "left" else sha256(current + step["hash"])
    return current == root


def tree_levels(leaves: list[str]) -> list[list[str]]:
    """Усі рівні дерева (для візуалізації): [листя, ..., [корінь]]."""
    if not leaves:
        return [[EMPTY_ROOT]]
    levels = [list(leaves)]
    while len(levels[-1]) > 1:
        levels.append(_next_level(levels[-1]))
    return levels
