"""Load chunk sets A and B with their vectors into pgvector, then check the store.

Run from starter/:  python -X utf8 scripts/ingest_store.py
Needs: docker compose -p day6_student_starter up -d --wait, and data/vectors/*.npz
(scripts/embed_chunks.py). Outputs results/store_log.json.

Checks (none of them uses the benchmark questions):
  1. re-ingest: loading the same chunks twice leaves row counts unchanged
  2. stale rows: a scratch chunk set loaded with 3 chunks, then 2, ends with 2 rows
  3. self-retrieval: a sample chunk's own vector returns that chunk at rank 1
  4. filter: searching with year=2012 / 2019 returns only rows of that year
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

STARTER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STARTER))
load_dotenv(STARTER / ".env")

from src.models import Chunk  # noqa: E402
from src.store import PgVectorStore  # noqa: E402


def load_set(name: str) -> tuple[list[Chunk], list[list[float]], str]:
    chunks = [Chunk(**json.loads(l)) for l in
              (STARTER / f"data/chunks/{name}.jsonl").read_text(encoding="utf-8").splitlines()]
    data = np.load(STARTER / f"data/vectors/{name}.npz")
    ids = [str(i) for i in data["chunk_ids"]]
    if ids != [c.chunk_id for c in chunks]:
        raise SystemExit(f"{name}: vectors are stale, run scripts/embed_chunks.py")
    return chunks, data["vectors"].tolist(), ids[0]


def main() -> None:
    config = json.loads((STARTER / "configs/strategies.json").read_text(encoding="utf-8"))
    emb_log = json.loads((STARTER / "results/embedding_log.json").read_text(encoding="utf-8"))
    model, dims = emb_log["embedder"]["model"], emb_log["embedder"]["dimensions"]
    store = PgVectorStore(os.getenv("DATABASE_URL", ""), dims)
    store.create_schema()
    with store.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT current_setting('server_version'), extversion FROM pg_extension WHERE extname='vector'")
        pg_version, pgvector_version = cur.fetchone()

    log: dict = {"database": {"postgresql": pg_version, "pgvector": pgvector_version, "table": "chunks",
                              "metric": "cosine distance (<=>), score = 1 - distance",
                              "search": "exact (no ANN index)"},
                 "model": model, "dimensions": dims, "sets": {}, "checks": {}}
    sets = sorted({c["chunks_from"] for c in config.values()})
    for name in sets:
        chunks, vectors, _ = load_set(name)
        t0 = time.perf_counter()
        first = store.upsert(name, chunks, vectors, model)
        t1 = time.perf_counter()
        second = store.upsert(name, chunks, vectors, model)
        t2 = time.perf_counter()
        log["sets"][name] = {"first_load": first, "first_seconds": round(t1 - t0, 2),
                             "reload": second, "reload_seconds": round(t2 - t1, 2)}
        log["checks"][f"reingest_{name}"] = second["before"] == second["after"] == len(chunks)
        print(f"{name}: load {first} ({t1 - t0:.1f}s); reload {second}")

    # 2. stale-row removal on a scratch set
    chunks, vectors, _ = load_set("B")
    scratch = "_selftest"
    store.delete_set(scratch)
    store.upsert(scratch, chunks[:3], vectors[:3], model)
    result = store.upsert(scratch, chunks[:2], vectors[:2], model)
    log["checks"]["stale_rows_removed"] = result["deleted_stale"] == 1 and result["after"] == 2
    store.delete_set(scratch)

    # 3. self-retrieval and 4. filter, on a fixed sample of chunks (every 50th)
    self_ok, filter_ok = [], []
    for name in sets:
        chunks, vectors, _ = load_set(name)
        for i in range(0, len(chunks), 50):
            top = store.search(name, vectors[i], top_k=1)
            self_ok.append(top[0]["chunk_id"] == chunks[i].chunk_id and abs(top[0]["score"] - 1) < 1e-4)
        for year in (2012, 2019):
            hits = store.search(name, vectors[0], top_k=10, filters={"year": year})
            filter_ok.append(len(hits) == 10 and all(h["year"] == year for h in hits))
    log["checks"]["self_retrieval_rank1"] = f"{sum(self_ok)}/{len(self_ok)}"
    log["checks"]["filter_year_respected"] = all(filter_ok)
    try:
        store.search("B", vectors[0], filters={"text; DROP TABLE chunks": 1})
        log["checks"]["unknown_filter_rejected"] = False
    except ValueError:
        log["checks"]["unknown_filter_rejected"] = True

    with store.connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT chunk_set, year, count(*) FROM chunks GROUP BY 1, 2 ORDER BY 1, 2")
        log["rows_by_set_and_year"] = [{"chunk_set": s, "year": y, "rows": n} for s, y, n in cur.fetchall()]
    log["strategies"] = {k: {"chunk_set": v["chunks_from"], "filter": v["use_filter"]} for k, v in config.items()}
    (STARTER / "results/store_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print("checks:", log["checks"])
    print("rows:", log["rows_by_set_and_year"])
    failed = [k for k, v in log["checks"].items() if v is False or (isinstance(v, str) and v.split("/")[0] != v.split("/")[1])]
    if failed:
        raise SystemExit(f"FAILED checks: {failed}")


if __name__ == "__main__":
    main()
