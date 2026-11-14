# Roadmap — Day 06 Data Ingestion (Bộ luật Lao động 2012 và 2019)

Lộ trình để hoàn thành bài lab, từ dữ liệu thô tới bài nộp. Mỗi bước ghi rõ việc cần làm, file đầu ra, lệnh chạy và mục rubric tương ứng.

**Trạng thái:** ✅ xong · 🔶 đang làm hoặc nên làm tiếp · ⬜ chưa làm

| # | Bước | Trạng thái | Rubric |
|---|---|---|---|
| 0 | Setup môi trường (Docker pgvector, venv, Tesseract) | ✅ | — |
| 1 | Corpus: tải, OCR, làm sạch, manifest | ✅ | Corpus và xử lý (20) |
| 2 | Benchmark 20 câu, kiểm chứng evidence | ✅ (commit `c8a0616`) | Benchmark (10/20) |
| 3 | Sửa lỗi OCR ký hiệu điểm `a)`/`c)` | ✅ | Corpus, Coherence |
| 4 | Chunking A (cố định) và B (theo Điều/khoản) | 🔶 làm tiếp | Ba chiến lược (20) |
| 5 | Embedding model thật | ⬜ | Ba chiến lược |
| 6 | Vector store pgvector: schema, upsert, filter | ⬜ | Ba chiến lược |
| 7 | Chạy A/B/C trên dev → chọn cấu hình → chạy test | ⬜ | Benchmark (10/20) |
| 8 | Audit thủ công: coherence, metadata, grounding | ⬜ | Năm khía cạnh (25) |
| 9 | Báo cáo, experiment log, STUDENT.md, nộp bài | ⬜ | Tái lập và báo cáo (15) |

---

## 0. Setup ✅

- Docker: container `day6_student_starter-postgres-1` (pgvector 0.8.7, PostgreSQL 16) chạy ở cổng `127.0.0.1:55433`.
- Python 3.12, venv ở `starter/.venv`; thư viện trong [starter/requirements.txt](starter/requirements.txt).
- Tesseract 5.4 (`winget install --id UB-Mannheim.TesseractOCR -e`) và model `starter/tessdata/vie.traineddata` (tessdata_best, không commit; cách tải xem [starter/README.md](starter/README.md)).

```bash
cd starter
.venv/Scripts/python scripts/check_setup.py
```

## 1. Corpus ✅

- **Nguồn:** PDF chính thức của Luật 10/2012/QH13 (moit.gov.vn) và Luật 45/2019/QH14 (vanban.chinhphu.vn). Quyền sử dụng theo khoản 2 Điều 15 Luật SHTT.
- **Số liệu:** 151 trang vật lý, cả 151 là trang nội dung, khoảng 350 nghìn ký tự. Cấu trúc nhận diện đủ: 17 chương / 242 điều (2012) và 17 chương / 220 điều (2019).
- **Đầu ra:**
  - [starter/data/manifest.json](starter/data/manifest.json)
  - `starter/data/processed/pages.jsonl`
  - `starter/data/ocr/*.ocr.json` (cache OCR)
  - [starter/results/ingestion_log.json](starter/results/ingestion_log.json)
- **Chạy lại** (khoảng 10 giây vì dùng cache; nếu chưa có cache thì OCR mất khoảng 8 phút):

```bash
cd starter
.venv/Scripts/python -X utf8 scripts/build_corpus.py
```

## 2. Benchmark ✅

- **Bộ câu hỏi:** [benchmark/questions.json](benchmark/questions.json) gồm 20 câu, 15 dev và 5 test, chia theo chủ đề. Có 8 câu có filter `year`, trong đó 3 câu thuộc test.
- **Tiêu chí chọn chiến lược** (đã chốt trước khi xem test) và các rủi ro rò rỉ: xem [benchmark/README.md](benchmark/README.md).
- **Kiểm chứng:** 34/34 đoạn evidence nằm đúng trang và đúng điều.

```bash
cd starter
.venv/Scripts/python -X utf8 scripts/verify_benchmark.py
```

> **Không sửa bộ câu hỏi sau bước này.** Nếu buộc phải sửa (ví dụ đổi bước làm sạch làm lệch evidence), ghi lý do vào báo cáo và chạy lại script kiểm chứng.

## 3. Sửa lỗi ký hiệu điểm ✅

**Vấn đề:** OCR đọc ký hiệu điểm sai theo hai kiểu, khiến điểm bị nối vào đoạn trước hoặc thứ tự bị nhảy:
- thành ký tự lạ: `8)`, `9)`, `3)`, `a3)`, `©)`, `ce)`, `ơ)`, `ở)`, `ï)`, `¡)`, `°)`, `.d)`, `đỳ`;
- thành chữ cái hợp lệ nhưng sai: `c)` thành `e)`, `d)` thành `đ)`.

