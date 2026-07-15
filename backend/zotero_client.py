"""Thin wrapper around pyzotero for the two things this app needs:
listing a user's library so they can pick a source, and pulling the best
attached PDF (or, failing that, the abstract) for a chosen item.

The Zotero API key/library id are supplied per-request from the frontend and
are never written to disk - they only live for the duration of one request.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pyzotero import zotero

from .citation import Author, Citation, year_from_date_string


class ZoteroError(RuntimeError):
    pass


def get_client(api_key: str, library_id: str, library_type: str = "user") -> zotero.Zotero:
    if not api_key or not library_id:
        raise ZoteroError("Zotero API key and library ID are required.")
    try:
        return zotero.Zotero(library_id, library_type, api_key)
    except Exception as exc:  # pragma: no cover - defensive
        raise ZoteroError(f"Could not create Zotero client: {exc}") from exc


def list_library_items(api_key: str, library_id: str, library_type: str, query: Optional[str] = None, limit: int = 50) -> list[dict]:
    zot = get_client(api_key, library_id, library_type)
    try:
        if query:
            items = zot.items(q=query, limit=limit, itemType="-attachment || note")
        else:
            items = zot.top(limit=limit)
    except Exception as exc:
        raise ZoteroError(f"Zotero request failed: {exc}") from exc

    out = []
    for it in items:
        data = it.get("data", {})
        item_type = data.get("itemType")
        if item_type in ("attachment", "note", "annotation"):
            continue
        creators = data.get("creators", [])
        author_names = []
        for c in creators:
            if "lastName" in c:
                name = c["lastName"]
                if c.get("firstName"):
                    name = f"{c['firstName']} {name}"
                author_names.append(name)
            elif c.get("name"):
                author_names.append(c["name"])
        out.append({
            "key": data.get("key"),
            "title": data.get("title") or "(untitled)",
            "authors": author_names,
            "date": data.get("date"),
            "itemType": item_type,
            "publicationTitle": data.get("publicationTitle") or data.get("bookTitle") or data.get("publisher"),
            "hasAttachment": True,
        })
    return out


def build_citation_from_zotero(data: dict) -> Citation:
    authors = []
    for c in data.get("creators", []):
        if "lastName" in c:
            authors.append(Author(last=c["lastName"], first=c.get("firstName", "")))
        elif c.get("name"):
            authors.append(Author(last=c["name"]))
    return Citation(
        title=data.get("title") or "(untitled)",
        authors=authors,
        year=year_from_date_string(data.get("date")),
        container_title=data.get("publicationTitle") or data.get("bookTitle") or data.get("publisher"),
        url=data.get("url"),
        source_kind="zotero",
        zotero_item_key=data.get("key"),
    )


@dataclass
class ZoteroAttachment:
    key: str
    filename: str
    content_type: str


def find_pdf_attachment(api_key: str, library_id: str, library_type: str, item_key: str) -> Optional[ZoteroAttachment]:
    zot = get_client(api_key, library_id, library_type)
    try:
        children = zot.children(item_key)
    except Exception as exc:
        raise ZoteroError(f"Could not list attachments: {exc}") from exc
    for child in children:
        data = child.get("data", {})
        if data.get("itemType") == "attachment" and data.get("contentType") == "application/pdf":
            return ZoteroAttachment(key=data["key"], filename=data.get("filename", "document.pdf"), content_type="application/pdf")
    return None


def download_attachment(api_key: str, library_id: str, library_type: str, attachment_key: str) -> bytes:
    zot = get_client(api_key, library_id, library_type)
    try:
        return zot.file(attachment_key)
    except Exception as exc:
        raise ZoteroError(f"Could not download attachment: {exc}") from exc


def get_item(api_key: str, library_id: str, library_type: str, item_key: str) -> dict:
    zot = get_client(api_key, library_id, library_type)
    try:
        item = zot.item(item_key)
    except Exception as exc:
        raise ZoteroError(f"Could not fetch item {item_key}: {exc}") from exc
    return item.get("data", {})
