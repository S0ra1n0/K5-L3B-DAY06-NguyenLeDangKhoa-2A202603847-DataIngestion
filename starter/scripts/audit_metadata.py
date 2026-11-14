"""Metadata audit of the test top-3 records (5 questions x 3 per strategy).

Run from starter/:  python -X utf8 scripts/audit_metadata.py
Writes results/audit/metadata.csv (one row per retrieved record). Each field is checked
against the cleaned source pages and the manifest:

  source_ok   chunk.source == manifest path of its document
  pages_ok    every content line of the chunk occurs on one of the chunk's `pages`
              (a heading repeated at the top of a split-article part is exempt: it is
              a copy of the line on the article's first page)
  year_ok     chunk.year == manifest year of its document
  article_ok  the chunk's content belongs to exactly the article in `article`;
              a fixed window that also contains another article's heading is NOT ok,
              because the single `article` value then hides part of the content
  chapter_ok  `chapter` is the chapter in force for that article

complete_and_correct = all five checks pass. Rows can be overridden by the reviewer in
the CSV (column student_review); scripts/summarize_audit.py recomputes the totals.
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
RE_HEAD = re.compile(r"^Điều (\d+)\. ")


def squash(text: str) -> str:
    return " ".join(text.split())


def main() -> None:
    pages = {(r["document_id"], r["page"]): r for r in map(
        json.loads, (STARTER / "data/processed/pages.jsonl").read_text(encoding="utf-8").splitlines())}
    manifest = {d["source_id"]: d for d in json.loads(
        (STARTER / "data/manifest.json").read_text(encoding="utf-8"))["documents"]}

    # chapter in force for each (document, article), from validated page structure
    chapter_of: dict[tuple[str, int], str] = {}
    for (doc, _), page in sorted(pages.items()):
        chapter = page["metadata"]["chapter_at_start"]
        valid = list(page["metadata"]["articles_on_page"])
        for line in page["text"].split("\n"):
            if m := re.match(r"^Chương ([IVXLC]+)$", line):
                chapter = m.group(1)
            elif (m := RE_HEAD.match(line)) and valid and int(m.group(1)) == valid[0]:
                chapter_of[(doc, valid.pop(0))] = chapter

    rows = []
    for strategy in "ABC":
        for line in (STARTER / f"results/traces/{strategy}_test.jsonl").read_text(encoding="utf-8").splitlines():
            trace = json.loads(line)
            for hit in trace["top_k"]:
                doc, chunk_pages, text = hit["document_id"], hit["pages"], hit["text"]
                page_text = squash(" ".join(pages[(doc, p)]["text"] for p in chunk_pages))
                valid_heads = {a for p in chunk_pages for a in pages[(doc, p)]["metadata"]["articles_on_page"]}
                lines = [l for l in text.split("\n") if l.strip()]
                content = [l for i, l in enumerate(lines)
                           if not (i == 0 and RE_HEAD.match(l) and int(RE_HEAD.match(l).group(1)) == hit["article"]
                                   and squash(l) not in page_text)]
                pages_ok = all(squash(l) in page_text for l in content)
                heads = [int(m.group(1)) for l in lines if (m := RE_HEAD.match(l))
                         and int(m.group(1)) in valid_heads | {hit["article"]}]
                other = sorted({a for a in heads if a != hit["article"]})
                article_ok = not other
                chapter_ok = chapter_of.get((doc, hit["article"])) == hit["chapter"]
                checks = {
                    "source_ok": hit["source"] == manifest[doc]["source_path_or_url"],
                    "pages_ok": pages_ok,
                    "year_ok": hit["year"] == manifest[doc]["year"],
                    "article_ok": article_ok,
                    "chapter_ok": chapter_ok,
                }
                note = []
                if other:
                    note.append(f"chunk also contains Điều {', '.join(map(str, other))} "
                                f"but metadata says Điều {hit['article']} only")
                if len(lines) != len(content):
                    note.append("repeated article heading (copied from first page of the article)")
                if hit["hit"]:
                    note.append("evidence hit")
                rows.append({
                    "strategy": strategy, "question_id": trace["id"], "rank": hit["rank"],
                    "chunk_id": hit["chunk_id"], "document_id": doc, "pages": " ".join(map(str, chunk_pages)),
                    "year": hit["year"], "chapter": hit["chapter"], "article": hit["article"],
                    **{k: int(v) for k, v in checks.items()},
                    "complete_and_correct": int(all(checks.values())),
                    "note": "; ".join(note),
                    "labeler": "auto-check + Claude review (draft)", "student_review": "",
                })
    out = STARTER / "results/audit/metadata.csv"
    with open(out, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for s in "ABC":
        sub = [r for r in rows if r["strategy"] == s]
        print(f"{s}: complete_and_correct {sum(r['complete_and_correct'] for r in sub)}/{len(sub)}; "
              f"fails: {[(r['question_id'], r['rank'], r['note']) for r in sub if not r['complete_and_correct']]}")


if __name__ == "__main__":
    main()
