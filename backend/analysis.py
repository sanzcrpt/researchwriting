"""Prompt templates for the five reading/note-taking methodologies, plus the
Claude call that runs them.

Each builder returns (system_prompt, user_prompt). The model is always asked
to (a) ground claims in the supplied text with page/location citations where
the text has [PAGE n] markers, (b) flag anything it adds beyond the source
as illustrative rather than sourced, and (c) respond in clean Markdown only.
"""
from __future__ import annotations

import os
from typing import Optional

from anthropic import Anthropic

from .citation import Citation

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_SOURCE_CHARS = int(os.environ.get("MAX_SOURCE_CHARS", "180000"))

_client: Optional[Anthropic] = None


def get_client() -> Anthropic:
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set on the server. Add it to your .env file "
                "(see .env.example) and restart the server."
            )
        _client = Anthropic(api_key=api_key)
    return _client


BASE_SYSTEM = """You are a meticulous research assistant helping a graduate student build \
notes for a thesis or dissertation literature review. You are careful, precise, and \
always ground your claims in the source text provided.

Rules you always follow:
- Cite page numbers using the [PAGE n] markers embedded in the source text whenever you \
quote or paraphrase, in the form (p. n). If the source has no page markers, cite it as \
(para. n) counting paragraphs, or simply omit a locator if truly ungrounded.
- Never fabricate quotations. Only quote text that actually appears in the source provided.
- If you illustrate a point with an example that is NOT drawn directly from the source, \
label it clearly as "(illustrative - not from source)".
- Output clean Markdown only: headings, bold, bullet lists, and tables where useful. \
No preamble like "Here is...", no closing remarks - just the content.
- Be substantive and specific rather than generic. Prefer the source's own terminology.
"""


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_SOURCE_CHARS:
        return text, False
    return text[:MAX_SOURCE_CHARS], True


def _citation_block(citation: Citation) -> str:
    return (
        f"Title: {citation.title}\n"
        f"Author(s): {', '.join(a.apa() for a in citation.authors) or 'unknown'}\n"
        f"Year: {citation.year or 'n.d.'}\n"
        f"Container/Publisher: {citation.container_title or 'n/a'}\n"
        f"Short form to use for in-text citation: ({citation.short_author_year()})\n"
    )


def _source_block(citation: Citation, text: str) -> tuple[str, bool]:
    truncated_text, was_truncated = _truncate(text)
    block = f"SOURCE METADATA\n{_citation_block(citation)}\nSOURCE TEXT\n{truncated_text}"
    return block, was_truncated


def build_rhetorical_precis(citation: Citation, text: str) -> tuple[str, str]:
    source_block, truncated = _source_block(citation, text)
    task = f"""Write a rhetorical precis of the source below, following this EXACT four-sentence \
structure (this is the Woodworth/rhetorical precis method used in academic reading courses):

1. **Sentence 1**: Name of the author(s), genre and title of the work, date in parentheses \
if known; a rhetorically accurate verb (e.g. "argues," "asserts," "demonstrates," "suggests," \
"claims"); and a "that" clause stating the major assertion (thesis) of the work.
2. **Sentence 2**: An explanation of how the author develops or supports the thesis, usually \
in chronological or logical order, citing (p. n) for specific moves.
3. **Sentence 3**: A statement of the author's apparent purpose, followed by an "in order to" \
phrase that explains what the author wants the audience to do or understand as a result.
4. **Sentence 4**: A description of the intended audience and/or the relationship the author \
establishes with that audience (tone, stance, assumed background).

Output format:
## Rhetorical Precis
### Citation
{{apa reference}}
### Precis
{{the four sentences, each on its own line, numbered}}
"""
    user = f"{source_block}\n\n{task}"
    if truncated:
        user += "\n\n(Note: source text was truncated to fit context length; work from what is provided.)"
    return BASE_SYSTEM, user


def build_dialectical_notes(citation: Citation, text: str) -> tuple[str, str]:
    source_block, truncated = _source_block(citation, text)
    task = """Produce dialectical (double-entry) notes on the source below. This is a two-column \
method: the left column holds direct quotations or close paraphrases from the text (with page \
citations), and the right column holds the reader's own response - questions, connections to \
other ideas, critiques, or implications for a thesis project.

Select 6-10 of the most significant, quotable, or argument-bearing passages spread across the \
source (not all from the introduction).

Output format:
## Dialectical Notes
### Citation
{apa reference}

| Passage (quote/paraphrase + page) | Response (question / connection / critique / implication) |
|---|---|
| "..." (p. n) | ... |
(repeat rows)

### Synthesis
A short paragraph (4-6 sentences) synthesizing what these passages together suggest, and what \
questions remain open.
"""
    user = f"{source_block}\n\n{task}"
    if truncated:
        user += "\n\n(Note: source text was truncated to fit context length; work from what is provided.)"
    return BASE_SYSTEM, user


