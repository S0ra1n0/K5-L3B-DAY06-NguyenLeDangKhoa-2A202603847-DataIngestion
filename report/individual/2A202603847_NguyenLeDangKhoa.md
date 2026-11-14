# Báo cáo cá nhân — Day 6

Học viên: Nguyễn Lê Đăng Khoa · MSSV 2A202603847 · Lớp L3B · Corpus: Bộ luật Lao động Việt Nam 2012 và 2019.
Mọi số liệu dưới đây lấy từ các file trong `starter/results/`; đường dẫn ghi ở từng mục.

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang:**
  - **Nguồn:**
    - Luật 10/2012/QH13: PDF trên Cổng TTĐT Bộ Công Thương (moit.gov.vn).
    - Luật 45/2019/QH14: PDF trên Hệ thống văn bản Chính phủ (vanban.chinhphu.vn).
    - Cả hai tải ngày 2026-11-14; URL và sha256 ghi trong [manifest](../../starter/data/manifest.json).
  - **Quyền sử dụng:** văn bản quy phạm pháp luật không thuộc phạm vi bảo hộ quyền tác giả (khoản 2 Điều 15 Luật SHTT).
  - **Số trang:** 151 trang PDF vật lý (68 + 83). Một trang được tính là trang nội dung khi text sau làm sạch có từ 300 ký tự trở lên; cả 151 trang đều đạt, tổng 349.975 ký tự.
  - **Lưu ý về phiên bản:**
    - Bản 2012 đã hết hiệu lực từ 01/01/2021.
    - Bản 2019 là văn bản gốc lúc ban hành, chưa gồm các lần sửa đổi về sau.
    - Ngày hiệu lực ghi trong manifest khớp với chữ trong văn bản (trang 67 bản 2012, trang 83 bản 2019).
- **Chuẩn hóa, lỗi và giới hạn:**
  - **OCR:** cả hai PDF là ảnh scan, không có lớp text (bản 2012 chỉ có watermark "www.LuatVietnam.vn"). OCR bằng Tesseract 5.4 với model `vie` tessdata_best, 300 DPI, mất 465 giây; độ tin cậy trung bình mỗi trang từ 92 đến 95. Có cache trong `starter/data/ocr/`.
  - **Làm sạch** (mọi thao tác ghi vào [ingestion_log.json](../../starter/results/ingestion_log.json)):
    - Chuẩn hóa Unicode về NFC.
    - Bỏ số trang, watermark và ký tự rác.
    - Nối các dòng bị ngắt thành đoạn.
    - Sửa số khoản bị đọc sai (`l.` hoặc `3,` thành `1.` hoặc `3.`).
    - Sửa ký hiệu điểm theo thứ tự a, b, c… (32 chỗ, 1 chỗ không giải quyết được và đã ghi log).
    - Sửa số La Mã và số điều theo thứ tự: "Điều 1109" thành 110, "XVH" thành XVII.
    - Loại trừ các tiêu đề điều trích từ luật khác trong Điều 219.
  - **Kiểm tra cấu trúc:** đủ 17 chương / 242 điều (2012) và 17 chương / 220 điều (2019), liên tục, không thiếu điều nào.
  - **Giới hạn:** không sửa chính tả, nên vẫn còn chữ sai dấu do OCR ("đê tuyên dụng", "thâm quyên"). Evidence của benchmark được copy nguyên văn từ text đã làm sạch.
