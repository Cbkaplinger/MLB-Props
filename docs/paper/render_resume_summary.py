"""Render resume-summary.md to a one-page PDF."""

from __future__ import annotations

import importlib.util
from pathlib import Path

PAPER = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("render_pdf", PAPER / "render_pdf.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

from playwright.sync_api import sync_playwright

MD_PATH = PAPER / "resume-summary.md"
PDF_PATH = PAPER / "resume-summary.pdf"
HTML_PATH = PAPER / "resume-summary.html"


def main() -> None:
    md = MD_PATH.read_text(encoding="utf-8")
    html = mod.build_html(md)
    # Slightly denser one-pager styling
    html = html.replace(
        "font-size: 10.2pt;",
        "font-size: 9.8pt;",
    ).replace(
        "max-width: 7.3in;",
        "max-width: 7.0in;",
    )
    HTML_PATH.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html, wait_until="load")
        page.pdf(
            path=str(PDF_PATH),
            format="Letter",
            print_background=True,
            margin={
                "top": "0.55in",
                "bottom": "0.55in",
                "left": "0.6in",
                "right": "0.6in",
            },
        )
        browser.close()
    print(f"Wrote {PDF_PATH} ({PDF_PATH.stat().st_size/1024:.1f} KB)")


if __name__ == "__main__":
    main()
