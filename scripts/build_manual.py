"""Gera o PDF do manual a partir do fonte em Markdown (``data/manuals/source``).

O manual usado na demonstracao foi escrito para este projeto (produto e fabricante ficticios), para
nao redistribuir material protegido por direitos autorais de um fabricante real. O PDF fica
versionado em ``data/manuals``; este script existe para que ele seja reproduzivel e editavel.

O pipeline de RAG nao depende deste script: qualquer PDF colocado em ``data/manuals`` e indexado.

Uso:  python scripts/build_manual.py [fonte.md] [saida.pdf]
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data" / "manuals" / "source" / "roteador_tucano_ax1800.md"
DEFAULT_OUTPUT = ROOT / "data" / "manuals" / "roteador_tucano_ax1800.pdf"

HEADER_TEXT = "Manual do Usuário - Roteador Wi-Fi 6 Tucano AX1800"
_NUMBERED = re.compile(r"^(\d+)\.\s+(.*)$")


class ManualPDF(FPDF):
    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(110, 110, 110)
        self.cell(0, 6, HEADER_TEXT, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
        self.ln(3)
        self.set_text_color(0, 0, 0)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(110, 110, 110)
        self.cell(0, 6, f"Página {self.page_no()}", align="C")
        self.set_text_color(0, 0, 0)


def _ensure_room(pdf: FPDF, height: float) -> None:
    """Evita titulo orfao no fim da pagina."""
    if pdf.get_y() + height > pdf.h - pdf.b_margin:
        pdf.add_page()


def build(source: Path, output: Path) -> Path:
    pdf = ManualPDF(format="A4")
    pdf.set_margins(22, 18, 22)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_title("Manual do Usuário - Roteador Wi-Fi 6 Tucano AX1800")
    pdf.set_author("Tucano Redes (fabricante fictício)")
    pdf.set_subject("Manual de instalação, configuração e solução de problemas")
    # Data fixa: o PDF gerado e identico byte a byte a cada execucao.
    pdf.set_creation_date(datetime(2026, 11, 1, tzinfo=timezone.utc))
    pdf.add_page()
    width = pdf.w - pdf.l_margin - pdf.r_margin

    for raw_line in source.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            pdf.ln(2)
            continue
        numbered = _NUMBERED.match(line)
        if line.startswith("# "):
            pdf.ln(40)
            pdf.set_font("Helvetica", "B", 22)
            pdf.multi_cell(width, 11, line[2:], align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(8)
        elif line.startswith("## "):
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 16)
            pdf.multi_cell(width, 9, line[3:], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2)
        elif line.startswith("### "):
            _ensure_room(pdf, 30)
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 12)
            pdf.multi_cell(width, 7, line[4:], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
        elif line.startswith("- ") or numbered:
            marker, text = ("-", line[2:]) if line.startswith("- ") else (f"{numbered.group(1)}.", numbered.group(2))
            pdf.set_font("Helvetica", "", 10.5)
            pdf.set_x(pdf.l_margin + 3)
            pdf.cell(7, 5.6, marker)
            pdf.multi_cell(width - 10, 5.6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.set_font("Helvetica", "", 10.5)
            pdf.multi_cell(width, 5.6, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    output.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output))
    return output


def main(argv: list[str]) -> int:
    source = Path(argv[1]) if len(argv) > 1 else DEFAULT_SOURCE
    output = Path(argv[2]) if len(argv) > 2 else DEFAULT_OUTPUT
    path = build(source, output)
    print(f"PDF gerado: {path} ({path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
