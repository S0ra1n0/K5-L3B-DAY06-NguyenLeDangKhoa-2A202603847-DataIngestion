"""OCR sample verification: error rate of the cleaned OCR text on hand-checked pages.

Run from starter/:  python -X utf8 scripts/ocr_sample_check.py
Reads data/ocr_sample/corrections.json (every difference found by comparing the page
image with the cleaned text), builds the reference text by applying the corrections,
and reports word error rate (WER) and character error rate (CER) of the cleaned OCR
text against it. Writes results/ocr_sample_check.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]


def levenshtein(a: list | str, b: list | str) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, start=1):
        cur = [i]
        for j, y in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def main() -> None:
    spec = json.loads((STARTER / "data/ocr_sample/corrections.json").read_text(encoding="utf-8"))
    pages = {f"{r['document_id']}#p{r['page']}": r["text"] for r in map(
        json.loads, (STARTER / "data/processed/pages.jsonl").read_text(encoding="utf-8").splitlines())}
    report, total = {}, {"words": 0, "word_errors": 0, "chars": 0, "char_errors": 0}
    for page_id, corrections in spec["pages"].items():
        hyp = pages[page_id]
        ref = hyp
        for wrong, right in corrections:
            if wrong not in ref:
                sys.exit(f"{page_id}: correction not found in text: {wrong!r}")
            ref = ref.replace(wrong, right, 1)
        hyp_w, ref_w = hyp.split(), ref.split()
        hyp_c, ref_c = " ".join(hyp_w), " ".join(ref_w)
        we, ce = levenshtein(hyp_w, ref_w), levenshtein(hyp_c, ref_c)
        report[page_id] = {"words": len(ref_w), "word_errors": we, "wer": round(we / len(ref_w), 4),
                           "chars": len(ref_c), "char_errors": ce, "cer": round(ce / len(ref_c), 4),
                           "corrections": len(corrections)}
        for k, v in (("words", len(ref_w)), ("word_errors", we), ("chars", len(ref_c)), ("char_errors", ce)):
            total[k] += v
        print(f"{page_id}: WER {we}/{len(ref_w)} = {we / len(ref_w):.1%}, CER {ce}/{len(ref_c)} = {ce / len(ref_c):.1%}")
    total["wer"] = round(total["word_errors"] / total["words"], 4)
    total["cer"] = round(total["char_errors"] / total["chars"], 4)
    print(f"total: WER {total['wer']:.1%}, CER {total['cer']:.1%}")
    out = {"method": spec["method"], "checked_by": spec["checked_by"], "pages": report, "total": total}
    (STARTER / "results/ocr_sample_check.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
