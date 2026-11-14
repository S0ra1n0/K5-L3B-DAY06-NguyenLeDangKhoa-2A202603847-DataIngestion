# Day 06 · Data Ingestion Engineering

## Bài làm: Bộ luật Lao động 2012 và 2019

**Học viên:** xem [STUDENT.md](STUDENT.md).
**Báo cáo:** [report/individual/2A202603847_NguyenLeDangKhoa.md](report/individual/2A202603847_NguyenLeDangKhoa.md).

**Kết quả:** chọn cấu hình **C** (chunk theo Điều + filter `year`).
- Dev: Hit@1 11/15, Evidence Hit@3 15/15.
- Test: Hit@1 5/5, Evidence Hit@3 5/5.

| Thành phần | Đường dẫn |
|---|---|
| Corpus gốc (2 PDF scan chính thức) và manifest | `starter/data/raw/`, `starter/data/manifest.json` |
| Trang đã OCR và làm sạch, log lỗi, kiểm chứng mẫu OCR | `starter/data/processed/pages.jsonl`, `starter/results/ingestion_log.json`, `starter/results/ocr_sample_check.json` |
| Phiên bản thư viện chính xác | `starter/requirements.lock.txt` |
| Benchmark 20 câu (15 dev / 5 test) | `benchmark/questions.json`, `benchmark/README.md` |
| Cấu hình A/B/C, experiment log | `starter/configs/strategies.json`, `artifacts/experiment_log.csv` |
| Code | `starter/src/` (ingestion, chunking, embeddings, store, evaluation, run), `starter/scripts/` |
| Trace top-3, metrics, lựa chọn | `starter/results/traces/`, `metrics_{dev,test}.json`, `selection.json` |
| Audit thủ công | `starter/results/audit/` |

### Cách chạy lại (từ thư mục `starter/`, Windows, Python 3.12)

**Yêu cầu:**
- Docker.
- Tesseract 5.4: `winget install --id UB-Mannheim.TesseractOCR -e`.
- Model tiếng Việt cho Tesseract tải vào `starter/tessdata/`:

```bash
curl -L -o tessdata/vie.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/vie.traineddata
```

**Cài đặt môi trường và khởi động database:**

```bash
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install torch==2.7.1 --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env
docker compose -p day6_student_starter up -d --wait
```

**Chạy pipeline theo thứ tự:**

```bash
.venv/Scripts/python -X utf8 scripts/build_corpus.py       # OCR + làm sạch + manifest (OCR ~8 phút lần đầu, sau đó dùng cache)
.venv/Scripts/python -X utf8 scripts/ocr_sample_check.py   # kiểm chứng mẫu OCR: WER/CER trên 2 trang so với ảnh
.venv/Scripts/python -X utf8 scripts/verify_benchmark.py   # kiểm chứng 34 đoạn evidence
.venv/Scripts/python -X utf8 scripts/build_chunks.py       # chunk A và B
.venv/Scripts/python -X utf8 scripts/embed_chunks.py       # multilingual-e5-base, CPU (~2 phút + tải model ~1,1 GB lần đầu)
.venv/Scripts/python -X utf8 scripts/ingest_store.py       # nạp vào pgvector + tự kiểm tra
.venv/Scripts/python -X utf8 -m src.run dev                # A/B/C trên dev
.venv/Scripts/python -X utf8 -m src.run select             # chọn theo tiêu chí đã chốt
.venv/Scripts/python -X utf8 -m src.run test               # test (chỉ chạy được một lần)
.venv/Scripts/python -X utf8 scripts/audit_metadata.py     # kiểm tra metadata top-3 test
.venv/Scripts/python -X utf8 scripts/summarize_audit.py    # tổng hợp nhãn thủ công
```

**Lưu ý khi chạy lại:**
- Lệnh `test` từ chối chạy nếu đã có `results/metrics_test.json`. Muốn chạy lại để kiểm tra tái lập, hãy xóa file đó (và ghi rõ đây không còn là holdout độc lập).
- Embedding chạy local, không cần API key; chi phí 0 USD.

---

## Đề bài

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database và hoàn thiện các hàm TODO, hoặc tự chọn vector store tương đương. Starter chỉ là khung: **bạn tự hiện thực pipeline và benchmark**.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.
