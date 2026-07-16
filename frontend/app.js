const state = {
  sourceId: null,
  citation: null,
  fromZotero: false,
  results: {},
};

// ---------- tabs ----------
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.remove("hidden");
  });
});

// ---------- persist zotero creds locally (not on server) ----------
["zot-api-key", "zot-library-id", "zot-library-type"].forEach((id) => {
  const el = document.getElementById(id);
  const saved = localStorage.getItem(id);
  if (saved) el.value = saved;
  el.addEventListener("change", () => localStorage.setItem(id, el.value));
});

function setStatus(elId, message, isError) {
  const el = document.getElementById(elId);
  el.textContent = message;
  el.className = isError ? "status-error" : "status-ok";
}

// ---------- Zotero: load items ----------
document.getElementById("zot-load-btn").addEventListener("click", async () => {
  const api_key = document.getElementById("zot-api-key").value.trim();
  const library_id = document.getElementById("zot-library-id").value.trim();
  const library_type = document.getElementById("zot-library-type").value;
  const query = document.getElementById("zot-search").value.trim();

  const listEl = document.getElementById("zot-items");
  listEl.innerHTML = "Loading…";
  try {
    const res = await fetch("/api/zotero/items", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key, library_id, library_type, query: query || null }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to load items");
    listEl.innerHTML = "";
    if (data.items.length === 0) {
      listEl.innerHTML = "<p>No items found.</p>";
      return;
    }
    data.items.forEach((item) => {
      const row = document.createElement("div");
      row.className = "item-row";
      row.innerHTML = `<div class="item-title">${escapeHtml(item.title)}</div>
        <div class="item-meta">${escapeHtml((item.authors || []).join(", "))} ${item.date ? "· " + escapeHtml(item.date) : ""} ${item.publicationTitle ? "· " + escapeHtml(item.publicationTitle) : ""}</div>`;
      row.addEventListener("click", () => ingestZoteroItem(api_key, library_id, library_type, item.key));
      listEl.appendChild(row);
    });
  } catch (err) {
    listEl.innerHTML = "";
    setStatus("source-status", err.message, true);
  }
});

async function ingestZoteroItem(api_key, library_id, library_type, item_key) {
  setStatus("source-status", "Fetching item and extracting text…", false);
  try {
    const res = await fetch("/api/source/zotero", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key, library_id, library_type, item_key }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to ingest item");
    onSourceIngested(data);
  } catch (err) {
    setStatus("source-status", err.message, true);
  }
}

// ---------- Upload PDF ----------
document.getElementById("upload-btn").addEventListener("click", async () => {
  const fileInput = document.getElementById("upload-file");
  if (!fileInput.files.length) {
    setStatus("source-status", "Choose a PDF file first.", true);
    return;
  }
  const form = new FormData();
  form.append("file", fileInput.files[0]);
  form.append("title", document.getElementById("upload-title").value);
  form.append("authors", document.getElementById("upload-authors").value);
  form.append("year", document.getElementById("upload-year").value);
  form.append("container_title", document.getElementById("upload-container").value);

  setStatus("source-status", "Uploading and extracting text…", false);
  try {
    const res = await fetch("/api/source/pdf", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to ingest PDF");
    onSourceIngested(data);
  } catch (err) {
    setStatus("source-status", err.message, true);
  }
});

// ---------- Ingest link ----------
document.getElementById("link-btn").addEventListener("click", async () => {
  const url = document.getElementById("link-url").value.trim();
  if (!url) {
    setStatus("source-status", "Enter a URL first.", true);
    return;
  }
  const body = {
    url,
    title: document.getElementById("link-title").value || null,
    authors: document.getElementById("link-authors").value || null,
    year: document.getElementById("link-year").value || null,
    container_title: document.getElementById("link-container").value || null,
  };
  setStatus("source-status", "Fetching and parsing page…", false);
  try {
    const res = await fetch("/api/source/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to ingest URL");
    onSourceIngested(data);
  } catch (err) {
    setStatus("source-status", err.message, true);
  }
});

function onSourceIngested(data) {
  state.sourceId = data.source_id;
  state.citation = data.citation;
  state.fromZotero = data.from_zotero;
  setStatus("source-status", "Source loaded.", false);

  document.getElementById("step-source-preview").classList.remove("hidden");
  document.getElementById("source-preview").innerHTML = `
    <div class="citation-line">${escapeHtml(data.citation.apa)}</div>
    <div>${data.page_count ? data.page_count + " pages · " : ""}${data.char_count.toLocaleString()} characters extracted</div>
    <div style="margin-top:0.5rem; font-style:italic;">${escapeHtml(data.text_preview)}…</div>
  `;

  document.getElementById("step-analyze").classList.remove("hidden");
  document.getElementById("step-results").classList.add("hidden");
  document.getElementById("results").innerHTML = "";
  state.results = {};
  loadAnalysisTypes();
}

// ---------- analysis type checkboxes ----------
let analysisTypesLoaded = false;
async function loadAnalysisTypes() {
  if (analysisTypesLoaded) return;
  const res = await fetch("/api/analysis-types");
  const types = await res.json();
  const grid = document.getElementById("analysis-checkboxes");
  grid.innerHTML = "";
  Object.entries(types).forEach(([key, spec]) => {
    const label = document.createElement("label");
    label.innerHTML = `<input type="checkbox" value="${key}" ${key !== "term_comparison" ? "checked" : ""}/> ${escapeHtml(spec.label)}`;
    grid.appendChild(label);
  });
  analysisTypesLoaded = true;
}

// ---------- run analysis ----------
document.getElementById("analyze-btn").addEventListener("click", async () => {
  if (!state.sourceId) return;
  const checked = Array.from(document.querySelectorAll("#analysis-checkboxes input:checked")).map((c) => c.value);
  if (checked.length === 0) {
    setStatus("analyze-status", "Select at least one analysis type.", true);
    return;
  }
  const concept_term = document.getElementById("concept-term").value.trim() || null;
  const termsRaw = document.getElementById("compare-terms").value.trim();
  const terms = termsRaw ? termsRaw.split(",").map((t) => t.trim()).filter(Boolean) : null;

  // Both fields are optional — leave blank and Claude picks the term(s) itself.
  // Only block the one genuinely ambiguous case: a single term with nothing to compare it to.
  if (checked.includes("term_comparison") && terms && terms.length === 1) {
    setStatus("analyze-status", "Enter 2+ comma-separated terms to compare, or leave the field blank to let Claude choose.", true);
    return;
  }

  const btn = document.getElementById("analyze-btn");
  btn.disabled = true;
  setStatus("analyze-status", "Running analysis with Claude — this can take a bit for multiple analyses…", false);

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_id: state.sourceId, analysis_types: checked, concept_term, terms }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Analysis failed");

    state.results = data.results;
    renderResults(data.results, data.errors);
    setStatus("analyze-status", "Done.", false);
  } catch (err) {
    setStatus("analyze-status", err.message, true);
  } finally {
    btn.disabled = false;
  }
});

