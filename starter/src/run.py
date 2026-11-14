"""Run the retrieval benchmark for strategies A, B, C.

Run from starter/ in this order (each step refuses to run out of order):
  python -X utf8 -m src.run dev      # A/B/C on the 15 dev questions
  python -X utf8 -m src.run select   # apply the pre-registered criterion to dev only
  python -X utf8 -m src.run test     # A/B/C once on the 5 test questions

Prerequisites: scripts/build_corpus.py, build_chunks.py, embed_chunks.py, ingest_store.py.
Outputs in results/: traces/<strategy>_<split>.jsonl, metrics_<split>.json, selection.json.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .store import PgVectorStore

STARTER = Path(__file__).resolve().parents[1]
RESULTS = STARTER / "results"
TOP_K = 3

# Pre-registered in benchmark/README.md before any retrieval run.
SELECTION_CRITERION = ["dev Evidence Hit@3 (higher)", "dev Hit@1 (higher)",
                       "dev filter compliance on filter questions (higher)",
                       "fewer chunks", "lower ingest time"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def run_split(split: str) -> None:
    load_dotenv(STARTER / ".env")
    config = load_json(STARTER / "configs/strategies.json")
    questions = [q for q in load_json(STARTER.parent / "benchmark/questions.json")["questions"]
                 if q["split"] == split]
    embedder = MyEmbedder()
    emb_log = load_json(RESULTS / "embedding_log.json")
    if embedder.model_name != emb_log["embedder"]["model"]:
        raise SystemExit("query model differs from the model used for the stored chunks")
    store = PgVectorStore(os.getenv("DATABASE_URL", ""), embedder.dimensions)

    query_vectors = {q["id"]: embedder.embed_query(q["question"]) for q in questions}
    traces = []
    (RESULTS / "traces").mkdir(parents=True, exist_ok=True)
    for strategy, cfg in sorted(config.items()):
        if store.count(cfg["chunks_from"]) == 0:
            raise SystemExit(f"chunk set {cfg['chunks_from']} is empty: run scripts/ingest_store.py")
        rows = []
        for q in questions:
            filters = q["filter"] if (cfg["use_filter"] and q["filter"]) else None
            t0 = time.perf_counter()
            hits = store.search(cfg["chunks_from"], query_vectors[q["id"]], top_k=TOP_K, filters=filters)
            latency = (time.perf_counter() - t0) * 1000
            result = evaluate_query(q, hits)
            rows.append({
                "strategy": strategy, "split": split, "id": q["id"], "type": q["type"],
                "question": q["question"], "question_filter": q["filter"], "filter_applied": filters,
                "gold": [f"{q['gold_source_id']}#p{q['gold_page']}"] +
                        [f"{g['source_id']}#p{g['page']}" for g in q.get("alternative_gold", [])],
                "expected_answer": q["expected_answer"], "latency_ms": round(latency, 2), **result,
            })
        with open(RESULTS / f"traces/{strategy}_{split}.jsonl", "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        traces.extend(rows)

    metrics = {"split": split, "run_at": now(), "top_k": TOP_K, "model": embedder.model_name,
               "questions": len(questions), "strategies": summarize(traces)}
    (RESULTS / f"metrics_{split}.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print_table(metrics)


def print_table(metrics: dict) -> None:
    print(f"split={metrics['split']} questions={metrics['questions']}")
    for strategy, by_split in metrics["strategies"].items():
        m = by_split[metrics["split"]]
        fc = m["filter_compliance_top3"]
        fc = f"{fc['n']}/{fc['N']}" if isinstance(fc, dict) else fc
        print(f"  {strategy}: Hit@1 {m['hit@1']['n']}/{m['hit@1']['N']}  Hit@3 {m['hit@3']['n']}/{m['hit@3']['N']}"
              f"  filter {fc}  missed@3 {m['missed_hit@3']}  split? {m['evidence_split_suspected']}")


def select() -> None:
    dev = load_json(RESULTS / "metrics_dev.json")
    if (RESULTS / "metrics_test.json").exists():
        raise SystemExit("test already run: selection must be made before test")
    config = load_json(STARTER / "configs/strategies.json")
    chunk_stats = load_json(RESULTS / "chunk_stats.json")["strategies"]
    store_log = load_json(RESULTS / "store_log.json")["sets"]
    ranking = []
    for strategy, cfg in config.items():
        m = dev["strategies"][strategy]["dev"]
        fc = m["filter_compliance_top3"]
        chunk_set = cfg["chunks_from"]
        key = (m["hit@3"]["n"], m["hit@1"]["n"], fc["rate"] if isinstance(fc, dict) else 0,
               -chunk_stats[chunk_set]["chunks"], -store_log[chunk_set]["first_seconds"])
        ranking.append({"strategy": strategy, "key": key,
                        "hit@3": f"{m['hit@3']['n']}/{m['hit@3']['N']}",
                        "hit@1": f"{m['hit@1']['n']}/{m['hit@1']['N']}",
                        "filter_compliance": f"{fc['n']}/{fc['N']}" if isinstance(fc, dict) else fc,
                        "chunks": chunk_stats[chunk_set]["chunks"]})
    ranking.sort(key=lambda r: r["key"], reverse=True)
    tied = [r["strategy"] for r in ranking if r["key"] == ranking[0]["key"]]
    selection = {"selected": ranking[0]["strategy"], "tied_with": tied[1:], "decided_at": now(),
                 "criterion": SELECTION_CRITERION, "based_on": "metrics_dev.json only",
                 "ranking": [{k: v for k, v in r.items() if k != "key"} for r in ranking]}
    (RESULTS / "selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(selection, ensure_ascii=False, indent=2))


def main() -> None:
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    if step == "dev":
        run_split("dev")
    elif step == "select":
        select()
    elif step == "test":
        if not (RESULTS / "selection.json").exists():
            raise SystemExit("run `python -m src.run select` on dev results before test")
        if (RESULTS / "metrics_test.json").exists():
            raise SystemExit("test was already run once; results/metrics_test.json exists")
        run_split("test")
    else:
        raise SystemExit("usage: python -m src.run dev|select|test")


if __name__ == "__main__":
    main()
