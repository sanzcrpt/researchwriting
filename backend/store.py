"""In-memory store for ingested sources.

This is a single-process, non-persistent app: sources live only for the
life of the server process. That's a deliberate simplicity trade-off for a
personal research tool - see README for notes on what you'd need to change
to make this multi-user / durable (a real DB instead of a dict).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .citation import Citation


@dataclass
class SourceRecord:
    id: str
    text: str
    citation: Citation
    page_count: Optional[int] = None
    created_at: float = field(default_factory=time.time)
    zotero_context: Optional[dict] = None  # api_key/library_id/library_type/item_key, if from Zotero


class SourceStore:
    def __init__(self, max_items: int = 200):
        self._items: dict[str, SourceRecord] = {}
        self._max_items = max_items

    def add(self, text: str, citation: Citation, page_count: Optional[int] = None, zotero_context: Optional[dict] = None) -> SourceRecord:
        if len(self._items) >= self._max_items:
            oldest_key = min(self._items, key=lambda k: self._items[k].created_at)
            del self._items[oldest_key]
        record = SourceRecord(id=str(uuid.uuid4()), text=text, citation=citation, page_count=page_count, zotero_context=zotero_context)
        self._items[record.id] = record
        return record

    def get(self, source_id: str) -> Optional[SourceRecord]:
        return self._items.get(source_id)


store = SourceStore()
