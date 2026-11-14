"""Evaluate retrieved evidence per question and aggregate Hit@1 / Evidence Hit@3.

A retrieved chunk is a HIT for a question when, for at least one documented gold
(main or alternative): the chunk's document_id equals the gold source_id, the gold
page is one of the pages the chunk covers, and the chunk text contains EVERY
evidence quote of that gold (compared after collapsing whitespace). Evidence split
across two chunks is therefore a miss, and is reported as such.

Manual labels (coherence, grounding) are never inferred here.
"""
from __future__ import annotations

from typing import Any


def squash(text: str) -> str:
    return " ".join(text.split())


def golds_of(question: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"source_id": question["gold_source_id"], "page": question["gold_page"],
             "evidence_quote": question["evidence_quote"]}] + question.get("alternative_gold", [])


def chunk_hit(hit: dict[str, Any], question: dict[str, Any]) -> dict[str, Any]:
    """Whether one retrieved chunk satisfies a gold; also report partial matches."""
    text = squash(hit["text"])
    best = {"hit": False, "matched_gold": None, "right_source_page": False, "quotes_found": 0}
    for gold in golds_of(question):
        same_place = hit["document_id"] == gold["source_id"] and gold["page"] in hit["pages"]
        found = sum(1 for q in gold["evidence_quote"] if squash(q) in text)
        if same_place and found == len(gold["evidence_quote"]):
            return {"hit": True, "matched_gold": f"{gold['source_id']}#p{gold['page']}",
                    "right_source_page": True, "quotes_found": found}
        if same_place:
            best["right_source_page"] = True
            best["quotes_found"] = max(best["quotes_found"], found)
    return best


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    """Label each of the top-k hits and derive hit@1, hit@3 and filter compliance."""
    labelled = []
    for rank, hit in enumerate(hits, start=1):
        labelled.append({"rank": rank, **{k: hit[k] for k in (
            "chunk_id", "document_id", "source", "page", "pages", "year", "law_number",
            "chapter", "article")}, "score": round(float(hit["score"]), 6),
            "text": hit["text"], **chunk_hit(hit, question)})
    wanted = question.get("filter") or {}
    compliance = (all(all(h[k] == v for k, v in wanted.items()) for h in labelled)
                  if wanted else None)
    return {
        "hit@1": bool(labelled and labelled[0]["hit"]),
        "hit@3": any(h["hit"] for h in labelled[:3]),
        "first_hit_rank": next((h["rank"] for h in labelled if h["hit"]), None),
        "filter_compliant_top3": compliance,
        "evidence_split_suspected": (not any(h["hit"] for h in labelled[:3])
                                     and any(h["right_source_page"] and h["quotes_found"] > 0
                                             for h in labelled[:3])),
        "top_k": labelled,
    }


def _ratio(n: int, total: int) -> dict[str, Any]:
    return {"n": n, "N": total, "rate": round(n / total, 4) if total else None}


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Hit@1 / Evidence Hit@3 (n/N) by strategy and split, plus filter compliance."""
    out: dict[str, Any] = {}
    for strategy in sorted({t["strategy"] for t in traces}):
        out[strategy] = {}
        for split in sorted({t["split"] for t in traces if t["strategy"] == strategy}):
            rows = [t for t in traces if t["strategy"] == strategy and t["split"] == split]
            filtered = [t for t in rows if t["question_filter"]]
            by_type: dict[str, Any] = {}
            for qtype in sorted({t["type"] for t in rows}):
                sub = [t for t in rows if t["type"] == qtype]
                by_type[qtype] = {"hit@1": _ratio(sum(t["hit@1"] for t in sub), len(sub)),
                                  "hit@3": _ratio(sum(t["hit@3"] for t in sub), len(sub))}
            out[strategy][split] = {
                "hit@1": _ratio(sum(t["hit@1"] for t in rows), len(rows)),
                "hit@3": _ratio(sum(t["hit@3"] for t in rows), len(rows)),
                "filter_compliance_top3": (_ratio(sum(t["filter_compliant_top3"] for t in filtered), len(filtered))
                                           if filtered else "N/A"),
                "missed_hit@3": [t["id"] for t in rows if not t["hit@3"]],
                "evidence_split_suspected": [t["id"] for t in rows if t["evidence_split_suspected"]],
                "mean_latency_ms": round(sum(t["latency_ms"] for t in rows) / len(rows), 1),
                "by_type": by_type,
            }
    return out
