"""Minimal Markdown -> HTML conversion, just enough to cover what our Claude
prompts actually produce (headings, bold/italic, bullet lists, tables,
paragraphs). Used when pushing a note back into Zotero, which stores notes
as HTML rather than Markdown.
"""
from __future__ import annotations

import re


def _inline(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", s)
    return s


def markdown_to_html(md: str) -> str:
    lines = md.splitlines()
    html: list[str] = []
    i = 0
    in_list = False

    def close_list():
        nonlocal in_list
        if in_list:
            html.append("</ul>")
            in_list = False

    while i < len(lines):
        line = lines[i].rstrip()

        if not line.strip():
            close_list()
            i += 1
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            close_list()
            level = len(heading_match.group(1))
            html.append(f"<h{level}>{_inline(heading_match.group(2))}</h{level}>")
            i += 1
            continue

        if line.strip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]):
            close_list()
            header_cells = [c.strip() for c in line.strip().strip("|").split("|")]
            html.append("<table><thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in header_cells) + "</tr></thead><tbody>")
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                row_cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                html.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row_cells) + "</tr>")
                i += 1
            html.append("</tbody></table>")
            continue

        bullet_match = re.match(r"^[-*]\s+(.*)", line.strip())
        if bullet_match:
            if not in_list:
                html.append("<ul>")
                in_list = True
            html.append(f"<li>{_inline(bullet_match.group(1))}</li>")
            i += 1
            continue

        close_list()
        html.append(f"<p>{_inline(line)}</p>")
        i += 1

    close_list()
    return "\n".join(html)
