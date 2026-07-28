"""Render docs/paper/manuscript.md to a readable PDF via Playwright."""

from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

PAPER_DIR = Path(__file__).resolve().parent
MD_PATH = PAPER_DIR / "manuscript.md"
PDF_PATH = PAPER_DIR / "manuscript.pdf"
HTML_PATH = PAPER_DIR / "manuscript.html"

CSS = """
@page { margin: 0.7in; }
body {
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  font-size: 10.2pt;
  line-height: 1.48;
  color: #1a1a1a;
  max-width: 7.3in;
  margin: 0 auto;
}
h1 {
  font-size: 17pt;
  line-height: 1.25;
  margin: 0 0 0.35em;
  font-weight: 700;
}
h2 {
  font-size: 13pt;
  margin: 1.35em 0 0.5em;
  padding-bottom: 0.18em;
  border-bottom: 1px solid #bbb;
  font-weight: 700;
  page-break-after: avoid;
}
h3 {
  font-size: 11pt;
  margin: 1.05em 0 0.35em;
  font-weight: 700;
  color: #222;
  page-break-after: avoid;
}
p { margin: 0.5em 0; }
ul, ol {
  margin: 0.4em 0 0.65em 1.35em;
  padding-left: 0.35em;
}
ol { list-style-type: decimal; }
ul { list-style-type: disc; }
li { margin: 0.3em 0; }
table {
  border-collapse: collapse;
  width: 100%;
  margin: 0.35em 0 0.95em;
  font-size: 9.1pt;
}
th, td {
  border: 1px solid #999;
  padding: 0.32em 0.45em;
  text-align: left;
  vertical-align: top;
}
th { background: #efefef; font-weight: 700; }
code {
  font-family: Consolas, "Courier New", monospace;
  font-size: 8.7pt;
  background: #f4f4f4;
  padding: 0.04em 0.22em;
  border-radius: 2px;
}
hr { border: none; border-top: 1px solid #ccc; margin: 1.15em 0; }
strong { font-weight: 700; }
em { font-style: italic; }
.equation {
  display: block;
  text-align: center;
  margin: 0.8em 0;
  padding: 0.5em 0.7em;
  font-family: "Cambria Math", "Times New Roman", Times, serif;
  font-size: 10.8pt;
  background: #f8f8f8;
  border: 1px solid #ddd;
  border-radius: 3px;
}
sub { font-size: 0.75em; }
figure {
  margin: 1em 0 1.15em;
  page-break-inside: avoid;
  text-align: center;
}
figure img {
  max-width: 100%;
  height: auto;
  border: 1px solid #ddd;
}
figcaption {
  margin-top: 0.4em;
  font-size: 9pt;
  line-height: 1.35;
  text-align: left;
  color: #222;
}
p.table-caption {
  margin: 0.85em 0 0.25em;
  font-size: 9.2pt;
  font-weight: 700;
}
"""


def embed_images(html: str) -> str:
    def repl(match: re.Match[str]) -> str:
        src = match.group(1)
        path = (PAPER_DIR / src).resolve()
        if not path.exists():
            return match.group(0)
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        return f'src="data:{mime};base64,{b64}"'

    return re.sub(r'src="([^"]+)"', repl, html)


def promote_table_captions(md_text: str) -> str:
    """Turn '**Table N.** ...' paragraphs into styled captions before tables."""
    return re.sub(
        r"(?m)^\*\*(Table [^.]+\.)\*\*\s*(.+)\s*$",
        r'<p class="table-caption">\1 \2</p>',
        md_text,
    )


def build_html(md_text: str) -> str:
    md_text = promote_table_captions(md_text)
    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "sane_lists", "md_in_html"],
        output_format="html5",
    )
    body = embed_images(body)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Leakage-Safe Pregame Pitcher Strikeout Projection</title>
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""


def main() -> None:
    md = MD_PATH.read_text(encoding="utf-8")
    page_html = build_html(md)
    HTML_PATH.write_text(page_html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(page_html, wait_until="load")
        page.pdf(
            path=str(PDF_PATH),
            format="Letter",
            print_background=True,
            margin={
                "top": "0.65in",
                "bottom": "0.65in",
                "left": "0.65in",
                "right": "0.65in",
            },
        )
        browser.close()

    print(f"Wrote {HTML_PATH}")
    print(f"Wrote {PDF_PATH}")
    print(f"PDF size: {PDF_PATH.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
