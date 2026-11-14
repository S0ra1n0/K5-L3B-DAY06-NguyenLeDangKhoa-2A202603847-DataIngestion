# Starter · PostgreSQL + pgvector

Docker Compose tạo PostgreSQL + pgvector local. Các khung TODO trong `src/` ban đầu **đã được hiện thực đầy đủ** cho corpus Bộ luật Lao động 2012 và 2019. Thứ tự lệnh chạy toàn bộ pipeline nằm ở [README gốc](../README.md#cách-chạy-lại-từ-thư-mục-starter-windows-python-312).

## Cấu trúc

```text
starter/
├── docker-compose.yml       # PostgreSQL 16 + pgvector, chỉ mở cổng local
├── init.sql                 # bật extension khi tạo database mới
├── requirements.txt         # thư viện (OCR, embedding, DB)
├── requirements.lock.txt    # phiên bản chính xác đã dùng (pip freeze)
├── .env.example             # cấu hình mẫu; copy thành .env
├── configs/strategies.json  # tham số A / B / C
├── scripts/                 # check_setup, build_corpus, ocr_sample_check, verify_benchmark,
│                            # build_chunks, embed_chunks, ingest_store, audit_metadata, summarize_audit
├── src/
│   ├── models.py            # DocumentPage, Chunk
│   ├── ingestion.py         # OCR (Tesseract), chuẩn hóa, làm sạch, kiểm tra cấu trúc Chương/Điều
│   ├── chunking.py          # A: cửa sổ cố định; B: theo Điều/khoản
│   ├── embeddings.py        # intfloat/multilingual-e5-base (local)
│   ├── store.py             # pgvector: schema, upsert, xóa chunk cũ, exact search + filter
│   ├── evaluation.py        # Hit@1 / Evidence Hit@3, tuân thủ filter
│   └── run.py               # dev → select → test, ghi trace
├── data/                    # raw PDF, ocr cache, processed pages, chunks, manifest, ocr_sample
└── results/                 # log, trace, metrics, audit
```

## 1. Cài và kiểm tra database

Cần Docker Desktop hoặc Docker Engine + Compose, Python **3.11–3.14**, và mạng để tải image/dependencies lần đầu. Các lệnh sau chạy từ thư mục `starter/`:

```bash
cd starter
python3 -m venv .venv
```

Kích hoạt `.venv`: macOS/Linux dùng `source .venv/bin/activate`; Windows PowerShell dùng `.venv\Scripts\Activate.ps1`. Sau đó:

```bash
python -m pip install -r requirements.txt
# macOS/Linux: cp .env.example .env
# Windows PowerShell: Copy-Item .env.example .env
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py
```

Kỳ vọng: hiện tên database, phiên bản PostgreSQL và pgvector, sau đó `Setup OK`. Đây **chỉ là kiểm tra hạ tầng**, không phải kết quả benchmark. Docker dùng cổng `127.0.0.1:55433` và mật khẩu cố định **chỉ dùng local cho lab**; nếu cổng bận, sửa đồng thời port trong `docker-compose.yml` và `DATABASE_URL` trong `.env`. `init.sql` chỉ chạy khi volume mới được tạo; nếu database sẵn có chưa bật extension, xem log Docker và kiểm tra cấu hình thay vì xóa volume chứa dữ liệu.

Dừng container nhưng giữ dữ liệu:

```bash
docker compose -p day6_student_starter stop
```

## 1b. Corpus của bài này: Bộ luật Lao động 2012 và 2019 (OCR)

Hai PDF gốc nằm trong `data/raw/` (nguồn, quyền và checksum xem `data/manifest.json`). Cả hai là **bản scan không có lớp text**, nên cần OCR:

1. Cài Tesseract 5.4 (Windows): `winget install --id UB-Mannheim.TesseractOCR -e`. Nếu cài ở chỗ khác, đặt biến `TESSERACT_CMD` trỏ tới `tesseract.exe`.
2. Tải model tiếng Việt `tessdata_best` vào `starter/tessdata/` (thư mục này không được commit):
   `curl -L -o tessdata/vie.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/vie.traineddata`
3. Chạy `python -X utf8 scripts/build_corpus.py` từ `starter/`.

Kết quả gồm cache OCR thô `data/ocr/*.ocr.json` (dùng lại nếu PDF và cấu hình OCR không đổi), các trang đã làm sạch `data/processed/pages.jsonl`, `data/manifest.json` và `results/ingestion_log.json` (trang rỗng hoặc độ tin cậy thấp, các chỗ đã sửa, kiểm tra thứ tự Chương/Điều).

Kiểm chứng mẫu OCR: chạy `python -X utf8 scripts/ocr_sample_check.py`. Script so text đã làm sạch của trang 6 ở mỗi bản với các chỗ sửa ghi trong `data/ocr_sample/corrections.json` (lập ra khi đối chiếu với ảnh) và báo WER/CER vào `results/ocr_sample_check.json`.

## 2. Embedding model

Dùng `intfloat/multilingual-e5-base`, chạy local (768 chiều, tiền tố `query:` / `passage:`), nên không cần API key. Không commit `.env`. Cài torch bản CPU trước:
`pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cpu`
rồi mới cài `requirements.txt`. Phiên bản thư viện thực tế đã dùng nằm trong `requirements.lock.txt`.

## 3. Pipeline

Chạy theo thứ tự `build_corpus` → `verify_benchmark` → `build_chunks` → `embed_chunks` → `ingest_store` → `python -m src.run dev | select | test` → `audit_metadata` → `summarize_audit` (lệnh đầy đủ ở README gốc). `src.run test` chỉ chạy được sau `select` và chỉ được chạy một lần.