**Cách sửa** (trong `_split_midline_points` và `_fix_point_marker` của [starter/src/ingestion.py](starter/src/ingestion.py)):
- Chữ cái **không đoán theo hình dạng ký tự** mà suy ra từ thứ tự:
  - đang trong một danh sách điểm (tính từ khoản hoặc Điều gần nhất) thì lấy chữ kế tiếp;
  - dòng trước mở đầu danh sách (kết thúc bằng `:`) thì là `a`.
- Chữ cái hợp lệ nhưng sai thứ tự chỉ được sửa với các cặp dễ nhầm c/e và d/đ.
- Điểm bị dính giữa dòng (`...36 tháng: ơ) Ít nhất...`) được tách thành dòng riêng.

**Kết quả:**
- 32 chỗ đã sửa, ghi trong `cleaning_issues` (vd. `fix_point_marker:ơ->c`, `fix_point_letter:e->c`).
- 1 chỗ không giải quyết được (`€)` ở trang 81 bản 2019): nằm trong phần trích Luật BHXH tại Điều 219, chuỗi điểm bắt đầu từ trang trước. Đã ghi `unresolved_point_marker`.
- Kiểm tra lại: mọi chuỗi điểm trong 151 trang đều liền mạch; `verify_benchmark.py` vẫn đạt 34/34 evidence, bộ câu hỏi không đổi.
- [ ] Commit riêng thay đổi này, ghi rõ nó xảy ra **sau** khi chốt benchmark và không đổi câu hỏi.

## 4. Chunking ⬜ — [starter/src/chunking.py](starter/src/chunking.py)

Mọi chunk mang metadata `chunk_id`, `document_id`, `source`, `page` (trang bắt đầu), `pages` (các trang mà chunk trải qua), `year`, `law_number`, `chapter`, `article`.

| | A — cố định | B — theo cấu trúc |
|---|---|---|
| Đơn vị | Cửa sổ 500 ký tự, overlap 50, **trong từng trang** | Một **Điều**, có thể trải qua 2 trang |
| Điều quá dài | — | Tách theo khoản, tối đa khoảng 1.200 ký tự; mỗi phần lặp lại dòng tiêu đề "Điều N. …" |
| `article` | Điều đang hiệu lực tại vị trí đầu chunk | Số của Điều |

- [ ] `chunk_id` ổn định, ví dụ `sha1(strategy|document_id|page|vị trí bắt đầu|text)`, để khi nạp lại không bị trùng.
- [ ] **Quy ước hit** (ghi vào báo cáo): chunk trúng khi `gold_page ∈ pages`, đúng `source_id` và chứa đủ mọi `evidence_quote` của gold đó.
- [ ] Ghi thống kê: số chunk, độ dài min/trung vị/max, tổng ký tự của A và B → `starter/results/chunk_stats.json`.

## 5. Embedding ⬜ — [starter/src/embeddings.py](starter/src/embeddings.py)

**Khuyến nghị: `intfloat/multilingual-e5-base`** (local, 768 chiều, giới hạn 512 token, hỗ trợ tiếng Việt, không tốn phí).
- Bắt buộc thêm tiền tố: `query: ` cho câu hỏi và `passage: ` cho chunk; chuẩn hóa vector.
- Không chọn `paraphrase-multilingual-MiniLM-L12-v2` vì nó chỉ đọc tối đa 128 token: chunk B dài sẽ bị cắt, làm so sánh A–B thiếu công bằng.

Việc cần làm:
- [ ] `pip install sentence-transformers` và ghi lại phiên bản vào requirements.
- [ ] Ghi tên model, revision, số chiều, thiết bị (CPU/GPU) và thời gian embed.
- [ ] Nếu model lỗi thì dừng và báo lỗi; **không** fallback sang vector ngẫu nhiên.

## 6. Vector store ⬜ — [starter/src/store.py](starter/src/store.py)

- [ ] Bảng `chunks`: `chunk_id` (khóa chính), `strategy`, `document_id`, `source`, `page`, `pages int[]`, `year int`, `law_number`, `chapter`, `article`, `text`, `embedding vector(768)`.
- [ ] `upsert` bằng `INSERT … ON CONFLICT (chunk_id) DO UPDATE`; xóa các chunk cũ của cùng `strategy` + `document_id` mà không còn trong lần nạp mới.
- [ ] `search`: `ORDER BY embedding <=> %s LIMIT 3`, khoảng cách cosine, filter `WHERE year = %s` truyền qua tham số. Không tạo index nên đây là **exact search**; ghi điều này vào báo cáo.
- [ ] Kiểm tra nạp lại: chạy ingest hai lần, `COUNT(*)` theo strategy không đổi → lưu `starter/results/reingest_check.json`.

