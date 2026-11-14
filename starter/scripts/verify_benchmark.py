"""Verify benchmark/questions.json against the cleaned corpus BEFORE any retrieval run.

Run from starter/:  python -X utf8 scripts/verify_benchmark.py
Checks: >=20 questions, >=15 dev / >=5 test, >=3 filter questions with >=1 in test,
unique ids, every evidence quote is an exact substring of its gold page, the gold
article really is on that page, every gold satisfies the question's filter, and the
filter value is stated in the question (user-provided, not taken from the gold).
Writes results/benchmark_verification.json; exits 1 if any check fails.
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
BENCHMARK = STARTER.parent / "benchmark/questions.json"
PAGES = STARTER / "data/processed/pages.jsonl"


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def main() -> int:
    pages = {}
    for line in PAGES.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        pages[(row["document_id"], row["page"])] = row
    questions = json.loads(BENCHMARK.read_text(encoding="utf-8"))["questions"]

    errors: list[str] = []
    report = []
    ids = [q["id"] for q in questions]
    if len(ids) != len(set(ids)):
        errors.append("duplicate question ids")
    for q in questions:
        golds = [{"source_id": q["gold_source_id"], "page": q["gold_page"],
                  "article": q.get("gold_article"), "evidence_quote": q["evidence_quote"]}]
        golds += q.get("alternative_gold", [])
        checks = []
        for gold in golds:
            key = (gold["source_id"], gold["page"])
            page = pages.get(key)
            if page is None:
                errors.append(f"{q['id']}: gold page {key} not in corpus")
                continue
            text = nfc(page["text"]).replace("\n", " ")
            meta = page["metadata"]
            quotes_ok = []
            for quote in gold["evidence_quote"]:
                found = nfc(quote) in text
                elsewhere = [f"{d}#p{p}" for (d, p), r in pages.items()
                             if (d, p) != key and nfc(quote) in nfc(r["text"]).replace("\n", " ")]
                quotes_ok.append({"quote": quote, "on_gold_page": found, "also_on": elsewhere})
                if not found:
                    errors.append(f"{q['id']}: quote not on {key[0]}#p{key[1]}: {quote[:60]}...")
            article = gold.get("article")
            covering = set(meta["articles_on_page"]) | ({meta["article_at_start"]} - {None})
            if article is not None and article not in covering:
                errors.append(f"{q['id']}: Điều {article} not on {key[0]}#p{key[1]} (page covers {sorted(covering)})")
            if q["filter"]:
                for field, value in q["filter"].items():
                    if meta.get(field) != value:
                        errors.append(f"{q['id']}: gold {key} has {field}={meta.get(field)}, filter wants {value}")
                    if str(value) not in q["question"]:
                        errors.append(f"{q['id']}: filter {field}={value} is not stated in the question")
            checks.append({"gold": f"{key[0]}#p{key[1]}", "article": article, "quotes": quotes_ok})
        report.append({"id": q["id"], "split": q["split"], "type": q["type"],
                       "filter": q["filter"], "golds": checks})

    dev = [q for q in questions if q["split"] == "dev"]
    test = [q for q in questions if q["split"] == "test"]
    filtered = [q for q in questions if q["filter"]]
    summary = {
        "total": len(questions), "dev": len(dev), "test": len(test),
        "filter_questions": len(filtered),
        "filter_questions_test": sum(1 for q in filtered if q["split"] == "test"),
        "types": {t: sum(1 for q in questions if q["type"] == t) for t in sorted({q["type"] for q in questions})},
        "quotes_checked": sum(len(g["quotes"]) for r in report for g in r["golds"]),
    }
    if summary["total"] < 20 or summary["dev"] < 15 or summary["test"] < 5:
        errors.append(f"split too small: {summary}")
    if summary["filter_questions"] < 3 or summary["filter_questions_test"] < 1:
        errors.append("need >=3 filter questions with >=1 in test")

    out = STARTER / "results/benchmark_verification.json"
    out.write_text(json.dumps({"summary": summary, "errors": errors, "questions": report},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    for r in report:
        for g in r["golds"]:
            dup = [q["also_on"] for q in g["quotes"] if q["also_on"]]
            if dup:
                print(f"  note {r['id']} {g['gold']}: quote also appears on {dup}")
    for e in errors:
        print("ERROR", e)
    print("OK" if not errors else f"{len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
