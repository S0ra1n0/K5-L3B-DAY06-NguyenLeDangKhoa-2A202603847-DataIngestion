"""Chunking strategies for the Labor Code corpus.

A  fixed_size  : character windows (size, overlap) inside one page. Ignores structure.
B  by_article  : one chunk per Điều (article), may span pages; an article longer than
                 max_size is split at khoản (then điểm, then sentence) boundaries and
                 every part repeats the "Điều N. Tiêu đề" line so it stays readable.
(C reuses the B chunks and only adds a metadata filter at query time.)

Every chunk keeps document_id, source, page (first page), pages (all pages it covers),
year, law_number, chapter and article so a hit can be traced back to the PDF page.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable

from .models import Chunk, DocumentPage

RE_DIEU_LINE = re.compile(r"^Điều (\d+)\. ")
RE_CHUONG_LINE = re.compile(r"^Chương ([IVXLC]+)$")
RE_MUC_LINE = re.compile(r"^Mục \d+$")
RE_KHOAN_LINE = re.compile(r"^\d{1,2}\. ")
RE_DIEM_LINE = re.compile(r"^[a-zđ]\) ")
DOC_FIELDS = ("year", "law_number", "document_type", "language")


def _chunk_id(*parts: Any) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:16]


def _structure_marks(page: DocumentPage) -> list[tuple[int, str, Any]]:
    """(offset, kind, value) of validated article / chapter headings in page.text."""
    marks, offset = [], 0
    valid_articles = list(page.metadata["articles_on_page"])
    for line in page.text.split("\n"):
        if (m := RE_DIEU_LINE.match(line)) and valid_articles and int(m.group(1)) == valid_articles[0]:
            marks.append((offset, "article", valid_articles.pop(0)))
        elif m := RE_CHUONG_LINE.match(line):
            marks.append((offset, "chapter", m.group(1)))
        offset += len(line) + 1
    return marks


def _base_metadata(page: DocumentPage, strategy: str) -> dict[str, Any]:
    return {"strategy": strategy, **{k: page.metadata[k] for k in DOC_FIELDS}}


# --------------------------------------------------------------------------- A

def fixed_size(page: DocumentPage, size: int, overlap: int, strategy: str = "A") -> list[Chunk]:
    """Overlapping character windows over one page (window start step = size - overlap).

    Windows are cut at exact character offsets, never moved to word or sentence
    boundaries: this is the structure-agnostic baseline. Each chunk's chapter/article
    is the one in force at the window start.
    """
    if not 0 <= overlap < size:
        raise ValueError("need 0 <= overlap < size")
    text, marks = page.text, _structure_marks(page)
    chunks: list[Chunk] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chapter, article = page.metadata["chapter_at_start"], page.metadata["article_at_start"]
        for offset, kind, value in marks:
            if offset > start:
                break
            if kind == "chapter":
                chapter = value
            else:
                article = value
        piece = text[start:end]
        chunks.append(Chunk(
            chunk_id=_chunk_id(strategy, page.document_id, page.page, start, piece),
            document_id=page.document_id, source=page.source, page=page.page, text=piece,
            metadata={**_base_metadata(page, strategy), "pages": [page.page],
                      "chapter": chapter, "article": article,
                      "char_start": start, "char_count": len(piece)},
        ))
        if end == len(text):
            break
        start += size - overlap
    return chunks


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Kept for the starter interface; this corpus uses by_article for strategy B."""
    raise NotImplementedError("Use by_article(pages, max_size) for the Labor Code corpus")


# --------------------------------------------------------------------------- B

def _units(pages: list[DocumentPage]) -> list[dict[str, Any]]:
    """Split one document into article units: [{article, chapter, lines:[(page, text)]}].

    Chương/Mục title lines are attached to the article that follows them; text before
    Điều 1 (issuing body, preamble) becomes a unit with article=None.
    """
    units: list[dict[str, Any]] = []
    pending_titles: list[tuple[int, str]] = []
    chapter = None
    current = {"article": None, "chapter": None, "lines": []}
    for page in pages:
        valid = list(page.metadata["articles_on_page"])
        for line in page.text.split("\n"):
            m = RE_DIEU_LINE.match(line)
            if m and valid and int(m.group(1)) == valid[0]:
                valid.pop(0)
                if current["lines"]:
                    units.append(current)
                current = {"article": int(m.group(1)), "chapter": chapter,
                           "lines": pending_titles + [(page.page, line)]}
                pending_titles = []
                continue
            if cm := RE_CHUONG_LINE.match(line):
                chapter = cm.group(1)
                pending_titles.append((page.page, line))
                continue
            if RE_MUC_LINE.match(line):                     # section title belongs to what follows
                pending_titles.append((page.page, line))
                continue
            if pending_titles and line.isupper():
                pending_titles.append((page.page, line))   # chapter/section title text
                continue
            if pending_titles:                              # title not followed by an article
                current["lines"].extend(pending_titles)
                pending_titles = []
            current["lines"].append((page.page, line))
    current["lines"].extend(pending_titles)
    if current["lines"]:
        units.append(current)
    return units


