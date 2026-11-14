"""Embed the A and B chunk sets and the benchmark questions with the same model.

Run from starter/:  python -X utf8 scripts/embed_chunks.py
Outputs:
  data/vectors/<strategy>.npz   chunk_ids + float32 vectors (not committed; rebuildable)
  data/vectors/queries.npz      question ids + query vectors
  results/embedding_log.json    model, revision, dimensions, timing, truncation, cost

Vectors are cached: a chunk set is re-embedded only when its chunk ids or the model
change. Embedding only encodes text; it computes no similarity against the benchmark.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

STARTER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STARTER))
load_dotenv(STARTER / ".env")

from src.embeddings import QUERY_PREFIX, MyEmbedder  # noqa: E402


def fingerprint(model: str, ids: list[str]) -> str:
    return hashlib.sha1((model + "|" + "|".join(ids)).encode("utf-8")).hexdigest()


def main() -> None:
    config = json.loads((STARTER / "configs/strategies.json").read_text(encoding="utf-8"))
    out_dir = STARTER / "data/vectors"
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    embedder = MyEmbedder()
    load_seconds = time.perf_counter() - started
    info = embedder.describe()
    print(f"model {info['model']} rev {info['revision']} dims {info['dimensions']} "
          f"device {info['device']} (load {load_seconds:.1f}s)", flush=True)

    log: dict = {"embedder": info, "model_load_seconds": round(load_seconds, 1), "sets": {}}
    for name in sorted({c["chunks_from"] for c in config.values()}):
        rows = [json.loads(l) for l in (STARTER / f"data/chunks/{name}.jsonl").read_text(encoding="utf-8").splitlines()]
        ids, texts = [r["chunk_id"] for r in rows], [r["text"] for r in rows]
        fp = fingerprint(info["model"], ids)
        path = out_dir / f"{name}.npz"
        if path.exists() and str(np.load(path)["fingerprint"]) == fp:
            print(f"{name}: cached ({len(ids)} vectors)")
            log["sets"][name] = json.loads((STARTER / "results/embedding_log.json").read_text(encoding="utf-8"))["sets"][name]
            continue
        lengths = embedder.token_lengths(texts)
        t0 = time.perf_counter()
        vectors = np.asarray(embedder.embed_documents(texts), dtype=np.float32)
        seconds = time.perf_counter() - t0
        np.savez(path, chunk_ids=np.array(ids), vectors=vectors, fingerprint=np.array(fp))
        norms = np.linalg.norm(vectors, axis=1)
        log["sets"][name] = {
            "chunks": len(ids), "seconds": round(seconds, 1),
            "chunks_per_second": round(len(ids) / seconds, 1),
            "tokens_max": max(lengths), "tokens_median": int(np.median(lengths)),
            "truncated_chunks": sum(1 for n in lengths if n > embedder.max_seq_length),
            "norm_min": round(float(norms.min()), 5), "norm_max": round(float(norms.max()), 5),
            "fingerprint": fp,
        }
        print(f"{name}: {len(ids)} vectors in {seconds:.1f}s, tokens max {max(lengths)}, "
              f"truncated {log['sets'][name]['truncated_chunks']}", flush=True)

    questions = json.loads((STARTER.parent / "benchmark/questions.json").read_text(encoding="utf-8"))["questions"]
    t0 = time.perf_counter()
    qvecs = np.asarray([embedder.embed_query(q["question"]) for q in questions], dtype=np.float32)
    np.savez(out_dir / "queries.npz", question_ids=np.array([q["id"] for q in questions]), vectors=qvecs)
    log["queries"] = {"count": len(questions), "seconds": round(time.perf_counter() - t0, 2),
                      "prefix": QUERY_PREFIX,
                      "tokens_max": max(embedder.token_lengths([q["question"] for q in questions], QUERY_PREFIX))}

    # determinism check: re-encoding the same query gives the same vector
    again = np.asarray(embedder.embed_query(questions[0]["question"]), dtype=np.float32)
    log["determinism_max_abs_diff"] = float(np.abs(again - qvecs[0]).max())
    (STARTER / "results/embedding_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"queries: {len(questions)} vectors; determinism diff {log['determinism_max_abs_diff']:.2e}")


if __name__ == "__main__":
    main()
