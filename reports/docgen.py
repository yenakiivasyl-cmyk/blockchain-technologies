"""Тонка обгортка над python-docx для оформлення звітів."""
from __future__ import annotations

import copy
import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

BODY_FONT = "Times New Roman"
MONO_FONT = "Courier New"
BLACK = RGBColor(0, 0, 0)
TEXT_WIDTH_CM = 16.5  # A4 21 см − поля 3 і 1,5 см
TEMPLATE = Path(__file__).resolve().parents[1] / "lab_1.docx"
TEACHER = "Остапов Сергій Едуардович"


def _shade(element, fill: str) -> None:
    pr = element.get_or_add_tcPr() if hasattr(element, "get_or_add_tcPr") else element.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pr.append(shd)


def _field(paragraph, instr: str, placeholder: str = "") -> None:
    run = paragraph.add_run()
    for kind, text in (("begin", None), ("instr", instr), ("separate", None), ("text", placeholder), ("end", None)):
        if kind == "instr":
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        elif kind == "text":
            el = OxmlElement("w:t")
            el.text = text
        else:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        run._r.append(el)


class Report:
    def __init__(self):
        self.doc = Document()
        self.figures = 0
        self.tables = 0
        self._break_before_next = False
        self._setup()

    # ── оформлення ──
    def _setup(self):
        sec = self.doc.sections[0]
        sec.page_height, sec.page_width = Cm(29.7), Cm(21)
        sec.left_margin, sec.right_margin = Cm(3), Cm(1.5)
        sec.top_margin, sec.bottom_margin = Cm(2), Cm(2)
        sec.different_first_page_header_footer = True

        normal = self.doc.styles["Normal"]
        normal.font.name = BODY_FONT
        normal.font.size = Pt(14)
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
        pf = normal.paragraph_format
        pf.line_spacing = 1.25
        pf.space_after = Pt(4)
        pf.first_line_indent = Cm(1.25)
        pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        for level, size in ((1, 16), (2, 14), (3, 14)):
            st = self.doc.styles[f"Heading {level}"]
            st.font.name = BODY_FONT
            st.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
            st.element.rPr.rFonts.set(qn("w:ascii"), BODY_FONT)
            st.element.rPr.rFonts.set(qn("w:hAnsi"), BODY_FONT)
            for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
                st.element.rPr.rFonts.attrib.pop(qn(attr), None)
            st.font.size = Pt(size)
            st.font.bold = True
            st.font.italic = False
            st.font.color.rgb = BLACK
            st.paragraph_format.space_before = Pt(14 if level == 1 else 10)
            st.paragraph_format.space_after = Pt(6)
            st.paragraph_format.first_line_indent = Cm(0)
            st.paragraph_format.keep_with_next = True

        footer = sec.footer.paragraphs[0]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _field(footer, "PAGE", "1")


    # ── текст ──
    def _rich(self, paragraph, text: str, size: float | None = None):
        """`код` — моноширинним; **…** — жирним лише якщо виділено весь абзац."""
        whole_bold = text.startswith("**") and text.endswith("**") and text.count("**") == 2
        if not whole_bold:
            text = text.replace("**", "")
        for part in re.split(r"(\*\*.+?\*\*|`.+?`)", text):
            if not part:
                continue
            if part.startswith("**"):
                run = paragraph.add_run(part[2:-2])
                run.bold = True
            elif part.startswith("`"):
                run = paragraph.add_run(part[1:-1])
                run.font.name = MONO_FONT
                run.font.size = Pt((size or 14) - 2)
            else:
                run = paragraph.add_run(part)
            if size and not part.startswith("`"):
                run.font.size = Pt(size)
        return paragraph

    def p(self, text: str, align=None, indent=True, size=None, space_after=None):
        par = self._rich(self.doc.add_paragraph(), text, size)
        if align is not None:
            par.alignment = align
        if not indent:
            par.paragraph_format.first_line_indent = Cm(0)
        if space_after is not None:
            par.paragraph_format.space_after = Pt(space_after)
        return par

    def h1(self, text):
        heading = self.doc.add_heading(text, 1)
        if self._break_before_next:  # розрив як властивість заголовка — без порожніх сторінок
            heading.paragraph_format.page_break_before = True
            self._break_before_next = False
        return heading

    def h2(self, text):
        return self.doc.add_heading(text, 2)

    def h3(self, text):
        return self.doc.add_heading(text, 3)

    def bullets(self, items, numbered=False):
        if numbered:  # власна нумерація: у Word списки «List Number» продовжують лічильник між розділами
            for n, item in enumerate(items, 1):
                par = self._rich(self.doc.add_paragraph(), f"{n}) {item}")
                pf = par.paragraph_format
                pf.left_indent, pf.first_line_indent = Cm(1.25), Cm(-0.6)
            return
        for item in items:
            par = self.doc.add_paragraph(style="List Bullet")
            par.paragraph_format.first_line_indent = Cm(0)
            self._rich(par, item)

    def qa(self, n: int, question: str, answer: list[str] | str):
        par = self.p(f"**{n}. {question}**", indent=False)
        par.paragraph_format.space_before = Pt(8)
        par.paragraph_format.keep_with_next = True
        for a in [answer] if isinstance(answer, str) else answer:
            if a.startswith("- "):
                self.bullets([a[2:]])
            else:
                self.p(a)

    # ── таблиці ──
    def table(self, header: list[str], rows: list[list], caption: str | None = None, widths: list[float] | None = None,
              mono: tuple[int, ...] = (), size: float = 11):
        if caption:
            self.tables += 1
            cap = self.p(f"Таблиця {self.tables} – {caption}", indent=False, size=12)
            cap.paragraph_format.keep_with_next = True
        t = self.doc.add_table(rows=1, cols=len(header))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, h in enumerate(header):
            cell = t.rows[0].cells[i]
            par = cell.paragraphs[0]
            par.paragraph_format.first_line_indent = Cm(0)
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = par.add_run(str(h))
            run.bold = True
            run.font.size = Pt(size)
        for row in rows:
            cells = t.add_row().cells
            for i, value in enumerate(row):
                par = cells[i].paragraphs[0]
                par.paragraph_format.first_line_indent = Cm(0)
                par.paragraph_format.line_spacing = 1.0
                par.alignment = WD_ALIGN_PARAGRAPH.LEFT
                if i in mono:
                    run = par.add_run(str(value))
                    run.font.name = MONO_FONT
                    run.font.size = Pt(size - 2)
                else:
                    self._rich(par, str(value), size)
        if widths:
            self._fix_widths(t, widths)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(0)
        return t

    @staticmethod
    def _fix_widths(t, widths: list[float]) -> None:
        """Фіксовані ширини колонок, масштабовані до ширини тексту (інакше Word їх перераховує сам)."""
        scale = min(1.0, TEXT_WIDTH_CM / sum(widths))
        widths = [w * scale for w in widths]
        t.autofit = False
        layout = OxmlElement("w:tblLayout")
        layout.set(qn("w:type"), "fixed")
        t._tbl.tblPr.append(layout)
        for col, w in zip(t._tbl.tblGrid.findall(qn("w:gridCol")), widths):
            col.set(qn("w:w"), str(int(Cm(w).twips)))
        for row in t.rows:
            for cell, w in zip(row.cells, widths):
                cell.width = Cm(w)

    # ── код ──
    def code(self, text: str, caption: str | None = None, size: float = 8.5):
        if caption:
            cap = self.p(caption, indent=False, size=12)
            cap.paragraph_format.keep_with_next = True
        t = self.doc.add_table(rows=1, cols=1)
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        self._fix_widths(t, [TEXT_WIDTH_CM])
        cell = t.rows[0].cells[0]
        par = cell.paragraphs[0]
        par.paragraph_format.first_line_indent = Cm(0)
        par.paragraph_format.line_spacing = 1.0
        par.paragraph_format.space_after = Pt(0)
        par.alignment = WD_ALIGN_PARAGRAPH.LEFT
        lines = text.rstrip("\n").split("\n")
        for i, line in enumerate(lines):
            run = par.add_run(line)
            run.font.name = MONO_FONT
            run.font.size = Pt(size)
            run._r.rPr.rFonts.set(qn("w:eastAsia"), MONO_FONT)
            if i < len(lines) - 1:
                run.add_break()
        self.doc.add_paragraph().paragraph_format.space_after = Pt(0)

    # ── рисунки ──
    def image(self, path: Path | str, caption: str, width_cm: float = 16.5):
        par = self.doc.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.first_line_indent = Cm(0)
        par.paragraph_format.keep_with_next = True
        par.add_run().add_picture(str(path), width=Cm(width_cm))
        self.figures += 1
        self.p(f"Рисунок {self.figures} – {caption}", align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, size=12)

    # ── службове ──
    def new_page(self):
        """Наступний заголовок розділу почнеться з нової сторінки."""
        self._break_before_next = True

    def page_break(self):
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def toc(self):
        par = self.p("ЗМІСТ", align=WD_ALIGN_PARAGRAPH.CENTER, indent=False)
        par.runs[0].bold = True
        _field(self.doc.add_paragraph(), 'TOC \\o "1-2" \\h \\z \\u',
               "Натисніть F9 (або «Оновити поле»), щоб сформувати зміст.")
        self._break_before_next = True

    def title_page(self, work: str, topic: str, discipline: str = "Сучасні блокчейн-технології",
                   action: str = "виконання"):
        """Титульна сторінка з шаблону кафедри (lab_1.docx): тема, дисципліна та викладач підставляються.

        work — напр. «лабораторної роботи №1» або «проєкту»; action — «виконання», «проходження» тощо.
        """
        paras = Document(TEMPLATE).paragraphs
        last = next(i for i, par in enumerate(paras) if par.text.strip() == "2026")

        def set_text(par, text):
            par.runs[0].text = text
            for run in par.runs[1:]:
                run.text = ""

        anchor = self.doc.element.body[0]
        for par in paras[:last + 1]:
            text = par.text.strip()
            if text.startswith("про виконання"):
                set_text(par, f"про {action} {work}")
            elif text.startswith("«"):
                set_text(par, f"«{topic}»")
            elif text.startswith(("“", '"')):
                set_text(par, f"“{discipline}”")
            elif text.startswith("Перевірив"):
                set_text(par, "Перевірив:")
                par.paragraph_format.first_line_indent = Cm(10)  # у шаблоні позиціювання пробілами
            pf = par.paragraph_format
            if pf.first_line_indent is not None and pf.first_line_indent > Cm(5):
                # блок «Виконав / Перевірив»: колонка з лівим відступом, щоб перенесення не з'їжджали до поля
                pf.left_indent, pf.first_line_indent = Cm(9.5), Cm(0)
                pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
            if pf.first_line_indent is None:  # не успадковувати абзацний відступ основного тексту
                pf.first_line_indent = Cm(0)
            if pf.space_after is None:
                pf.space_after = Pt(0)
            anchor.addprevious(copy.deepcopy(par._p))
            if text.startswith("Перевірив"):
                set_text(par, TEACHER)
                anchor.addprevious(copy.deepcopy(par._p))
        self.page_break()

    def save(self, path: Path):
        self.doc.save(path)
        return path
