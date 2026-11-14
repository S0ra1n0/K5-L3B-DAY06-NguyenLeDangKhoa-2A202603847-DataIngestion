# Audit thủ công: coherence, metadata, grounding

| File | Nội dung |
|---|---|
| [coherence.csv](coherence.csv) | 10 vị trí × 3 strategy, điểm 0/1/2 kèm lý do |
| [metadata.csv](metadata.csv) | 5 câu test × top-3 × 3 strategy = 45 bản ghi, kiểm tra từng trường |
| [grounding.csv](grounding.csv) | 5 câu test × 3 strategy, điểm 0/1/2 kèm hạng của evidence và lý do |
| [coherence_positions.json](coherence_positions.json) | 10 vị trí, chunk tương ứng của A và B |
| [audit_summary.json](audit_summary.json) | Số tổng hợp (tạo bởi `scripts/summarize_audit.py`) |

## Ai chấm và cách chấm

- **Nhãn coherence và grounding** là bản nháp do trợ lý AI (Claude) chấm. Claude đọc từng chunk trong trace theo thang điểm của GUIDE.md và ghi lý do cụ thể cho từng nhãn. **Học viên phải duyệt từng dòng** ở cột `student_review`:
  - để trống hoặc ghi `ok` nghĩa là đồng ý;
  - ghi một số nghĩa là thay nhãn.

  Sau đó chạy lại `python -X utf8 scripts/summarize_audit.py`. Trường `all_rows_reviewed_by_student` trong `audit_summary.json` cho biết đã duyệt hết hay chưa.
- **Metadata** được kiểm tra tự động so với trang nguồn đã làm sạch và manifest (`scripts/audit_metadata.py`, xem docstring). Claude đã xem lại toàn bộ các dòng lỗi. Mỗi lỗi đều đã được đối chiếu với text của chunk.
- **Rủi ro thiên lệch:** người chấm (Claude và học viên) biết cấu hình nào sinh ra chunk nào, và biết C được chọn trên dev. Thang 0/1/2 thô và mẫu nhỏ. Các nhãn **không** được suy ra từ so khớp chuỗi.

## Mẫu (chốt trước khi xem điểm)

- **Coherence:** đoạn đầu của các Điều 10, 50, 90, 130, 170 trong cả hai bộ luật (chọn theo khoảng cách đều, ghi trong ROADMAP trước khi chạy). Chấm chunk chứa vị trí đó.
  - A: cửa sổ đầu tiên chứa câu mở đầu của đoạn.
  - B và C: dùng chung chunk.
  - Hạn chế: cả 10 vị trí đều rơi vào điều đủ ngắn để B giữ trọn (part 1/1), nên mẫu **không đo** chất lượng của 69 điều bị tách.
- **Metadata và grounding:** cả 5 câu test, top-3 của mỗi strategy.

## Thang điểm (theo GUIDE.md)

- **Coherence:** 0 = bị cắt giữa ý hoặc thiếu chủ thể, không hiểu được; 1 = hiểu một phần, thiếu ngữ cảnh; 2 = tự hiểu được và giữ trọn ý.
- **Grounding** (độ đủ của evidence trong top-3, **không phải** độ chính xác câu trả lời của LLM): 0 = không có bằng chứng; 1 = có nhưng thiếu điều kiện/ngữ cảnh hoặc truy nguồn sai; 2 = đủ để trả lời và truy được nguồn.
- **Metadata đủ và đúng:** `source`, `pages`, `year`, `chapter`, `article` đều khớp nguồn. Nếu `article` chỉ ghi một điều trong khi chunk chứa nội dung của hai điều thì tính là **không đủ**.

## Kết quả (bản nháp, chờ học viên duyệt)

| Strategy | Coherence TB /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (test) | Grounding 0/1/2 và TB /2 |
|---|---|---|---|---|
| A | 1.10 (10) | 10/15 | 1/3 | 0/1/4, TB 1.80 |
| B | 2.00 (10) | 15/15 | 0/3 | 0/0/5, TB 2.00 |
| C | 2.00 (10) | 15/15 | 3/3 | 0/0/5, TB 2.00 |

## Nhận xét chính

- **A:**
  - Coherence: 8/10 vị trí bị cắt giữa câu hoặc giữa từ, hoặc lẫn đuôi điều trước. Vị trí "Điều 170 bản 2012" bị 0 điểm vì chỉ còn tiêu đề và nửa dòng.
  - Metadata: 5/15 bản ghi chứa hai điều nhưng `article` chỉ ghi điều bắt đầu cửa sổ. Ví dụ q16 rank 3 (`blld-2012#p52`): evidence thuộc Điều 187 nhưng metadata ghi Điều 186. Đây cũng là lý do grounding của A ở q16 chỉ được 1.
- **B so với C:** cùng chunk, nên coherence, metadata và grounding giống nhau. Khác biệt duy nhất là filter: C tuân thủ 3/3, B 0/3. Trên q18, top-3 của B chứa cả "Quốc khánh 02 ngày" (2019) và "01 ngày" (2012), hai bằng chứng **mâu thuẫn nhau**. Điểm grounding vẫn là 2 vì metadata `year` cho phép phân biệt, nhưng một hệ thống sinh câu trả lời có thể chọn sai.
- **Trường metadata hữu ích nhất:** `year`. Nó là trường duy nhất tách được hai bộ luật có cùng chủ đề; filter `year` sửa các lỗi q03, q08 (dev) và q16 (test). `pages` giúp truy vết điều luật trải qua hai trang (ví dụ Điều 112 bản 2019, trang 41–42).
- **Hạn chế của metadata:**
  - Điều 219 bản 2019 trích nguyên văn Luật BHXH nhưng metadata chỉ ghi "Điều 219, BLLĐ 2019", không có trường nào đánh dấu "nội dung trích từ luật khác". Vì vậy dù có filter, các chunk này vẫn lọt vào top-3 của q17 (C rank 2–3).
  - Filter `year` chỉ có tác dụng khi câu hỏi nêu năm (8/20 câu).