def build_charted_reading(citation: Citation, text: str) -> tuple[str, str]:
    source_block, truncated = _source_block(citation, text)
    task = """Produce a "reading chart" (synthesis-matrix style structured chart) for the source \
below, the kind used to quickly compare sources across a literature review later.

Output format (a single Markdown table with one row, so it can later be stacked with other \
sources' rows into one big comparison matrix), followed by supporting bullet detail:

## Charted Reading
### Citation
{apa reference}

| Field | Notes |
|---|---|
| Research question / thesis | ... (p. n) |
| Methodology (if applicable) | ... |
| Key findings / arguments | bulleted, each with (p. n) |
| Key terms & concepts used | ... |
| Evidence & support offered | ... |
| Strengths | ... |
| Limitations / gaps | ... |
| Notable quotes | 2-4 short quotes with (p. n) |
| Relevance to my research (prompt for user to fill in) | *(leave this cell as "— fill in —")* |
"""
    user = f"{source_block}\n\n{task}"
    if truncated:
        user += "\n\n(Note: source text was truncated to fit context length; work from what is provided.)"
    return BASE_SYSTEM, user


def build_concept_development(citation: Citation, text: str, concept_term: str) -> tuple[str, str]:
    source_block, truncated = _source_block(citation, text)
    task = f"""Perform a concept-development / concept-analysis of the term or phrase \
"{concept_term}" as it is used in the source below. Follow the classic concept-analysis \
structure (Walker & Avant style) used for developing key terms in a thesis:

1. **Uses & classifications** - how the source (and, briefly, common/disciplinary usage if you \
know it) uses or classifies this term. Note if the source treats it as a single fixed idea or \
a spectrum/typology.
2. **Defining (critical) attributes** - the specific characteristics that MUST be present for \
something to count as an instance of this concept, per the source. Cite (p. n).
3. **Model case ("live" case)** - a concrete example, drawn from the source if possible \
(otherwise clearly labeled illustrative), that includes ALL the defining attributes - a clean, \
unambiguous positive instance of the concept.
4. **Contrary case ("dead" case)** - a concrete example that clearly lacks the defining \
attributes - something that looks related but is NOT an instance of the concept, to sharpen \
the boundary.
5. **Antecedents** - conditions or events that must exist/occur before this concept can apply.
6. **Consequences** - what results or follows once this concept applies.
7. **Empirical referents** - how you would recognize/measure this concept in real data or \
practice.

Output format:
## Concept Development: {concept_term}
### Citation
{{apa reference}}
### Uses & Classifications
...
### Defining (Critical) Attributes
- ...
### Model Case ("Live")
...
### Contrary Case ("Dead")
...
### Antecedents
- ...
### Consequences
- ...
### Empirical Referents
- ...
"""
    user = f"{source_block}\n\n{task}"
    if truncated:
        user += "\n\n(Note: source text was truncated to fit context length; work from what is provided.)"
    return BASE_SYSTEM, user


def build_term_comparison(citation: Citation, text: str, terms: list[str]) -> tuple[str, str]:
    source_block, truncated = _source_block(citation, text)
    terms_str = ", ".join(terms)
    task = f"""Compare and contrast the following key terms as used in (or relevant to) the \
source below: {terms_str}. If a term does not literally appear in the source, use the source's \
closest related discussion, and clearly note when you're drawing on general scholarly usage \
instead of the source itself.

Output format:
## Key Term Comparison: {terms_str}
### Citation
{{apa reference}}

| Term | Definition (as used/relevant here) | Key characteristics | How it differs from the other term(s) |
|---|---|---|---|
(one row per term, with (p. n) citations where grounded in the source)

### Analogy
Offer one clear analogy or metaphor that captures the relationship between these terms \
(e.g. "X is to Y as ___ is to ___"), explained in 2-3 sentences.

### Synthesis
A short paragraph (4-6 sentences) on why this comparison matters for understanding the source's \
argument or for a thesis built around these terms.
"""
    user = f"{source_block}\n\n{task}"
    if truncated:
        user += "\n\n(Note: source text was truncated to fit context length; work from what is provided.)"
    return BASE_SYSTEM, user


ANALYSIS_TYPES = {
    "rhetorical_precis": {
        "label": "Rhetorical Precis",
        "builder": build_rhetorical_precis,
        "requires": [],
        "max_tokens": 1200,
    },
    "dialectical_notes": {
        "label": "Dialectical Notetaking",
        "builder": build_dialectical_notes,
        "requires": [],
        "max_tokens": 2800,
    },
    "charted_reading": {
        "label": "Charted Reading",
        "builder": build_charted_reading,
        "requires": [],
        "max_tokens": 2200,
    },
    "concept_development": {
        "label": "Concept Development (Term/Concept Analysis)",
        "builder": build_concept_development,
        "requires": ["concept_term"],
        "max_tokens": 2400,
    },
    "term_comparison": {
        "label": "Key Term Comparison",
        "builder": build_term_comparison,
        "requires": ["terms"],
        "max_tokens": 2000,
    },
}


def run_analysis(analysis_type: str, citation: Citation, text: str, options: dict) -> str:
    if analysis_type not in ANALYSIS_TYPES:
        raise ValueError(f"Unknown analysis type: {analysis_type}")
    spec = ANALYSIS_TYPES[analysis_type]
    for req in spec["requires"]:
        if not options.get(req):
            raise ValueError(f"Analysis '{analysis_type}' requires '{req}' in options.")

    if analysis_type == "concept_development":
        system, user = spec["builder"](citation, text, options["concept_term"])
    elif analysis_type == "term_comparison":
        system, user = spec["builder"](citation, text, options["terms"])
    else:
        system, user = spec["builder"](citation, text)

    client = get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=spec["max_tokens"],
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in response.content if getattr(block, "type", None) == "text").strip()
