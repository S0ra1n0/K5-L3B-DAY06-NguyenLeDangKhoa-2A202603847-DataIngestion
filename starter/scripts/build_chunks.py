"""Build the chunk sets for strategies A and B (C reuses B) and describe them.

Run from starter/:  python -X utf8 scripts/build_chunks.py
Outputs:
  data/chunks/A.jsonl, data/chunks/B.jsonl     one chunk per line
  results/chunk_stats.json                     counts, length distribution, timing,
                                               evidence reachability per question
  results/audit/coherence_positions.json       the 10 fixed coherence positions and
                                               the chunk that covers each, per strategy

"Evidence reachability" only asks whether SOME chunk could ever be a hit (it contains
every evidence quote of a gold and covers the gold page); it uses no retrieval and no
scores, so it does not leak test results into strategy design.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STARTER))

from src.chunking import build  # noqa: E402
from src.models import Chunk, DocumentPage  # noqa: E402

# fixed before any scoring (see ROADMAP step 8): first paragraph of these articles
COHERENCE_ARTICLES = [10, 50, 90, 130, 170]


def squash(text: str) -> str:
    return " ".join(text.split())


def load_pages() -> list[DocumentPage]:
    rows = (json.loads(l) for l in (STARTER / "data/processed/pages.jsonl").read_text(encoding="utf-8").splitlines())
    return [DocumentPage(**row) for row in rows]


def is_hit(chunk: dict, gold: dict) -> bool:
    text = squash(chunk["text"])
    return (chunk["document_id"] == gold["source_id"] and gold["page"] in chunk["metadata"]["pages"]
            and all(squash(q) in text for q in gold["evidence_quote"]))


def golds_of(question: dict) -> list[dict]:
    return [{"source_id": question["gold_source_id"], "page": question["gold_page"],
             "evidence_quote": question["evidence_quote"]}] + question.get("alternative_gold", [])


def first_paragraph(pages: list[DocumentPage], doc: str, article: int) -> tuple[int, str]:
    """(page, text) of the first line after the 'Điều N.' heading."""
    lines = [(p.page, line) for p in pages if p.document_id == doc for line in p.text.split("\n")]
    for i, (page, line) in enumerate(lines):
        if line.startswith(f"Điều {article}. ") and article in next(
                p.metadata["articles_on_page"] for p in pages if p.document_id == doc and p.page == page):
            return lines[i + 1]
    raise LookupError(f"{doc} Điều {article} not found")


def main() -> None:
    config = json.loads((STARTER / "configs/strategies.json").read_text(encoding="utf-8"))
    pages = load_pages()
    questions = json.loads((STARTER.parent / "benchmark/questions.json").read_text(encoding="utf-8"))["questions"]
    out_dir = STARTER / "data/chunks"
    out_dir.mkdir(parents=True, exist_ok=True)
    (STARTER / "results/audit").mkdir(parents=True, exist_ok=True)

    stats, chunk_sets = {}, {}
    for name in sorted({c["chunks_from"] for c in config.values()}):
        started = time.perf_counter()
        chunks: list[Chunk] = build(pages, name, **config[name]["chunking"])
        seconds = time.perf_counter() - started
        rows = [asdict(c) for c in chunks]
        ids = [r["chunk_id"] for r in rows]
        if len(ids) != len(set(ids)):
            raise SystemExit(f"{name}: duplicate chunk ids")
        with open(out_dir / f"{name}.jsonl", "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        chunk_sets[name] = rows
        lengths = [r["metadata"]["char_count"] for r in rows]
        stats[name] = {
            "params": config[name]["chunking"],
            "chunks": len(rows),
            "chunks_per_document": {d: sum(1 for r in rows if r["document_id"] == d)
                                    for d in sorted({r["document_id"] for r in rows})},
            "chars_total": sum(lengths),
            "chars_min": min(lengths), "chars_median": statistics.median(lengths),
            "chars_p90": sorted(lengths)[int(0.9 * (len(lengths) - 1))], "chars_max": max(lengths),
            "multi_page_chunks": sum(1 for r in rows if len(r["metadata"]["pages"]) > 1),
            "split_articles": len({(r["document_id"], r["metadata"]["article"]) for r in rows
                                   if r["metadata"].get("parts", 1) > 1}),
            "chunks_without_article": sum(1 for r in rows if r["metadata"]["article"] is None),
            "build_seconds": round(seconds, 3),
        }

    reach = {}
    for q in questions:
        reach[q["id"]] = {name: any(is_hit(c, g) for c in rows for g in golds_of(q))
                          for name, rows in chunk_sets.items()}
    for name in chunk_sets:
        ok = [qid for qid, r in reach.items() if r[name]]
        stats[name]["evidence_reachable"] = f"{len(ok)}/{len(questions)}"
        stats[name]["evidence_unreachable_ids"] = [qid for qid, r in reach.items() if not r[name]]

    positions = []
    for doc in ("blld-2012", "blld-2019"):
        for article in COHERENCE_ARTICLES:
            page, text = first_paragraph(pages, doc, article)
            probe = squash(text)[:60]
            entry = {"position": f"{doc} Điều {article} (đoạn đầu)", "page": page, "probe": probe}
            for name, rows in chunk_sets.items():
                covering = [r for r in rows if r["document_id"] == doc and page in r["metadata"]["pages"]
                            and probe[:30] in squash(r["text"])]
                entry[name] = covering[0]["chunk_id"] if covering else None
            positions.append(entry)

    (STARTER / "results/chunk_stats.json").write_text(
        json.dumps({"strategies": stats, "evidence_reachability": reach}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    (STARTER / "results/audit/coherence_positions.json").write_text(
        json.dumps(positions, ensure_ascii=False, indent=2), encoding="utf-8")

    for name, s in stats.items():
        print(f"{name}: {s['chunks']} chunks, median {s['chars_median']} chars "
              f"(min {s['chars_min']}, p90 {s['chars_p90']}, max {s['chars_max']}), "
              f"multi-page {s['multi_page_chunks']}, split articles {s['split_articles']}, "
              f"reachable {s['evidence_reachable']} missing {s['evidence_unreachable_ids']}")
    missing = [p["position"] for p in positions if not all(p[n] for n in chunk_sets)]
    print("coherence positions mapped:", len(positions) - len(missing), "/", len(positions), missing or "")


if __name__ == "__main__":
    main()