- **Embedding, vector store, metric, lệnh chạy và chi phí:**
  - **Embedding:** `intfloat/multilingual-e5-base` (revision `d1287505…`), chạy local bằng sentence-transformers 4.1.0 trên torch 2.7.1+cpu. 768 chiều, tiền tố `query:` / `passage:`, vector đã chuẩn hóa. Không chunk nào vượt 512 token.
  - **Vector store:** PostgreSQL 16.16 + pgvector 0.8.7 (Docker), dùng khoảng cách cosine `<=>` và exact search (không có index ANN).
  - **Chi phí:** 0 USD.
  - **Thời gian:** embed A mất 55 giây, B mất 51 giây; nạp vào DB 0,3 giây (A) và 0,25 giây (B); mỗi truy vấn khoảng 20–26 ms.
  - **Lệnh chạy:** xem [README](../../README.md#bài-làm-bộ-luật-lao-động-2012-và-2019).
- **Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn:**
  - Mỗi chunk có `document_id`, `source`, `page` (trang đầu) và `pages` (mọi trang chunk trải qua).
  - Trường bổ sung:
    - `year` (int, 2012 hoặc 2019): lấy từ số hiệu văn bản trong manifest, dùng để lọc.
    - `law_number`.
    - `chapter` và `article`: lấy từ tiêu đề Chương/Điều sau khi đã kiểm tra thứ tự.
  - Lý do chọn `year`: hai bộ luật quy định cùng chủ đề nhưng khác con số (lời nói dưới 01 tháng hay dưới 03 tháng, làm thêm 40 hay 30 giờ/tháng, Quốc khánh 02 hay 01 ngày). Vì vậy `year` là trường lọc có giá trị phân biệt thật.

## Cấu hình và benchmark

- **A / B / C** (tham số trong [strategies.json](../../starter/configs/strategies.json)):
  - **A:** cửa sổ cố định 500 ký tự, overlap 50, trong từng trang, cắt đúng vị trí ký tự; 834 chunk.
  - **B:** mỗi Điều một chunk, có thể trải qua 2 trang. Điều dài hơn 1.200 ký tự được tách theo khoản → điểm → câu, mỗi phần lặp lại dòng "Điều N. …"; 552 chunk (69 điều bị tách).
  - **C:** đúng các chunk của B, chỉ thêm `WHERE year = …` khi câu hỏi có filter.
  - Như vậy A–B chỉ đổi cách chunk, còn B–C chỉ đổi filter. Cùng model, cùng store, cùng 20 câu hỏi.
- **Bộ 20 câu, chia 15 dev / 5 test** ([questions.json](../../benchmark/questions.json), [README](../../benchmark/README.md)):
  - Chia theo chủ đề để dev và test không trùng chủ đề.
  - 8 câu có filter `year` (3 câu thuộc test); năm luôn được nêu ngay trong câu hỏi, không lấy từ gold.
  - Loại câu: 7 điều kiện/ngoại lệ, 7 metadata, 3 trực tiếp, 3 diễn đạt lại.
  - Câu không có filter chỉ hỏi về quy định giống nhau ở hai bản (ghi cả hai nguồn là gold) hoặc chỉ có ở một bản.
  - Kiểm chứng evidence: `scripts/verify_benchmark.py` xác nhận 34/34 đoạn evidence nằm nguyên văn trên trang gold và đúng điều luật. Bộ câu hỏi được commit trước khi chạy bất kỳ truy xuất nào.
- **Tiêu chí chọn chiến lược đã chốt trước khi xem test** (ghi trong `benchmark/README.md`): Evidence Hit@3 trên dev → Hit@1 → tỷ lệ tuân thủ filter → ít chunk hơn → thời gian nạp thấp hơn. `src/run.py` bắt buộc thứ tự dev → select → test và không cho chạy test lần hai. Lựa chọn C được ghi vào `artifacts/experiment_log.csv` lúc 05:04Z, trước khi chạy test.

## Kết quả

Định nghĩa hit: chunk đúng `source_id`, có `gold_page` nằm trong `pages`, và chứa **đủ** mọi đoạn evidence của gold đó.

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 9/15 | 14/15 | 834 | Embed 55,1 giây · nạp 0,31 giây · truy vấn khoảng 26 ms | 0 |
| B | dev | 10/15 | 14/15 | 552 | Embed 51,0 giây · nạp 0,25 giây · truy vấn khoảng 24 ms | 0 |
| C | dev | 11/15 | 15/15 | 552 (dùng chunk của B) | Như B · truy vấn khoảng 20 ms | 0 |
| A | test | 4/5 | 5/5 | 834 | | 0 |
| B | test | 4/5 | 5/5 | 552 | | 0 |
| C | test | 5/5 | 5/5 | 552 | | 0 |

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 1,10 (10) | 10/15 | dev 0/5 · test 1/3 | 0/1/4 · 1,80 |
| B | 2,00 (10) | 15/15 | dev 1/5 · test 0/3 | 0/0/5 · 2,00 |
| C | 2,00 (10) | 15/15 | dev 5/5 · test 3/3 | 0/0/5 · 2,00 |

**Đường dẫn trace, nhãn thủ công và cách chọn mẫu:**
- **Trace top-3:** `starter/results/traces/{A,B,C}_{dev,test}.jsonl` (text, score, metadata, nhãn hit từng chunk). Metrics trong `metrics_dev.json` và `metrics_test.json`; lựa chọn trong `selection.json`.
- **Nhãn thủ công:** `starter/results/audit/` (phương pháp trong `README.md`).
  - Coherence: đoạn đầu các Điều 10, 50, 90, 130, 170 của cả hai bộ luật, chọn từ trước khi xem điểm.
  - Metadata và grounding: cả 5 câu test × top-3.
- **Người chấm:** nhãn coherence và grounding do trợ lý AI (Claude) chấm nháp theo thang điểm của GUIDE, có lý do cho từng nhãn. Tôi đã duyệt cả 90 nhãn và không sửa nhãn nào. Metadata được kiểm tra tự động so với trang nguồn, rồi các dòng lỗi được xem lại thủ công.

## Phân tích và kết luận

- **So sánh A–B (đổi cách chunk):**
  - Hit@3 trên dev bằng nhau (14/15); Hit@1 B hơn A 1 câu.
  - Khác biệt rõ nằm ở chất lượng: coherence 2,00 so với 1,10, metadata 15/15 so với 10/15.
  - Cửa sổ của A cắt giữa câu ở 8/10 vị trí, và trong 5/15 bản ghi test nó chứa nội dung hai điều trong khi metadata chỉ ghi một điều.
- **So sánh B–C (chỉ thêm filter `year`):**
  - Mọi khác biệt đều nằm ở các câu có filter: tuân thủ filter tăng từ 1/5 lên 5/5 (dev) và từ 0/3 lên 3/3 (test). Hit@3 dev tăng từ 14/15 lên 15/15, Hit@1 test từ 4/5 lên 5/5.
  - Các câu không filter cho kết quả giống hệt nhau, đúng như thiết kế.
- **Ví dụ lỗi:**
  1. **q16 (test, `blld-2012#p52`), A và B:** câu "Theo BLLĐ 2012, hưởng lương hưu khi đủ bao nhiêu tuổi?". Top-1 là Điều 219 bản 2019 (trang 80–81), vốn trích nguyên văn điều kiện lương hưu của Luật BHXH; Điều 187 bản 2012 chỉ đứng hạng 3. Riêng A còn gán metadata `article = 186` cho chunk chứa evidence của Điều 187. C (lọc `year = 2012`) đưa Điều 187 lên hạng 1.
  2. **q03 (dev, `blld-2019#p40`), B:** Điều 106 bản 2012 ("không quá 30 giờ/tháng") xếp trên Điều 107 bản 2019 ("40 giờ/tháng"). Một hệ thống sinh câu trả lời có thể trả sai con số, trong khi C trả đúng. Ngoài ra ở **q11 (dev, `blld-2012#p15`)**, A lấy đúng trang nhưng cửa sổ cắt mất câu "có thể kéo dài… không quá 30 ngày", nên trượt cả Hit@3.
- **Chiến lược chọn, đánh đổi, điều kiện áp dụng:**
  - **Chọn C** theo tiêu chí đã chốt trước; kết quả test xác nhận lựa chọn (5/5, 5/5, filter 3/3).
  - **Đánh đổi:**
    - B/C cần nhận diện cấu trúc Chương/Điều đáng tin. Với corpus OCR, việc này cần thêm bước sửa số điều và ký hiệu điểm.
    - Chunk của B/C dài hơn (trung vị 606 so với 500 ký tự, tối đa 1.199).
    - Filter chỉ có tác dụng khi người dùng nêu năm. Trong benchmark có 12/20 câu không có filter; với những câu này C hoạt động y như B, và top-3 của B ở q18 vẫn chứa hai mức trái nhau ("Quốc khánh 02 ngày" của 2019 và "01 ngày" của 2012).
  - **Điều kiện áp dụng:** văn bản pháp luật có cấu trúc Điều/khoản rõ ràng và có nhiều phiên bản cùng chủ đề.
- **Hạn chế:**
  - Test chỉ có 5 câu và dev 15 câu: chênh lệch 1 câu là 6,7 đến 20 điểm phần trăm, nên không đủ để kết luận chung ngoài corpus này.
  - Chỉ có một người duyệt nhãn và người đó biết cấu hình nào đã được chọn; thang 0/1/2 thô.
  - Mẫu coherence không rơi vào phần bị tách của 69 điều dài.
  - Evidence giữ nguyên lỗi OCR.
  - Thời gian đo trên một laptop (CPU), latency đã gồm cả thời gian mở kết nối DB.
  - Các câu "không filter" được thiết kế để đáp án giống nhau ở hai bản, nên chưa đo trường hợp người dùng không nêu năm mà đáp án lại khác nhau.
- **Nếu làm lại hoặc mở rộng:**
  - Thêm trường `quoted_from` (hoặc tách riêng phần trích luật khác trong Điều 219) để loại nhiễu ở q16 và q17.
  - Khi câu hỏi không nêu năm, mặc định lọc theo bản còn hiệu lực.
  - Thêm hybrid BM25 cho các câu có con số ("30 giờ", "06 tháng").
  - Mở rộng test lên 15–20 câu, có câu hỏi không nêu năm nhưng đáp án khác nhau giữa hai bản.
  - Dùng thêm một người chấm thứ hai để đo độ đồng thuận.

## Công cụ AI đã dùng

Tôi dùng Claude Code (Claude Opus 5.5) để:
- tìm nguồn, viết code (OCR, làm sạch, chunk, embed, store, đánh giá);
- soạn câu hỏi benchmark;
- chấm nháp các nhãn coherence và grounding.

Cách tôi kiểm tra lại:
- Mọi evidence được script đối chiếu với trang nguồn (34/34).
- Cấu trúc được kiểm tra liên tục điều 1–242 và 1–220.
- Store có các bài tự kiểm tra (nạp lại không trùng, xóa chunk cũ, tự truy xuất 29/29, filter đúng năm).
- Tôi đã đọc và duyệt cả 90 nhãn thủ công.
- Không có số liệu nào được điền tay; tất cả lấy từ các file kết quả đã chạy.
