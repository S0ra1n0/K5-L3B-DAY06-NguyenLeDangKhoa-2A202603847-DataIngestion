"""Build the cleaned page-level corpus, the data manifest and the ingestion log.

Run from starter/:  python -m scripts.build_corpus
Outputs:
  data/ocr/<doc>.ocr.json        raw OCR cache (slow step, reused when unchanged)
  data/processed/pages.jsonl     one cleaned page per line with traceable metadata
  data/manifest.json             sources, permission, page counts and counting rule
  results/ingestion_log.json     empty/low-confidence pages, repairs, structure checks
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(STARTER))

from src.ingestion import (  # noqa: E402
    MIN_CONTENT_CHARS, MIN_TEXT_LAYER_CHARS, RE_EFFECTIVE, load_pdf,
)

ACCESSED_AT = "2026-11-14"
PERMISSION = (
    "Văn bản quy phạm pháp luật: không thuộc phạm vi bảo hộ quyền tác giả theo khoản 2 "
    "Điều 15 Luật Sở hữu trí tuệ 2005 (sửa đổi, bổ sung). Tải từ cổng thông tin chính thức."
)

# Values below are copied from the official listing pages (source_page_url) on ACCESSED_AT,
# not inferred. effective_date is additionally checked against the OCR text below.
DOCUMENTS = [
    {
        "source_id": "blld-2012",
        "title": "Bộ luật Lao động (Luật số 10/2012/QH13)",
        "law_number": "10/2012/QH13",
        "year": 2012,
        "issuer": "Quốc hội",
        "issued_date": "2012-06-18",
        "effective_date": "2013-05-01",
        "status_note": "Hết hiệu lực từ 2021-01-01, thay thế bởi Luật số 45/2019/QH14.",
        "path": "data/raw/blld_2012_10-2012-QH13.pdf",
        "source_page_url": "https://moit.gov.vn/van-ban-phap-luat/van-ban-phap-quy/-bo-luat-lao-dong.html",
        "file_url": "https://moit.gov.vn/upload/2005517/20210623/_CB99Ad01.pdf",
        "publisher": "Cổng TTĐT Bộ Công Thương (moit.gov.vn)",
        "notes": "Bản scan; ảnh có watermark LuatVietnam, lớp text chỉ chứa 'www.LuatVietnam.vn'. "
                 "Watermark bị loại khi làm sạch.",
    },
    {
        "source_id": "blld-2019",
        "title": "Bộ luật Lao động (Luật số 45/2019/QH14)",
        "law_number": "45/2019/QH14",
        "year": 2019,
        "issuer": "Quốc hội",
        "issued_date": "2019-11-20",
        "effective_date": "2021-01-01",
        "status_note": "Văn bản gốc khi ban hành; không gồm các sửa đổi/văn bản hợp nhất về sau.",
        "path": "data/raw/blld_2019_45-2019-QH14.pdf",
        "source_page_url": "https://vanban.chinhphu.vn/?pageid=27160&docid=198540",
        "file_url": "https://datafiles.chinhphu.vn/cpp/files/vbpq/2019/12/45.signed.pdf",
        "publisher": "Hệ thống văn bản Chính phủ (vanban.chinhphu.vn)",
        "notes": "Bản scan có chữ ký số; không có lớp text.",
    },
]



def main() -> None:
    out_pages = STARTER / "data/processed/pages.jsonl"
    out_pages.parent.mkdir(parents=True, exist_ok=True)
    (STARTER / "results").mkdir(exist_ok=True)

    manifest_docs, log_docs, all_pages = [], [], []
    for doc in DOCUMENTS:
        print(f"[{doc['source_id']}] reading {doc['path']}", flush=True)
        doc_meta = {"year": doc["year"], "law_number": doc["law_number"],
                    "document_type": "bo_luat", "language": "vi"}
        pages, report = load_pdf(STARTER / doc["path"], doc["source_id"], doc["path"],
                                 STARTER / "data/ocr", doc_meta)
        all_pages.extend(pages)

        content = [p for p in pages if p.metadata["is_content_page"]]
        excluded = [p for p in pages if not p.metadata["is_content_page"]]
        effective_hits = []
        for p in pages:
            for m in RE_EFFECTIVE.finditer(p.text.replace("\n", " ")):
                effective_hits.append({"page": p.page, "date": f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"})
        manifest_docs.append({
            "source_id": doc["source_id"],
            "title": doc["title"],
            "law_number": doc["law_number"],
            "year": doc["year"],
            "issuer": doc["issuer"],
            "issued_date": doc["issued_date"],
            "effective_date": doc["effective_date"],
            "effective_date_in_text": effective_hits,
            "status_note": doc["status_note"],
            "source_path_or_url": doc["path"],
            "source_page_url": doc["source_page_url"],
            "file_url": doc["file_url"],
            "publisher": doc["publisher"],
            "license_or_permission": PERMISSION,
            "accessed_at": ACCESSED_AT,
            "sha256": report["pdf_sha256"],
            "physical_pages": len(pages),
            "content_pages": [p.page for p in content],
            "content_page_count": len(content),
            "excluded_pages": [{"page": p.page, "chars": p.metadata["char_count"]} for p in excluded],
            "content_chars": sum(p.metadata["char_count"] for p in content),
            "notes": doc["notes"],
        })
        log_docs.append({
            **report,
            "pages_without_text_layer": sum(1 for p in pages if p.metadata["text_layer_chars"] < MIN_TEXT_LAYER_CHARS),
            "empty_pages_after_ocr": [p.page for p in pages if p.metadata["char_count"] == 0],
            "lowest_conf_pages": sorted(
                ({"page": p.page, "mean_conf": p.metadata["ocr_mean_conf"],
                  "low_conf_words": p.metadata["ocr_low_conf_words"]} for p in pages),
                key=lambda r: (r["mean_conf"] is not None, r["mean_conf"] or 0))[:10],
            "cleaning_issue_counts": _count([i for p in pages for i in p.metadata["cleaning_issues"]]),
            "pages": [{"page": p.page, **{k: p.metadata[k] for k in (
                "char_count", "is_content_page", "text_layer_chars", "ocr_mean_conf",
                "ocr_low_conf_words", "chapters_on_page", "articles_on_page", "cleaning_issues")}}
                for p in pages],
        })

    with open(out_pages, "w", encoding="utf-8") as handle:
        for page in all_pages:
            handle.write(json.dumps(asdict(page), ensure_ascii=False) + "\n")

    manifest = {
        "corpus": "Bộ luật Lao động Việt Nam — bản 2012 và bản 2019",
        "counting_rule": (
            f"Đếm theo trang PDF vật lý (1-based). Trang được tính là trang nội dung khi văn bản "
            f"sau OCR + làm sạch có >= {MIN_CONTENT_CHARS} ký tự (NFC). Trang ngắn hơn (vd. trang "
            f"chỉ có chữ ký) bị loại và liệt kê trong excluded_pages. Hai văn bản không có bìa, "
            f"mục lục hay trang tài liệu tham khảo."),
        "page_id_format": "<source_id>#p<page>, vd. blld-2019#p6",
        "filter_fields": {"year": "int, lấy từ số hiệu văn bản trong manifest (2012 | 2019)"},
        "total_physical_pages": sum(d["physical_pages"] for d in manifest_docs),
        "total_content_pages": sum(d["content_page_count"] for d in manifest_docs),
        "total_content_chars": sum(d["content_chars"] for d in manifest_docs),
        "documents": manifest_docs,
    }
    (STARTER / "data/manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (STARTER / "results/ingestion_log.json").write_text(
        json.dumps({"documents": log_docs}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"pages={len(all_pages)} content={manifest['total_content_pages']} "
          f"chars={manifest['total_content_chars']}")
    for d, l in zip(manifest_docs, log_docs):
        print(f"  {d['source_id']}: physical={d['physical_pages']} content={d['content_page_count']} "
              f"excluded={d['excluded_pages']} effective_in_text={d['effective_date_in_text']}")
        print(f"    issues={l['cleaning_issue_counts']}")
        for line in l["structure_log"]:
            print(f"    {line}")


def _count(items: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        out[item] = out.get(item, 0) + 1
    return dict(sorted(out.items()))


if __name__ == "__main__":
    main()
