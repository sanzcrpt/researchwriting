"""Text extraction from PDFs and web pages, with light metadata sniffing so
we can build a citation even when the user doesn't type one in by hand.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .citation import Author, Citation, parse_manual_author, year_from_date_string

USER_AGENT = "ThesisResearchAssistant/1.0 (+academic research tool)"
REQUEST_TIMEOUT = 20


@dataclass
class ExtractedSource:
    text: str
    citation: Citation
    page_count: Optional[int] = None


def extract_pdf_text(pdf_bytes: bytes) -> tuple[str, int]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        page_text = page_text.strip()
        if page_text:
            parts.append(f"\n\n[PAGE {i}]\n{page_text}")
    text = "".join(parts).strip()
    return text, len(reader.pages)


def sniff_pdf_metadata(pdf_bytes: bytes) -> dict:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        meta = reader.metadata or {}
        return {
            "title": (meta.title or "").strip() if meta.title else None,
            "author": (meta.author or "").strip() if meta.author else None,
        }
    except Exception:
        return {}


def build_pdf_citation(pdf_bytes: bytes, filename: str, manual: Optional[dict] = None) -> Citation:
    manual = manual or {}
    sniffed = sniff_pdf_metadata(pdf_bytes)

    title = manual.get("title") or sniffed.get("title") or filename.rsplit(".", 1)[0]
    authors_raw = manual.get("authors") or sniffed.get("author") or ""
    authors = [parse_manual_author(a) for a in re.split(r";|,\s*and\s+|\band\b", authors_raw) if a.strip()] if authors_raw else []
    year = manual.get("year") or None

    return Citation(
        title=title,
        authors=authors,
        year=year,
        container_title=manual.get("container_title"),
        url=manual.get("url"),
        source_kind="pdf",
    )


def fetch_url_text(url: str) -> tuple[str, dict]:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    meta = _extract_meta(soup, url)

    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"]):
        tag.decompose()

    main = soup.find("article") or soup.find("main") or soup.body or soup
    paragraphs = [p.get_text(" ", strip=True) for p in main.find_all(["p", "h1", "h2", "h3", "li", "blockquote"])]
    paragraphs = [p for p in paragraphs if len(p) > 20]
    text = "\n\n".join(paragraphs)
    if not text:
        text = main.get_text(" ", strip=True)
    return text, meta


def _extract_meta(soup: BeautifulSoup, url: str) -> dict:
    def og(prop):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        return tag.get("content") if tag else None

    title = og("og:title") or (soup.title.string.strip() if soup.title and soup.title.string else None)
    site_name = og("og:site_name")
    author = og("article:author") or og("author")
    published = og("article:published_time") or og("date")

    return {
        "title": title,
        "site_name": site_name,
        "author": author,
        "published": published,
        "url": url,
    }


def build_url_citation(url: str, meta: dict, manual: Optional[dict] = None) -> Citation:
    manual = manual or {}
    title = manual.get("title") or meta.get("title") or url
    authors_raw = manual.get("authors") or meta.get("author") or ""
    authors = [parse_manual_author(a) for a in re.split(r";|,\s*and\s+|\band\b", authors_raw) if a.strip()] if authors_raw else []
    year = manual.get("year") or year_from_date_string(meta.get("published"))

    return Citation(
        title=title,
        authors=authors,
        year=year,
        container_title=manual.get("container_title") or meta.get("site_name"),
        url=url,
        source_kind="url",
    )
