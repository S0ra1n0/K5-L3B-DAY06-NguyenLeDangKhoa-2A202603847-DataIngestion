"""Read, OCR and normalize the Labor Code PDFs (Bộ luật Lao động 2012 và 2019).

Both official PDFs are image scans with no usable text layer, so each physical
page is rendered and OCR'd with Tesseract (`vie`, tessdata_best). Raw OCR output
is cached per document (keyed by the PDF's SHA-256 and the OCR settings) so the
slow step runs once and the cleaning rules can be re-run and audited.

Nothing here silently falls back: a page with no text is kept and logged as
empty, and every cleaning repair is recorded in the page's `issues` list.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

from .models import DocumentPage

STARTER_DIR = Path(__file__).resolve().parents[1]
TESSERACT_CMD = os.getenv("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
TESSDATA_DIR = Path(os.getenv("TESSDATA_PREFIX", STARTER_DIR / "tessdata"))
OCR_LANG = "vie"
OCR_DPI = 300
OCR_CONFIG = "--oem 1 --psm 4"
LOW_CONF = 60            # word confidence below this is counted as "low confidence"
MIN_TEXT_LAYER_CHARS = 200  # fewer chars than this per page => treat page as image-only
MIN_CONTENT_CHARS = 300  # cleaned page shorter than this is not counted as a content page


# --------------------------------------------------------------------------- PDF reading

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def text_layer_chars(path: Path) -> list[int]:
    """Characters per page in the PDF's own text layer (to prove OCR is needed)."""
    from pypdf import PdfReader

    return [len((page.extract_text() or "").strip()) for page in PdfReader(path).pages]


def _ocr_settings() -> dict[str, Any]:
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    os.environ["TESSDATA_PREFIX"] = str(TESSDATA_DIR)
    return {
        "engine": f"tesseract {pytesseract.get_tesseract_version()}",
        "lang": OCR_LANG,
        "traineddata": "tessdata_best/vie.traineddata",
        "traineddata_sha256": sha256_file(TESSDATA_DIR / f"{OCR_LANG}.traineddata"),
        "dpi": OCR_DPI,
        "config": OCR_CONFIG,
    }


def _rebuild_lines(data: dict[str, list]) -> tuple[str, list[float]]:
    """Rebuild text from image_to_data, one output line per Tesseract line.

    A blank line separates Tesseract paragraphs/blocks so later steps can use them.
    """
    lines: list[str] = []
    confs: list[float] = []
    current_key = None
    current_par = None
    words: list[str] = []
    for i, word in enumerate(data["text"]):
        if int(data["level"][i]) != 5:
            continue
        word = word.strip()
        if not word:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        par = key[:2]
        if key != current_key:
            if words:
                lines.append(" ".join(words))
            if current_par is not None and par != current_par:
                lines.append("")
            words, current_key, current_par = [], key, par
        words.append(word)
        conf = float(data["conf"][i])
        if conf >= 0:
            confs.append(conf)
    if words:
        lines.append(" ".join(words))
    return "\n".join(lines), confs


def ocr_pdf(path: Path, cache_path: Path) -> dict[str, Any]:
    """OCR every physical page; reuse the cache when PDF hash and settings match."""
    import pypdfium2 as pdfium
    import pytesseract

    settings = _ocr_settings()
    pdf_hash = sha256_file(path)
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("pdf_sha256") == pdf_hash and cached.get("settings") == settings:
            return cached

    pdf = pdfium.PdfDocument(str(path))
    pages = []
    for index in range(len(pdf)):
        started = time.perf_counter()
        image = pdf[index].render(scale=OCR_DPI / 72).to_pil().convert("L")
        data = pytesseract.image_to_data(
            image, lang=OCR_LANG, config=OCR_CONFIG, output_type=pytesseract.Output.DICT
        )
        text, confs = _rebuild_lines(data)
        pages.append({
            "page": index + 1,
            "text": text,
            "word_count": len(confs),
            "mean_conf": round(sum(confs) / len(confs), 2) if confs else None,
            "low_conf_words": sum(1 for c in confs if c < LOW_CONF),
            "seconds": round(time.perf_counter() - started, 2),
        })
        print(f"  OCR {path.name} p{index + 1}/{len(pdf)} "
              f"conf={pages[-1]['mean_conf']} {pages[-1]['seconds']}s", flush=True)
    result = {"pdf": path.name, "pdf_sha256": pdf_hash, "settings": settings, "pages": pages}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


# --------------------------------------------------------------------------- normalization

