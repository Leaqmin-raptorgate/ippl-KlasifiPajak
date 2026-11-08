"""Pure-Python BM25 over a small regulation corpus (FR-12).

Passages in ``corpus.json`` are whitespace-collapsed ``pdftotext`` output,
including OCR errors. Do not replace them with recalled article text.
No embeddings and no network.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

_TOKEN = re.compile(r"[0-9A-Za-z]+")
_K1 = 1.5
_B = 0.75
_MAX_HITS = 5

_docs: list[dict[str, str]] | None = None
_index: list[tuple[dict[str, str], dict[str, int], int]] | None = None
_df: dict[str, int] | None = None
_avgdl: float = 0.0


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.casefold())


def _load_docs() -> list[dict[str, str]]:
    path = Path(__file__).with_name("corpus.json")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    docs: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        doc_id = item.get("id")
        text = item.get("text")
        citation = item.get("citation")
        if not all(isinstance(value, str) and value for value in (doc_id, text, citation)):
            continue
        docs.append({"id": doc_id, "text": text, "citation": citation})
        if len(docs) == _MAX_HITS:
            break
    return docs


def _ensure_index() -> None:
    global _docs, _index, _df, _avgdl
    if _index is not None:
        return
    _docs = _load_docs()
    built: list[tuple[dict[str, str], dict[str, int], int]] = []
    df: dict[str, int] = {}
    total = 0
    for doc in _docs:
        counts: dict[str, int] = {}
        tokens = _tokens(doc["text"])
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        built.append((doc, counts, len(tokens)))
        total += len(tokens)
        for token in counts:
            df[token] = df.get(token, 0) + 1
    _index = built
    _df = df
    _avgdl = (total / len(built)) if built else 0.0


def _idf(df: int, n_docs: int) -> float:
    return math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))


def search(query: str) -> list[dict]:
    """Return at most five corpus hits with ``id``, ``text``, and ``citation`` (FR-12)."""
    if not isinstance(query, str) or not query.strip():
        return []
    _ensure_index()
    assert _index is not None and _df is not None
    if not _index or _avgdl <= 0:
        return []
    query_counts: dict[str, int] = {}
    for token in _tokens(query):
        query_counts[token] = query_counts.get(token, 0) + 1
    if not query_counts:
        return []
    n_docs = len(_index)
    ranked: list[tuple[float, str, dict[str, str]]] = []
    for doc, counts, length in _index:
        score = 0.0
        for token in query_counts:
            freq = counts.get(token, 0)
            if freq == 0:
                continue
            idf = _idf(_df.get(token, 0), n_docs)
            denom = freq + _K1 * (1.0 - _B + _B * length / _avgdl)
            score += idf * (freq * (_K1 + 1.0)) / denom
        if score > 0:
            ranked.append((score, doc["id"], doc))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [
        {"id": doc["id"], "text": doc["text"], "citation": doc["citation"]}
        for _score, _doc_id, doc in ranked[:_MAX_HITS]
    ]
