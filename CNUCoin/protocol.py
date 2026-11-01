"""Допоміжний журнал протоколу: друкує кроки в консоль і зберігає їх у .txt та .json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent / "output"
OUTPUT.mkdir(exist_ok=True)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CYAN, GREEN, RED, DIM, BOLD, RESET = "\033[96m", "\033[92m", "\033[91m", "\033[2m", "\033[1m", "\033[0m"


class Protocol:
    def __init__(self, name: str):
        self.name = name
        self.lines: list[str] = []
        self.data: dict = {}
        self._step = 0

    def _emit(self, text: str, color: str = "") -> None:
        self.lines.append(text)
        print(f"{color}{text}{RESET}" if color else text)

    def title(self, text: str) -> None:
        bar = "═" * 78
        self._emit(bar, CYAN)
        self._emit(f"  {text}", BOLD)
        self._emit(bar, CYAN)

    def step(self, text: str) -> None:
        self._step += 1
        self._emit("")
        self._emit(f"▶ Крок {self._step}. {text}", CYAN)

    def kv(self, key: str, value) -> None:
        self._emit(f"    {key:<26} {value}")

    def line(self, text: str = "", color: str = "") -> None:
        self._emit(f"    {text}" if text else "", color)

    def ok(self, text: str) -> None:
        self._emit(f"    ✔ {text}", GREEN)

    def fail(self, text: str) -> None:
        self._emit(f"    ✘ {text}", RED)

    def save(self) -> None:
        (OUTPUT / f"{self.name}_protocol.txt").write_text("\n".join(self.lines), encoding="utf-8")
        (OUTPUT / f"{self.name}_result.json").write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        print(f"\n{DIM}Протокол збережено: {OUTPUT / (self.name + '_protocol.txt')}{RESET}")


def short(h: str, n: int = 16) -> str:
    return f"{h[:n]}…{h[-6:]}" if h and len(h) > n + 6 else h