## 7. Chạy thí nghiệm ⬜ — [starter/src/evaluation.py](starter/src/evaluation.py), [starter/src/run.py](starter/src/run.py)

| Cấu hình | Chunk | Filter |
|---|---|---|
| A | Cố định 500/50 | Không |
| B | Theo Điều/khoản | Không |
| C | Giống B | `year` khi câu hỏi có filter; câu không filter chạy như B |

Hai so sánh có kiểm soát: A–B chỉ đổi cách chunk, B–C chỉ đổi filter.

1. [ ] Chạy A, B, C **chỉ trên dev** → `starter/results/traces/{A,B,C}_dev.jsonl`. Mỗi dòng lưu câu hỏi, filter, top-3 (id, text, score, metadata) và cờ hit@1/hit@3.
2. [ ] Tính Hit@1 và Evidence Hit@3 dưới dạng n/N theo strategy → `starter/results/metrics_dev.json`.
3. [ ] Chọn cấu hình theo tiêu chí trong `benchmark/README.md` và ghi vào `artifacts/experiment_log.csv` **trước khi** chạy test.
4. [ ] Chạy test một lần cho cả A, B, C → `traces/*_test.jsonl`, `metrics_test.json`.
5. [ ] Ghi thời gian ingest/embed và chi phí (0 đồng nếu dùng model local).

## 8. Audit thủ công ⬜ → `starter/results/audit/`

Chấm thủ công, độc lập với điểm số. Người chấm là tác giả bài, nên phải ghi rõ nguy cơ thiên lệch.

- [ ] **Coherence** (10 vị trí, **chốt từ bây giờ**): đoạn đầu tiên của các Điều 10, 50, 90, 130, 170 trong **cả hai** bộ luật. Với mỗi strategy, chấm chunk chứa vị trí đó theo thang 0/1/2 kèm lý do → `coherence.csv`.
- [ ] **Metadata:** 5 câu test × top-3 = 15 bản ghi mỗi strategy. Đối chiếu `source`, `page`, `year`, `article` với PDF để tính số bản ghi đúng/tổng. Tỷ lệ tuân thủ filter tính trên 3 câu test có filter. Nêu 1 trường hữu ích và 1 hạn chế → `metadata.csv`.
- [ ] **Grounding:** 5 câu test, chấm top-3 theo thang 0/1/2, báo số lượng từng mức, trung bình và lý do → `grounding.csv`.
- [ ] Chọn **2 ví dụ lỗi** có ID câu và nguồn, ví dụ:
  - câu có filter mà B trả về chunk sai năm;
  - evidence của q08/q20 bị tách qua hai chunk.

## 9. Báo cáo và nộp ⬜

- [ ] `artifacts/experiment_log.csv`: tham số, giả thuyết và Hit@1/Hit@3 dev/test của A, B, C.
- [ ] Copy [report/individual/MSSV_HoTen.md](report/individual/MSSV_HoTen.md) thành `report/individual/2A202603847_NguyenLeDangKhoa.md` rồi điền:
  - hai bảng kết quả;
  - phân tích A–B và B–C;
  - đánh đổi;
  - hạn chế: OCR sai dấu, bản 2019 là văn bản gốc chưa sửa đổi, test chỉ có 5 câu, một người chấm.
- [ ] Ghi công cụ AI đã dùng và cách kiểm tra lại (theo [RULES.md](RULES.md)).
- [ ] Điền [STUDENT.md](STUDENT.md) (chủ đề, link repo, commit chốt bài).
- [ ] README gốc: thêm phần "Cách chạy lại toàn bộ", gồm các lệnh của bước 1 → 2 → 7.
- [ ] Rà [SUBMISSION.md](SUBMISSION.md):
  - không có `.env` hay key nào;
  - `tessdata/` và `.venv/` không được commit;
  - repo mở được cho người chấm.

## Gợi ý phân bổ thời gian (theo [CHECKPOINTS.md](CHECKPOINTS.md))

| Mốc | Phải có |
|---|---|
| 1:50 | Bước 3 và 4 xong: xuất được hai cấu hình chunk |
| 2:40 | Bước 5, 6 và 7.1 xong: cả ba index trả được top-3, đã kiểm tra nạp lại |
| 3:30 | Bước 7 và 8 xong: có metrics dev/test và các file audit |
| 4:00 | Bước 9 xong: báo cáo, đã nộp link |

## Tùy chọn (nếu còn thời gian)

- Hybrid retrieval: dense kết hợp BM25 trên cùng chunk B và cùng filter. Chọn trọng số trên dev, so với baseline, và ghi cả những câu hybrid làm kết quả xấu đi.
- Thêm filter `chapter`. Hạn chế: số chương giữa hai bản lệch nhau, nên chỉ có ích khi câu hỏi nêu rõ chương.