_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)
_SPACES = re.compile(r"[ \t\u00a0\u2000-\u200a\u202f\u3000]+")


def normalize_text(text: str) -> str:
    """NFC Unicode, unify spaces, trim lines; keep line breaks (structure) intact."""
    text = unicodedata.normalize("NFC", text).translate(_INVISIBLE)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# --------------------------------------------------------------------------- OCR cleaning

ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
# OCR often reads roman "II" as "H" ("XVH" = XVII) and "I" as "l"/"1"; accept these and
# normalize them in roman_to_int, the sequence check below then confirms the value.
RE_CHUONG = re.compile(r"^(?:CHƯƠNG|Chương)\s+([IVXLCHl1]+)\s*$|^(?:CHƯƠNG|Chương)\s+([IVXLCHl1]+)\b")
RE_MUC = re.compile(r"^Mục\s+(\d+)\b")
# OCR variants seen: "Điêu 138.", "Điệu 238.", "Điều 48, Trách nhiệm...", 'Điều 183. "Quyền...'
RE_DIEU = re.compile(r"^Đi[eêềệểễéẻẽ]u\s+(\d+)\s*[.,]\s*[“”\"'„]*\s*(\S.*)$")
RE_KHOAN = re.compile(r"^\d{1,2}\.\s")
RE_KHOAN_OCR = re.compile(r"^(?:[lIÌÍ|]|(\d{1,2}))[.,]\s")   # "l." / "Ì." / "3," for khoản "1." / "3."


def match_dieu(line: str) -> re.Match | None:
    """Article heading, but not a cross-reference such as "Điều 18, điểm a khoản 1"."""
    m = RE_DIEU.match(line)
    return m if m and m.group(2)[:1].isupper() else None


RE_DIEM = re.compile(r"^[a-zđ]\)\s")
RE_PAGE_NO = re.compile(r"^[\W_]*\d{1,3}[\W_]*$")
RE_WATERMARK = re.compile(r"luat\s*vietnam|vanbanluat|www\.", re.IGNORECASE)
RE_LEAD_NOISE = re.compile(r"^[.,:;„“”\"'`~_|•·*]+\s*")
RE_GARBAGE_PREFIX = re.compile(
    r"^(\S{1,4})\s+(?=(?:Điều\s+\d+\s*\.|CHƯƠNG\s+[IVXLC]+\b|Chương\s+[IVXLC]+\b|Mục\s+\d+\b))"
)
RE_TRAIL_NOISE = re.compile(r"\s+[.,:;!„“”\"'`~_|•·*]+$")
RE_EFFECTIVE = re.compile(r"có hiệu lực.{0,15}?từ ngày (\d{1,2}) tháng (\d{1,2}) năm (\d{4})")


def _chapter_token(match: re.Match) -> str:
    return match.group(1) or match.group(2)


def roman_to_int(value: str) -> int | None:
    value = value.replace("H", "II").replace("l", "I").replace("1", "I").upper()
    if not value or any(ch not in ROMAN for ch in value):
        return None
    total = 0
    for i, ch in enumerate(value):
        nxt = ROMAN[value[i + 1]] if i + 1 < len(value) else 0
        total += -ROMAN[ch] if ROMAN[ch] < nxt else ROMAN[ch]
    return total


