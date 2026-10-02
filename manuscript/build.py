"""Build the submission files (Word and PDF) from the Markdown sources.

    python manuscript/build.py

Needs pandoc (with citeproc), python-docx, and xelatex with the TeX Gyre Termes font (for the
PDF versions). Tables are generated from results/ by make_tables.py, so rerun
scripts/run_all.py, scripts/descriptives.py and scripts/extra_checks.py first if results change.
Outputs go to manuscript/out/.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.shared import Pt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "out"
TAB = HERE / "tables"


def reference_docx() -> Path:
    """A Word style file: Times New Roman 12 pt, double-spaced body text, 1-inch margins."""
    path = HERE / "reference.docx"
    subprocess.run(["pandoc", "-o", str(path), "--print-default-data-file", "reference.docx"], check=True)
    doc = Document(path)
    for style in doc.styles:
        try:
            font = style.font
        except AttributeError:
            continue
        if font is None:
            continue
        font.name = "Times New Roman"
        try:
            rf = style.element.rPr.rFonts
            W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            for att in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
                rf.attrib.pop(W + att, None)
            for att in ("ascii", "hAnsi", "eastAsia", "cs"):
                rf.set(W + att, "Times New Roman")
        except AttributeError:
            pass
        if hasattr(font, "color") and font.color is not None:
            font.color.rgb = None
    for name in ["Normal", "Body Text", "First Paragraph", "Compact", "Bibliography"]:
        if name in [s.name for s in doc.styles]:
            st = doc.styles[name]
            st.font.size = Pt(12)
            pf = st.paragraph_format
            if name == "Compact":            # table cells and tight lists
                st.font.size = Pt(10)
                pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
                pf.space_before = pf.space_after = Pt(1)
                continue
            pf.line_spacing_rule = WD_LINE_SPACING.DOUBLE
    for name, size in [("Title", 16), ("Heading 1", 13), ("Heading 2", 12), ("Heading 3", 12)]:
        try:
            st = doc.styles[name]
        except KeyError:
            continue
        st.font.size = Pt(size)
        st.font.bold = True
    for name in ["Table", "Caption", "Image Caption", "Table Caption"]:
        if name in [s.name for s in doc.styles]:
            doc.styles[name].font.size = Pt(10)
    for section in doc.sections:
        section.left_margin = section.right_margin = section.top_margin = section.bottom_margin = Pt(72)
    doc.save(path)
    return path


def fill(src: str, extra: dict | None = None) -> str:
    text = (HERE / src).read_text()
    for f in TAB.glob("*.md"):
        key = f.stem.split("_")[0].upper()
        text = text.replace("{{" + key + "}}", f.read_text().strip())
    for k, v in (extra or {}).items():
        text = text.replace("{{" + k + "}}", v)
    left = re.findall(r"\{\{[A-Z0-9_]+\}\}", text)
    if left:
        raise ValueError(f"unfilled placeholders in {src}: {left}")
    return text


def pandoc(md: str, stem: str, ref: Path, number: bool, citeproc: bool):
    tmp = HERE / f"_{stem}.md"
    tmp.write_text(md)
    args = ["pandoc", str(tmp), "-o", str(OUT / f"{stem}.docx"), "--reference-doc", str(ref),
            "--resource-path", str(HERE)]
    if citeproc:
        args += ["--citeproc"]
    if number:
        args += ["--number-sections"]
    subprocess.run(args, check=True, cwd=HERE)
    tmp.unlink()


def to_pdf(stem: str, md: str, number: bool, citeproc: bool):
    """PDF through LaTeX (xelatex), so equations and tables render properly."""
    tmp = HERE / f"_{stem}_pdf.md"
    tmp.write_text(md)
    args = ["pandoc", str(tmp), "-o", str(OUT / f"{stem}.pdf"), "--pdf-engine=xelatex",
            "--template", str(HERE / "template.latex"), "--resource-path", str(HERE),
            "-V", "mainfont=TeX Gyre Termes", "-V", "fontsize=11pt", "-V", "geometry:margin=2.5cm",
            "-V", "linestretch=1.5", "-V", "colorlinks=true", "-H", str(HERE / "header.tex")]
    if citeproc:
        args += ["--citeproc"]
    if number:
        args += ["--number-sections"]
    subprocess.run(args, check=True, cwd=HERE)
    tmp.unlink()


def word_count(stem: str) -> int:
    txt = subprocess.run(["pandoc", str(OUT / f"{stem}.docx"), "-t", "plain"], check=True,
                         capture_output=True, text=True).stdout
    return len(txt.split())


def main():
    subprocess.run(["python3", str(HERE / "make_tables.py")], check=True)
    OUT.mkdir(exist_ok=True)
    ref = reference_docx()
    act = pd.read_csv(ROOT / "results" / "option_activity_by_year.csv")
    n = act[act["index"] == "nifty50"].set_index("year")["share_0dte_of_year"]
    extra = {"ACT_N24": f"{100 * n.loc[2024]:.0f}%",
             "ACT_N_EARLY": f"{100 * n.loc[2014:2018].min():.0f}–{100 * n.loc[2014:2018].max():.0f}%"}
    ms = fill("manuscript_src.md", extra)
    pandoc(ms, "manuscript", ref, number=True, citeproc=True)
    to_pdf("manuscript", ms, number=True, citeproc=True)
    words = word_count("manuscript")
    docs = {"supplementary_material": fill("supplement_src.md"),
            "title_page": fill("title_page_src.md", {"WORDS": f"{words:,}"}),
            "cover_letter": fill("cover_letter_src.md"),
            "highlights": fill("highlights_src.md")}
    for stem, md in docs.items():
        cp = stem == "supplementary_material"
        pandoc(md, stem, ref, number=False, citeproc=cp)
        to_pdf(stem, md, number=False, citeproc=cp)
    print(f"manuscript words (incl. tables, captions, references): {words:,}")
    for f in sorted(OUT.iterdir()):
        print(f.name, f.stat().st_size)


if __name__ == "__main__":
    main()
