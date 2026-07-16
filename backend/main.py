from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analysis, extraction, zotero_client
from .citation import Citation
from .md import markdown_to_html
from .store import store
from .zotero_client import ZoteroError

APP_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = APP_DIR.parent / "frontend"

app = FastAPI(title="Thesis Research Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- schemas ----------

class ZoteroListRequest(BaseModel):
    api_key: str
    library_id: str
    library_type: str = "user"
    query: Optional[str] = None


class ZoteroIngestRequest(BaseModel):
    api_key: str
    library_id: str
    library_type: str = "user"
    item_key: str


class UrlIngestRequest(BaseModel):
    url: str
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[str] = None
    container_title: Optional[str] = None


class AnalyzeRequest(BaseModel):
    source_id: str
    analysis_types: list[str]
    concept_term: Optional[str] = None
    terms: Optional[list[str]] = None


class SaveToZoteroRequest(BaseModel):
    source_id: str
    analysis_label: str
    markdown: str


# ---------- health ----------

@app.get("/api/health")
def health():
    # Constructing the client never fails, even with zero credentials - the SDK only
    # validates auth on an actual request. Make one real (unbilled) call so this
    # reports what will actually happen when an analysis runs.
    try:
        analysis.get_client().models.retrieve(analysis.MODEL)
        auth_configured = True
        auth_error = None
    except Exception as exc:
        auth_configured = False
        auth_error = str(exc)
    auth_source = "ANTHROPIC_API_KEY" if os.environ.get("ANTHROPIC_API_KEY") else "ant auth login / ANTHROPIC_AUTH_TOKEN"
    return {
        "ok": True,
        "model": analysis.MODEL,
        "auth_configured": auth_configured,
        "auth_source": auth_source,
        "auth_error": auth_error,
    }


@app.get("/api/analysis-types")
def analysis_types():
    return {
        key: {"label": spec["label"], "requires": spec["requires"]}
        for key, spec in analysis.ANALYSIS_TYPES.items()
    }


# ---------- Zotero ----------

@app.post("/api/zotero/items")
def zotero_items(req: ZoteroListRequest):
    try:
        items = zotero_client.list_library_items(req.api_key, req.library_id, req.library_type, req.query)
    except ZoteroError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"items": items}


@app.post("/api/source/zotero")
def source_from_zotero(req: ZoteroIngestRequest):
    try:
        item_data = zotero_client.get_item(req.api_key, req.library_id, req.library_type, req.item_key)
        citation = zotero_client.build_citation_from_zotero(item_data)

        attachment = zotero_client.find_pdf_attachment(req.api_key, req.library_id, req.library_type, req.item_key)
        if attachment:
            pdf_bytes = zotero_client.download_attachment(req.api_key, req.library_id, req.library_type, attachment.key)
            text, page_count = extraction.extract_pdf_text(pdf_bytes)
        else:
            abstract = item_data.get("abstractNote", "")
            if not abstract:
                raise HTTPException(
                    status_code=400,
                    detail="No PDF attachment or abstract found on this Zotero item. Try uploading the PDF directly.",
                )
            text = f"[ABSTRACT ONLY - no PDF attachment found in Zotero]\n\n{abstract}"
            page_count = None
    except ZoteroError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract any text from this source's PDF.")

    record = store.add(
        text=text,
        citation=citation,
        page_count=page_count,
        zotero_context={
            "api_key": req.api_key,
            "library_id": req.library_id,
            "library_type": req.library_type,
            "item_key": req.item_key,
        },
    )
    return _source_response(record)


@app.post("/api/source/pdf")
async def source_from_pdf(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    authors: Optional[str] = Form(None),
    year: Optional[str] = Form(None),
    container_title: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
):
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    try:
        text, page_count = extraction.extract_pdf_text(pdf_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not read PDF: {exc}")
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract any text from this PDF (it may be scanned images without OCR).")

    manual = {"title": title, "authors": authors, "year": year, "container_title": container_title, "url": url}
    citation = extraction.build_pdf_citation(pdf_bytes, file.filename or "document.pdf", manual)

    record = store.add(text=text, citation=citation, page_count=page_count)
    return _source_response(record)


@app.post("/api/source/url")
def source_from_url(req: UrlIngestRequest):
    try:
        text, meta = extraction.fetch_url_text(req.url)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not fetch or parse URL: {exc}")
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract readable text from this page.")

    manual = {"title": req.title, "authors": req.authors, "year": req.year, "container_title": req.container_title}
    citation = extraction.build_url_citation(req.url, meta, manual)

    record = store.add(text=text, citation=citation)
    return _source_response(record)


def _source_response(record):
    return {
        "source_id": record.id,
        "citation": record.citation.to_dict(),
        "page_count": record.page_count,
        "char_count": len(record.text),
        "text_preview": record.text[:800],
        "from_zotero": record.zotero_context is not None,
    }


# ---------- analysis ----------

@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    record = store.get(req.source_id)
    if not record:
        raise HTTPException(status_code=404, detail="Source not found (server may have restarted - re-add the source).")

    if not req.analysis_types:
        raise HTTPException(status_code=400, detail="No analysis types requested.")

    options = {"concept_term": req.concept_term, "terms": req.terms}

    results = {}
    errors = {}
    for a_type in req.analysis_types:
        if a_type not in analysis.ANALYSIS_TYPES:
            errors[a_type] = f"Unknown analysis type: {a_type}"
            continue
        try:
            results[a_type] = analysis.run_analysis(a_type, record.citation, record.text, options)
        except ValueError as exc:
            errors[a_type] = str(exc)
        except Exception as exc:
            errors[a_type] = f"Analysis failed: {exc}"

    return {"results": results, "errors": errors, "citation": record.citation.to_dict()}


@app.post("/api/save-to-zotero")
def save_to_zotero(req: SaveToZoteroRequest):
    record = store.get(req.source_id)
    if not record:
        raise HTTPException(status_code=404, detail="Source not found.")
    if not record.zotero_context:
        raise HTTPException(status_code=400, detail="This source was not loaded from Zotero, so there is no item to attach a note to.")

    ctx = record.zotero_context
    html = f"<h2>{req.analysis_label}</h2>\n" + markdown_to_html(req.markdown)
    try:
        zot = zotero_client.get_client(ctx["api_key"], ctx["library_id"], ctx["library_type"])
        zot.create_items([{"itemType": "note", "note": html}], ctx["item_key"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not save note to Zotero: {exc}")

    return {"ok": True}


# ---------- frontend static files ----------

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))
