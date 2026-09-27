"""Small local document retriever: extract PDF/TXT and rank chunks by term overlap."""
from __future__ import annotations

import re
from dataclasses import dataclass

from config import MAX_CONTEXT_CHARS

WORD_RE = re.compile(r"[\wÀ-ỹ]+", re.UNICODE)


@dataclass
class Chunk:
    source: str
    text: str


def extract_text(name: str, content: bytes) -> str:
    suffix = name.lower().rsplit(".", 1)[-1]
    if suffix == "txt":
        return content.decode("utf-8", errors="replace")
    if suffix == "pdf":
        try:
            from pypdf import PdfReader
            from io import BytesIO
            reader = PdfReader(BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise ValueError(f"Không đọc được PDF: {exc}") from exc
    raise ValueError("Chỉ hỗ trợ file PDF và TXT.")


def split_chunks(name: str, text: str, size: int = 900, overlap: int = 140) -> list[Chunk]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    chunks, start = [], 0
    while start < len(clean):
        end = min(len(clean), start + size)
        if end < len(clean):
            boundary = clean.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        chunks.append(Chunk(name, clean[start:end]))
        if end == len(clean):
            break
        start = max(start + 1, end - overlap)
    return chunks


def retrieve(question: str, documents: dict[str, str], limit: int = 5) -> str:
    terms = {w.casefold() for w in WORD_RE.findall(question) if len(w) > 1}
    if not terms:
        return ""
    ranked: list[tuple[int, Chunk]] = []
    for name, text in documents.items():
        for chunk in split_chunks(name, text):
            haystack = chunk.text.casefold()
            score = sum(haystack.count(term) for term in terms)
            if score:
                ranked.append((score, chunk))
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected, used = [], 0
    for score, chunk in ranked[:limit]:
        excerpt = f"[Nguồn: {chunk.source}; độ khớp: {score}]\n{chunk.text}"
        if used + len(excerpt) > MAX_CONTEXT_CHARS:
            break
        selected.append(excerpt)
        used += len(excerpt)
    return "\n\n---\n\n".join(selected)


def all_document_context(documents: dict[str, str]) -> str:
    """Return as much extracted text as fits for requests that need a full summary."""
    selected: list[str] = []
    remaining = MAX_CONTEXT_CHARS
    truncated = False
    for name, text in documents.items():
        for chunk in split_chunks(name, text):
            excerpt = f"[Source: {chunk.source}]\n{chunk.text}"
            cost = len(excerpt) + 2
            if cost <= remaining:
                selected.append(excerpt)
                remaining -= cost
                continue
            room = remaining - len(f"[Source: {name}]\n")
            if room > 0:
                selected.append(f"[Source: {name}]\n{chunk.text[:room]}")
            truncated = True
            break
        if truncated:
            break
    if truncated and selected:
        selected.append("[Additional document text was omitted to fit the model context limit.]")
    return "\n\n---\n\n".join(selected)