def _join(lines: list[tuple[int, str]]) -> str:
    """Join lines; a paragraph cut by a page break is re-joined with a space."""
    out = ""
    for i, (page, text) in enumerate(lines):
        if i == 0:
            out = text
            continue
        prev_page = lines[i - 1][0]
        continues = (page != prev_page and not (RE_KHOAN_LINE.match(text) or RE_DIEM_LINE.match(text)
                     or RE_DIEU_LINE.match(text)) and not out.endswith((".", ";", ":")))
        out += (" " if continues else "\n") + text
    return out


def _split_long(lines: list[tuple[int, str]], header: list[tuple[int, str]],
                max_size: int) -> list[list[tuple[int, str]]]:
    """Greedy pack of structural blocks (khoản > điểm > sentence) under max_size."""
    header_len = len(_join(header)) + 1 if header else 0
    budget = max_size - header_len

    def blocks(seq: list[tuple[int, str]], pattern: re.Pattern | None) -> list[list[tuple[int, str]]]:
        out: list[list[tuple[int, str]]] = []
        for item in seq:
            if not out or (pattern and pattern.match(item[1])):
                out.append([item])
            else:
                out[-1].append(item)
        return out

    def explode(block: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
        if len(_join(block)) <= budget:
            return [block]
        if len(block) > 1:                         # khoản with several điểm: split by điểm
            parts = blocks(block, RE_DIEM_LINE)
            if len(parts) > 1:
                return [p for part in parts for p in explode(part)]
        out = []                                   # one long paragraph: split by sentence
        for page, text in block:
            sentences = re.split(r"(?<=[.;:])\s+", text)
            buf = ""
            for sentence in sentences:
                while len(sentence) > budget:      # no boundary at all: hard cut
                    out.append([(page, sentence[:budget])])
                    sentence = sentence[budget:]
                if buf and len(buf) + 1 + len(sentence) > budget:
                    out.append([(page, buf)])
                    buf = sentence
                else:
                    buf = f"{buf} {sentence}".strip()
            if buf:
                out.append([(page, buf)])
        return out

    pieces = [p for block in blocks(lines, RE_KHOAN_LINE) for p in explode(block)]
    groups: list[list[tuple[int, str]]] = []
    for piece in pieces:
        if groups and len(_join(groups[-1] + piece)) <= budget:
            groups[-1] = groups[-1] + piece
        else:
            groups.append(piece)
    return groups


def by_article(pages: list[DocumentPage], max_size: int, strategy: str = "B") -> list[Chunk]:
    """One chunk per article; long articles split at khoản/điểm/sentence boundaries."""
    if not pages:
        return []
    first = pages[0]
    chunks: list[Chunk] = []
    for unit in _units(sorted(pages, key=lambda p: p.page)):
        lines = unit["lines"]
        text = _join(lines)
        if len(text) <= max_size:
            groups = [lines]
            header: list[tuple[int, str]] = []
        else:
            head_idx = next((i for i, (_, t) in enumerate(lines) if RE_DIEU_LINE.match(t)), None)
            header = [lines[head_idx]] if head_idx is not None else []
            body = lines[head_idx + 1:] if head_idx is not None else lines
            prefix = lines[:head_idx] if head_idx is not None else []
            # budget leaves room for the heading and, conservatively, the chapter titles
            groups = _split_long(body, prefix + header, max_size)
            if prefix:                              # chapter titles go with the first part
                groups[0] = prefix + groups[0]
        for part, group in enumerate(groups, start=1):
            # every part of a split article starts with its "Điều N. ..." line
            full = group if len(groups) == 1 else _insert_header(group, header)
            piece = _join(full)
            # a repeated heading does not make its page part of a later part's content
            content = group if part > 1 or not header else group + header
            pages_covered = sorted({p for p, _ in content})
            chunks.append(Chunk(
                chunk_id=_chunk_id(strategy, first.document_id, unit["article"], part, piece),
                document_id=first.document_id, source=first.source, page=pages_covered[0], text=piece,
                metadata={**_base_metadata(first, strategy), "pages": pages_covered,
                          "chapter": unit["chapter"], "article": unit["article"],
                          "part": part, "parts": len(groups), "char_count": len(piece)},
            ))
    return chunks


def _insert_header(group: list[tuple[int, str]], header: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Place the article heading right after any leading chapter/section title lines."""
    if not header or header[0] in group:
        return group
    i = 0
    while i < len(group) and (RE_CHUONG_LINE.match(group[i][1]) or RE_MUC_LINE.match(group[i][1])
                              or group[i][1].isupper()):
        i += 1
    return group[:i] + header + group[i:]


def build(pages: Iterable[DocumentPage], strategy: str, **params: Any) -> list[Chunk]:
    """Chunk every document of the corpus with one strategy."""
    by_doc: dict[str, list[DocumentPage]] = {}
    for page in pages:
        by_doc.setdefault(page.document_id, []).append(page)
    chunks: list[Chunk] = []
    for doc_pages in by_doc.values():
        doc_pages.sort(key=lambda p: p.page)
        if params["method"] == "fixed":
            for page in doc_pages:
                chunks.extend(fixed_size(page, params["size"], params["overlap"], strategy))
        elif params["method"] == "article":
            chunks.extend(by_article(doc_pages, params["max_size"], strategy))
        else:
            raise ValueError(f"unknown method {params['method']}")
    return chunks
