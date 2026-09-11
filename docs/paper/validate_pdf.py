"""Validate manuscript.pdf for publication readiness (layout, not numbers).

Checks: page count/dimensions, blank pages (raster), image presence per
page, figure-caption co-location, text selectability, replacement chars,
figure order. Prints FAIL lines; exit 0 always (report, don't gate).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pymupdf

PAPER_DIR = Path(__file__).resolve().parent
PDF_PATH = PAPER_DIR / "manuscript.pdf"

CAPTION_RE = re.compile(r"Figure (\d+)\.")


def main() -> None:
    doc = pymupdf.open(PDF_PATH)
    print(f"pages={len(doc)} size={doc[0].rect.width}x{doc[0].rect.height}")
    fails: list[str] = []
    full_text: list[str] = []
    for i, page in enumerate(doc):
        text = page.get_text()
        full_text.append(text)
        if "�" in text:
            fails.append(f"p{i + 1}: replacement char present")
        pix = page.get_pixmap(dpi=110)
        import collections
        samples = pix.samples
        total = len(samples) // pix.n
        dark = sum(1 for j in range(0, len(samples), pix.n * 7)
                   if sum(samples[j:j + pix.n]) / pix.n < 235)
        frac = dark / max(total // 7, 1)
        n_images = len(page.get_images(full=True))
        starts = [m.group(1) for m in re.finditer(r"(?m)^Figure (\d+)\.", text)]
        words = len(text.split())
        print(f"p{i + 1}: words={words} images={n_images} ink={frac:.3f} caps={starts}")
        if words < 20 and n_images == 0:
            fails.append(f"p{i + 1}: BLANK (words={words}, images=0)")
        if starts and n_images == 0:
            fails.append(f"p{i + 1}: caption without figure {starts}")
    body = "\n".join(full_text)
    order = [int(m.group(1)) for p in full_text
             for m in re.finditer(r"(?m)^Figure (\d+)\.", p)]
    seen: list[int] = []
    for n in order:
        if n not in seen:
            seen.append(n)
    print(f"caption_order={seen}")
    if seen != sorted(seen):
        fails.append(f"captions out of order: {seen}")
    for n in range(1, 9):
        if n not in seen:
            fails.append(f"Figure {n} caption missing from PDF text")
    if "Figure A1." not in body:
        fails.append("Figure A1 caption missing from PDF text")
    for token in ["2014.", "White", "k_rate", "P(K"]:
        if token not in body:
            fails.append(f"expected token missing: {token}")
    print("FAILURES:" if fails else "ALL CHECKS PASS")
    for f in fails:
        print("FAIL:", f)


if __name__ == "__main__":
    sys.exit(main())
