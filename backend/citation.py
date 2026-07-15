"""Lightweight citation model + APA-ish reference formatting.

This is intentionally not a full CSL/citeproc implementation - it produces a
reasonable APA 7-style reference string from whatever metadata is available
(Zotero item data, PDF metadata, URL meta tags, or manual entry) so every
generated note has something citable attached to it. Users should still spot
check the formatting before it goes into a final bibliography.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Author:
    last: str
    first: str = ""

    def apa(self) -> str:
        if not self.first:
            return self.last
        initials = "".join(f"{part[0]}." for part in re.split(r"[\s\-]+", self.first) if part)
        return f"{self.last}, {initials}"


@dataclass
class Citation:
    title: str
    authors: list[Author] = field(default_factory=list)
    year: Optional[str] = None
    container_title: Optional[str] = None  # journal, book title, publisher, site name
    url: Optional[str] = None
    source_kind: str = "document"  # zotero | pdf | url
    zotero_item_key: Optional[str] = None

    def short_author_year(self) -> str:
        if not self.authors:
            base = self.title[:40] + ("…" if len(self.title) > 40 else "")
            return f'"{base}"{f", {self.year}" if self.year else ""}'
        if len(self.authors) == 1:
            names = self.authors[0].last
        elif len(self.authors) == 2:
            names = f"{self.authors[0].last} & {self.authors[1].last}"
        else:
            names = f"{self.authors[0].last} et al."
        return f"{names}{f', {self.year}' if self.year else ''}"

    def apa_reference(self) -> str:
        if self.authors:
            author_str = "; ".join(a.apa() for a in self.authors[:20])
        else:
            author_str = ""
        year_str = f"({self.year})" if self.year else "(n.d.)"
        head = f"{author_str} {year_str}" if author_str else year_str
        title = self.title.strip().rstrip(".")
        body = f"{title}."
        if self.container_title:
            body += f" {self.container_title}."
        if self.url:
            body += f" {self.url}"
        ref = f"{head}. {body}" if head else body
        return re.sub(r"\s+", " ", ref).strip()

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "authors": [{"last": a.last, "first": a.first} for a in self.authors],
            "year": self.year,
            "container_title": self.container_title,
            "url": self.url,
            "source_kind": self.source_kind,
            "zotero_item_key": self.zotero_item_key,
            "short": self.short_author_year(),
            "apa": self.apa_reference(),
        }


def year_from_date_string(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    match = re.search(r"(1[5-9]\d{2}|20\d{2})", date_str)
    return match.group(1) if match else None


def parse_manual_author(name: str) -> Author:
    name = name.strip()
    if "," in name:
        last, _, first = name.partition(",")
        return Author(last=last.strip(), first=first.strip())
    parts = name.split()
    if len(parts) == 1:
        return Author(last=parts[0])
    return Author(last=parts[-1], first=" ".join(parts[:-1]))
