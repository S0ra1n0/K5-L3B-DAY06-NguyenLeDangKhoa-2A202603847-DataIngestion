# Benchmark — Bộ luật Lao động 2012 và 2019

File câu hỏi: [questions.json](questions.json). Gồm 20 câu: 15 dev (q01–q15) và 5 test (q16–q20). Bộ câu hỏi được viết và chia split **trước khi chạy bất kỳ lần truy xuất nào**.

## Cách xây

- **Nguồn evidence:** đọc trực tiếp các điều luật trong `starter/data/processed/pages.jsonl` (text OCR đã làm sạch). Mỗi `evidence_quote` được copy nguyên văn, kể cả lỗi OCR như "băng" hay "khuyêt", để so khớp tự động được. `expected_answer` thì viết bằng tiếng Việt chuẩn.
- **Nhiều gold hợp lệ:** câu không có filter mà cả hai bộ luật quy định giống nhau (vd. q06: lương thử việc 85%) liệt kê thêm nguồn thứ hai trong `alternative_gold`; truy xuất trúng bất kỳ gold nào đều được tính hit.
- **Câu không có filter** chỉ dùng cho quy định giống nhau ở hai bản, hoặc chỉ có trong một bản (q05). Câu hỏi về điểm khác nhau giữa 2012 và 2019 luôn nêu rõ năm và có filter.
- **Filter `year`** là input giả định do người dùng cung cấp trước khi truy xuất: năm phải được nhắc trong câu hỏi (script kiểm tra điều này), không lấy từ gold. Giá trị `year` của mỗi trang lấy từ số hiệu văn bản trong manifest.
- **Kiểm chứng:** chạy `python -X utf8 scripts/verify_benchmark.py` từ `starter/`. Script kiểm tra 34/34 đoạn evidence nằm đúng trang gold, đúng điều, khớp filter và đủ số lượng split. Kết quả ghi ra `starter/results/benchmark_verification.json`.

## Thành phần

| Loại | Dev | Test | Ghi chú |
|---|---:|---:|---|
| `metadata_filter` | 4 (q01–q04) | 3 (q16–q18) | Cặp q01/q02 và q03/q04 hỏi cùng một chủ đề ở hai năm, đáp án khác nhau |
| `dieu_kien_ngoai_le` | 6 | 2 | q08 vừa là câu điều kiện vừa có filter 2019 |
| `truc_tiep` | 3 | 0 | |
| `dien_dat_lai` | 3 | 0 | Diễn đạt đời thường ("nhân viên", "ca đêm") khác từ ngữ trong luật |

Tổng cộng có 8 câu có filter, trong đó 3 câu thuộc test.

## Cách chia dev/test và rủi ro rò rỉ

Chia theo **chủ đề**, không chia ngẫu nhiên:
- **Test:** tuổi nghỉ hưu (q16, q17), nghỉ lễ Quốc khánh (q18), thời hiệu kỷ luật (q19), bảo vệ thai sản (q20).
- **Dev:** không có câu nào hỏi về các chủ đề trên.

Rủi ro còn lại:
1. q14 (dev) hỏi lương làm thêm "ngày nghỉ lễ", gần với q18 (test) về từ ngữ nhưng nằm ở điều khác (Điều 98 so với Điều 112).
2. Cặp câu dev có filter (q01–q04) cho biết cách filter `year` hoạt động, nên tinh chỉnh trên dev có thể có lợi cho các câu filter ở test.
3. Người viết câu hỏi đã đọc toàn bộ corpus, nên có thiên lệch về cách diễn đạt.

## Tiêu chí chọn chiến lược (chốt trước khi xem test)

Chọn cấu hình dựa trên **dev**, theo thứ tự ưu tiên:
1. Evidence Hit@3 cao hơn.
2. Nếu bằng nhau: Hit@1 cao hơn.
3. Nếu vẫn bằng: tỷ lệ tuân thủ filter trên các câu có filter.
4. Cuối cùng: ít chunk hơn và thời gian ingest thấp hơn.

Sau khi chốt cấu hình mới chạy test một lần. Không sửa bộ câu hỏi, nhãn hay cấu hình dựa trên kết quả test.

## Hạn chế

- Bản 2019 là văn bản gốc lúc ban hành, chưa gồm các lần sửa đổi về sau, nên đáp án phản ánh luật tại thời điểm 2019.
- Evidence giữ nguyên lỗi OCR. Nếu sau này thay đổi bước làm sạch, phải chạy lại `verify_benchmark.py`.
- Evidence của q08 và q20 gồm 2 đoạn trong cùng một điều. Chunk nhỏ có thể tách rời hai đoạn này, và khi đó câu đó không được tính hit; đây là lỗi cần ghi lại khi phân tích.