def int_to_roman(value: int) -> str:
    out = ""
    for number, letters in ((100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"),
                            (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while value >= number:
            out, value = out + letters, value - number
    return out


def _letters(line: str) -> str:
    return "".join(ch for ch in line if ch.isalpha())


def _is_upper_line(line: str) -> bool:
    letters = _letters(line)
    return len(letters) >= 4 and sum(ch.isupper() for ch in letters) / len(letters) > 0.8


def _is_heading(line: str) -> bool:
    return bool(RE_CHUONG.match(line) or RE_MUC.match(line) or match_dieu(line)) or _is_upper_line(line)


def _starts_block(line: str) -> bool:
    return bool(RE_CHUONG.match(line) or RE_MUC.match(line) or match_dieu(line)
                or RE_KHOAN.match(line) or RE_DIEM.match(line))


def clean_ocr_page(raw: str) -> tuple[str, list[str]]:
    """Remove OCR noise and re-flow wrapped lines into paragraphs.

    Returns the cleaned text (one paragraph per line) and a list of issue codes.
    Words are never "spell-corrected": wrong diacritics stay as OCR produced
    them, so evidence quotes must be taken from this cleaned text.
    """
    issues: list[str] = []
    kept: list[str] = []
    for line in normalize_text(raw).split("\n"):
        if not line:
            kept.append("")
            continue
        if RE_PAGE_NO.match(line):
            issues.append("drop_page_number")
            continue
        if RE_WATERMARK.search(line):
            issues.append("drop_watermark")
            continue
        if not any(ch.isalnum() for ch in line):
            issues.append("drop_symbol_line")
            continue
        fixed = RE_LEAD_NOISE.sub("", line)
        match = RE_GARBAGE_PREFIX.match(fixed)
        if match and not match.group(1).isalnum():
            fixed = fixed[match.end():]
        fixed = RE_TRAIL_NOISE.sub("", fixed)
        if ((km := RE_KHOAN_OCR.match(fixed)) and not RE_KHOAN.match(fixed)
                and fixed[km.end():km.end() + 1].isupper()):
            fixed = f"{km.group(1) or '1'}. " + fixed[km.end():]
            issues.append("fix_khoan_number")
        if fixed != line:
            issues.append("strip_noise")
        if len(_letters(fixed)) < 2 and not RE_KHOAN.match(fixed + " "):
            issues.append("drop_short_noise")
            continue
        kept.append(fixed)

    paragraphs: list[str] = []
    prev = ""
    for line in kept:
        if not line:
            continue
        new_para = (
            not paragraphs
            or _starts_block(line)
            or bool(RE_CHUONG.match(prev) or RE_MUC.match(prev))
            # an article title that wraps continues on a lowercase line
            or (bool(match_dieu(prev)) and not line[0].islower())
            or _is_upper_line(line) != _is_upper_line(prev)
            or (line[0].isupper() and prev.rstrip().endswith((".", ";", ":", "!", "?")))
        )
        if new_para:
            paragraphs.append(line)
        else:
            joined = paragraphs[-1]
            # re-join a word hyphenated across lines ("lao-\nđộng" is not used in VN law text)
            paragraphs[-1] = joined[:-1] + line if joined.endswith("-") else f"{joined} {line}"
        prev = line
    return "\n".join(paragraphs), issues


# --------------------------------------------------------------------------- structure

def find_structure(text: str) -> dict[str, list]:
    """Chapter (roman), section and article-heading numbers found on this page (raw)."""
    chapters, sections, articles = [], [], []
    for line in text.split("\n"):
        if m := RE_CHUONG.match(line):
            chapters.append(_chapter_token(m))
        elif m := RE_MUC.match(line):
            sections.append(int(m.group(1)))
        elif m := match_dieu(line):
            articles.append(int(m.group(1)))
    return {"chapters": chapters, "sections": sections, "articles": articles}


def _looks_like_misread(read: int, expected: int) -> bool:
    """One wrong/extra/missing digit, e.g. 90 for 80 or 1109 for 110."""
    r, e = str(read), str(expected)
    if len(r) == len(e):
        return sum(a != b for a, b in zip(r, e)) == 1
    if len(r) == len(e) + 1:
        return r.startswith(e) or any(r[:i] + r[i + 1:] == e for i in range(len(r)))
    if len(r) + 1 == len(e):
        return any(e[:i] + e[i + 1:] == r for i in range(len(e)))
    return False


ARTICLE_WINDOW = 3  # accept a heading up to 2 articles ahead (heading lost in OCR)


def repair_structure(pages: list[dict[str, Any]]) -> list[str]:
    """Check chapter/article numbering across a document; fix only unambiguous misreads.

    Chapters must be I, II, III, ... in order. A value lower than expected, an invalid
    numeral, or a numeral containing OCR look-alikes (H, l, 1) that disagrees with the
    sequence is replaced by the expected one ("XIHI" is ambiguous, the sequence is not).
    A clean numeral higher than expected means a heading was missed: kept, gap reported.

    Articles: a heading whose number is within the next ARTICLE_WINDOW is accepted
    (gaps reported). A number that differs from the expected one by a single digit is
    an OCR misread and is corrected in the text. Anything else (e.g. "Điều 54." quoted
    inside an amendment to another law) is NOT an article of this code: it is kept in
    the text but excluded from article metadata. Every decision is logged and the
    validated article list is stored in page["articles"].
    """
    log: list[str] = []
    expected_chapter = 1
    expected_article = 1
    for page in pages:
        new_lines, articles, quoted = [], [], []
        for line in page["text"].split("\n"):
            if m := RE_CHUONG.match(line):
                token = _chapter_token(m)
                read = roman_to_int(token)
                ambiguous = any(ch in token for ch in "Hl1")
                if read is None or read < expected_chapter or (ambiguous and read != expected_chapter):
                    fixed = int_to_roman(expected_chapter)
                    log.append(f"p{page['page']}: chapter OCR '{m.group(0).strip()}' -> 'Chương {fixed}' (sequence)")
                    page["issues"].append("fix_chapter_sequence")
                else:
                    if read > expected_chapter:
                        log.append(f"p{page['page']}: chapter {int_to_roman(read)} found, expected "
                                   f"{int_to_roman(expected_chapter)} (heading missed?)")
                        page["issues"].append("chapter_sequence_gap")
                        expected_chapter = read
                    fixed = int_to_roman(read)
                    if fixed != token:
                        log.append(f"p{page['page']}: chapter OCR '{token}' normalized to '{fixed}'")
                        page["issues"].append("fix_chapter_numeral")
                line = f"Chương {fixed}" + line[m.end():].rstrip()
                expected_chapter += 1
            elif m := match_dieu(line):
                read = int(m.group(1))
                if expected_article <= read < expected_article + ARTICLE_WINDOW:
                    if read != expected_article:
                        log.append(f"p{page['page']}: Điều {expected_article}..{read - 1} heading not found")
                        page["issues"].append("article_sequence_gap")
                    number = read
                elif _looks_like_misread(read, expected_article):
                    log.append(f"p{page['page']}: article OCR 'Điều {read}' -> 'Điều {expected_article}'")
                    page["issues"].append("fix_article_number")
                    number = expected_article
                    line = f"Điều {number}. {m.group(2)}"
                else:
                    log.append(f"p{page['page']}: 'Điều {read}.' is not the next article "
                               f"(expected {expected_article}); treated as quoted/reference text")
                    page["issues"].append("quoted_article_heading")
                    quoted.append(read)
                    number = None
                if number is not None:
                    articles.append(number)
                    expected_article = number + 1
                    canonical = f"Điều {number}. {m.group(2)}"
                    if line != canonical:
                        if read == number:
                            page["issues"].append("fix_article_heading_spelling")
                        line = canonical
            new_lines.append(line)
        page["text"] = "\n".join(new_lines)
        page["articles"], page["quoted_articles"] = articles, quoted
    log.append(f"summary: last chapter = {int_to_roman(expected_chapter - 1)}, "
               f"last article = Điều {expected_article - 1}")
    return log


def load_pdf(path: Path, document_id: str, source: str, cache_dir: Path,
             doc_metadata: dict[str, Any]) -> tuple[list[DocumentPage], dict[str, Any]]:
    """Extract each physical page via OCR, clean it and attach traceable metadata."""
    layer = text_layer_chars(path)
    ocr = ocr_pdf(path, cache_dir / f"{document_id}.ocr.json")
    pages = []
    for raw in ocr["pages"]:
        text, issues = clean_ocr_page(raw["text"])
        pages.append({"page": raw["page"], "text": text, "issues": issues, "raw": raw})
    structure_log = repair_structure(pages)

    result: list[DocumentPage] = []
    chapter = section = article = None
    for page in pages:
        found = find_structure(page["text"])
        found["articles"] = page["articles"]          # validated, quoted headings excluded
        start = {"chapter": chapter, "section": section, "article": article}
        if found["chapters"]:
            section = None                     # a new chapter resets its sections
        chapter = found["chapters"][-1] if found["chapters"] else chapter
        section = found["sections"][-1] if found["sections"] else section
        article = found["articles"][-1] if found["articles"] else article
        raw = page["raw"]
        result.append(DocumentPage(
            document_id=document_id,
            source=source,
            page=page["page"],
            text=page["text"],
            metadata={
                **doc_metadata,
                "chapter_at_start": start["chapter"],
                "article_at_start": start["article"],
                "chapters_on_page": found["chapters"],
                "sections_on_page": found["sections"],
                "articles_on_page": found["articles"],
                "quoted_article_headings": page["quoted_articles"],
                "char_count": len(page["text"]),
                "is_content_page": len(page["text"]) >= MIN_CONTENT_CHARS,
                "text_layer_chars": layer[page["page"] - 1],
                "ocr_mean_conf": raw["mean_conf"],
                "ocr_low_conf_words": raw["low_conf_words"],
                "ocr_word_count": raw["word_count"],
                "cleaning_issues": sorted(set(page["issues"])),
            },
        ))
    report = {
        "document_id": document_id,
        "ocr_settings": ocr["settings"],
        "pdf_sha256": ocr["pdf_sha256"],
        "structure_log": structure_log,
        "ocr_seconds_total": round(sum(p["seconds"] for p in ocr["pages"]), 1),
    }
    return result, report