function renderResults(results, errors) {
  const container = document.getElementById("results");
  container.innerHTML = "";
  document.getElementById("step-results").classList.remove("hidden");
  document.getElementById("save-zotero-btn").classList.toggle("hidden", !state.fromZotero);

  Object.entries(results).forEach(([type, markdown]) => {
    const block = document.createElement("div");
    block.className = "result-block";
    block.innerHTML = `
      <h3>${escapeHtml(labelFor(type))}
        <span class="result-actions">
          <button class="secondary copy-btn">Copy</button>
          <button class="secondary export-btn">Export .md</button>
        </span>
      </h3>
      <div class="rendered">${markdownToHtml(markdown)}</div>
    `;
    block.querySelector(".copy-btn").addEventListener("click", () => navigator.clipboard.writeText(markdown));
    block.querySelector(".export-btn").addEventListener("click", () => downloadText(`${type}.md`, markdown));
    container.appendChild(block);
  });

  Object.entries(errors || {}).forEach(([type, msg]) => {
    const block = document.createElement("div");
    block.className = "result-block";
    block.innerHTML = `<h3>${escapeHtml(labelFor(type))}</h3><p class="status-error">${escapeHtml(msg)}</p>`;
    container.appendChild(block);
  });
}

let typeLabelCache = null;
function labelFor(type) {
  return (typeLabelCache && typeLabelCache[type]) || type;
}
fetch("/api/analysis-types").then((r) => r.json()).then((types) => {
  typeLabelCache = {};
  Object.entries(types).forEach(([k, v]) => (typeLabelCache[k] = v.label));
});

document.getElementById("export-all-btn").addEventListener("click", () => {
  const parts = [`# Research Notes\n\n**Source:** ${state.citation ? state.citation.apa : ""}\n`];
  Object.entries(state.results).forEach(([type, md]) => {
    parts.push(`\n---\n\n${md}`);
  });
  downloadText("research-notes.md", parts.join("\n"));
});

document.getElementById("save-zotero-btn").addEventListener("click", async () => {
  if (!state.sourceId) return;
  const statusEl = document.getElementById("analyze-status");
  for (const [type, md] of Object.entries(state.results)) {
    try {
      const res = await fetch("/api/save-to-zotero", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_id: state.sourceId, analysis_label: labelFor(type), markdown: md }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to save note");
    } catch (err) {
      statusEl.textContent = `Error saving "${labelFor(type)}" to Zotero: ${err.message}`;
      statusEl.className = "status-error";
      return;
    }
  }
  statusEl.textContent = "All notes saved to Zotero as child notes on the item.";
  statusEl.className = "status-ok";
});

// ---------- helpers ----------
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

function downloadText(filename, text) {
  const blob = new Blob([text], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// Small Markdown -> HTML renderer for headings, bold/italic, bullet lists,
// and pipe tables - matches the structured output our prompts ask Claude for.
function markdownToHtml(md) {
  const lines = md.split("\n");
  let html = "";
  let inList = false;
  let i = 0;

  function inline(s) {
    s = escapeHtml(s);
    s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(?<!\*)\*([^*]+?)\*(?!\*)/g, "<em>$1</em>");
    return s;
  }

  function closeList() {
    if (inList) { html += "</ul>"; inList = false; }
  }

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { closeList(); i++; continue; }

    const heading = line.match(/^(#{1,6})\s+(.*)/);
    if (heading) {
      closeList();
      const level = heading[1].length;
      html += `<h${level}>${inline(heading[2])}</h${level}>`;
      i++; continue;
    }

    if (line.trim().startsWith("|") && lines[i + 1] && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1])) {
      closeList();
      const headerCells = line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      html += "<table><thead><tr>" + headerCells.map((c) => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>";
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        const cells = lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
        html += "<tr>" + cells.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>";
        i++;
      }
      html += "</tbody></table>";
      continue;
    }

    const bullet = line.trim().match(/^[-*]\s+(.*)/);
    if (bullet) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(bullet[1])}</li>`;
      i++; continue;
    }

    closeList();
    html += `<p>${inline(line)}</p>`;
    i++;
  }
  closeList();
  return html;
}
