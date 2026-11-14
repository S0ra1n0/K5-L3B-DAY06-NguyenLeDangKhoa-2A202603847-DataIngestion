"""Aggregate the manual audit CSVs into the numbers the report needs.

Run from starter/:  python -X utf8 scripts/summarize_audit.py
Reads results/audit/{coherence,metadata,grounding}.csv and results/metrics_test.json,
writes results/audit/audit_summary.json and prints a markdown table.

Reviewer overrides: in column `student_review`, leave empty or write "ok" to accept the
draft label; write a number to replace it (coherence/grounding: 0, 1 or 2;
metadata: 1 = complete and correct, 0 = not). Anything else is reported as a comment.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
AUDIT = STARTER / "results/audit"


def read(name: str) -> list[dict]:
    with open(AUDIT / name, encoding="utf-8") as handle:
        # spreadsheet-style editors may append an empty row; it is not a label
        return [r for r in csv.DictReader(handle) if (r.get("strategy") or "").strip()]


def final(row: dict, field: str, allowed: set[int]) -> tuple[int, bool]:
    review = (row.get("student_review") or "").strip()
    if review.lstrip("-").isdigit() and int(review) in allowed:
        return int(review), int(review) != int(row[field])
    return int(row[field]), False


def main() -> None:
    coherence, metadata, grounding = read("coherence.csv"), read("metadata.csv"), read("grounding.csv")
    test = json.loads((STARTER / "results/metrics_test.json").read_text(encoding="utf-8"))["strategies"]
    reviewed = all((r.get("student_review") or "").strip() for r in coherence + metadata + grounding)
    summary = {"all_rows_reviewed_by_student": reviewed, "strategies": {}}
    for s in "ABC":
        coh = [final(r, "score_0_2", {0, 1, 2}) for r in coherence if r["strategy"] == s]
        meta = [final(r, "complete_and_correct", {0, 1}) for r in metadata if r["strategy"] == s]
        gro = [final(r, "score_0_2", {0, 1, 2}) for r in grounding if r["strategy"] == s]
        fc = test[s]["test"]["filter_compliance_top3"]
        g_scores = [v for v, _ in gro]
        summary["strategies"][s] = {
            "coherence_mean": round(sum(v for v, _ in coh) / len(coh), 2), "coherence_n": len(coh),
            "coherence_counts": {k: sum(1 for v, _ in coh if v == k) for k in (0, 1, 2)},
            "metadata_complete_correct": f"{sum(v for v, _ in meta)}/{len(meta)}",
            "filter_compliance_test": f"{fc['n']}/{fc['N']}" if isinstance(fc, dict) else fc,
            "grounding_counts": {k: g_scores.count(k) for k in (0, 1, 2)},
            "grounding_mean": round(sum(g_scores) / len(g_scores), 2), "grounding_n": len(g_scores),
            "labels_changed_by_student": sum(changed for _, changed in coh + meta + gro),
        }
    (AUDIT / "audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("| Strategy | Coherence TB /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (test) | Grounding 0/1/2 và TB /2 |")
    print("|---|---|---|---|---|")
    for s, m in summary["strategies"].items():
        g = m["grounding_counts"]
        print(f"| {s} | {m['coherence_mean']:.2f} ({m['coherence_n']}) | {m['metadata_complete_correct']} | "
              f"{m['filter_compliance_test']} | {g[0]}/{g[1]}/{g[2]}, TB {m['grounding_mean']:.2f} |")
    print("all rows reviewed by student:", reviewed)


if __name__ == "__main__":
    main()
