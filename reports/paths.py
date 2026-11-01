from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CNU = ROOT / "CNUCoin"
AID = ROOT / "AidChain"
OUT = CNU / "output"
IMG = ROOT / "reports" / "img"


def read_src(path: Path, start: str | None = None, end: str | None = None) -> str:
    """Текст файлу або його фрагмент від рядка з `start` до рядка з `end` (не включно)."""
    text = path.read_text(encoding="utf-8")
    if start:
        text = text[text.index(start):]
    if end:
        text = text[:text.index(end)]
    return text.rstrip() + "\n"

REPORTS = ROOT / "Звіти"
REPORTS.mkdir(exist_ok=True)
