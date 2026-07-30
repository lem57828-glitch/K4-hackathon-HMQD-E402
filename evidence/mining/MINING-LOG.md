# Mining log — Đường B (bằng chứng đếm được)

**Ngày chạy:** 2026-07-30 · **Script:** [mine_chatlog.py](mine_chatlog.py) · **Output thô:** [run-output-2026-07-30.txt](run-output-2026-07-30.txt)
**Nguồn:** `data/vlearn-pack/chatlog/chat_history_anonymized_for_hackathon.csv` — 2.522 dòng, 1.261 câu hỏi học viên, 369 user, 22/07→29/07/2026.

## Vì sao dùng chatlog VLearn cho một feature trên Discord

Đề bài hướng B không cấp data pack riêng — khu hỏi đáp Discord phải tự quan sát. Chatlog VLearn là **bề mặt hỏi-đáp AI duy nhất của khoá có log đo được**, và nó trả lời được đúng câu hỏi nền của chúng tôi: *học viên khoá này có hỏi lại câu người khác đã hỏi không, và với tần suất nào?* Chúng tôi coi đây là **proxy có giới hạn**, khai rõ giới hạn ở §Giới hạn bên dưới, và bù bằng quan sát trực tiếp trong Discord (`evidence/discord/`) + khảo sát (`evidence/survey/`).

## Phương pháp đếm (kiểm lại được)

1. Chỉ lấy `role == "student"` → 1.261 dòng.
2. Bỏ tiền tố ngữ cảnh VLearn tự chèn `(Trang N, đoạn được chọn: "...")`. Phần còn lại được gán nhãn nguồn:
   - `typed` (926) — học viên tự gõ;
   - `template_click` (335) — học viên bấm nút, VLearn sinh câu "Giải thích đoạn bôi đen ở Trang N: ...";
   - `selection_only` (0) — chỉ bôi đen, không gõ gì.
3. Chuẩn hoá: bỏ dấu, lowercase, chỉ giữ `[a-z0-9]+`, bỏ stopword tiếng Việt (danh sách cứng trong script), giữ token ≥ 2 ký tự.
4. **Gần trùng** = `Jaccard(token_set) ≥ 0.60`, mỗi câu ≥ 2 token. Gom cụm bằng union-find, chặn nến bằng inverted index; token xuất hiện ở > 400 câu bị bỏ (không mang tin).
5. **Lặp thật** = cụm có ≥ 2 message **và** ≥ 2 `user_id` khác nhau. Một người hỏi lại chính mình 2 lần không tính.

Đổi ngưỡng thì đổi kết luận — ngưỡng nằm ở hằng số `SIM_THRESHOLD` đầu script, chạy lại là ra số khác. Chúng tôi chốt 0.60 sau khi đọc tay 30 cụm ở các ngưỡng 0.5 / 0.6 / 0.7: 0.5 gom lẫn câu khác chủ đề, 0.7 bỏ sót cách diễn đạt khác ("tool calling là gì" vs "giải thích cho tôi về tool calling").

## Số đếm được

| Chỉ số | Giá trị |
|---|---|
| Câu hỏi học viên | 1.261 |
| Câu đủ dài để so trùng (≥2 token) | 803 |
| Cụm gần trùng (≥2 message) | 52 |
| **Cụm lặp thật (≥2 user khác nhau)** | **37** |
| **Message nằm trong cụm lặp thật** | **190 / 1.261 = 15,1%** |
| ├ cụm 100% do học viên tự gõ | 26 cụm · 158 message = **17,1% câu tự gõ** |
| └ cụm có lẫn template_click | 11 cụm |
| Cụm lặp lớn nhất | **94 message · 73 user khác nhau** — "tóm tắt slide này" |

Phân loại intent (toàn bộ / trong cụm lặp thật):

| Intent | Tổng | Trong cụm lặp | % loại này bị hỏi lặp |
|---|---|---|---|
| khái niệm (hỏi bài) | 1.140 | 176 | 15,4% |
| logistics (deadline/link/nộp bài/tài liệu) | 62 | 12 | 19,4% |
| chào hỏi / lạc đề | 59 | 2 | 3,4% |

Số khác lấy trực tiếp từ `DATA_DICTIONARY.md` (team VLearn đã tính, không phải chúng tôi đếm): **46,2% câu trả lời của tutor có `citations` rỗng** — trả lời mà không trỏ được về tài liệu. Đây là lý do lát cắt của chúng tôi bắt buộc mọi câu trả lời phải kèm link post gốc.

## ≥5 ví dụ nguyên văn (mã message để đối chiếu)

Trích ngắn theo quy định bảo mật data pack — mỗi ví dụ ≤ 1 dòng, kèm mã `M####`/`U####`.

| # | Cụm | Message | User | Nguyên văn (rút gọn) |
|---|---|---|---|---|
| 1 | "tool calling là gì" — 3 msg / 3 user | `M1280` | `U0294` | "tool calling là gì" |
| 2 | cùng cụm trên | `M0740` | `U0183` | "Giải thích cho tôi về tool calling" |
| 3 | cùng cụm trên | `M2338` | `U0015` | "chi tiết tool calling" |
| 4 | "harness engineering là gì" — 3 msg / 2 user | `M2484` | `U0072` | "harness engineering là gì" |
| 5 | cùng cụm trên | `M2374` | `U0306` | "Harness engineering là gì" |
| 6 | "tóm tắt slide" — 94 msg / 73 user | `M1149` | `U0067` | "tóm tắt nội dung chính trong slide này" |
| 7 | cùng cụm trên | `M0903` | `U0128` | "Tóm tắt sờ lai này" |
| 8 | "rule-based bot vs LLM chatbot vs agent" — 3 msg / 3 user | `M0318` | `U0342` | "Khi nào nên dùng cái nào: rule-based bot, LLM chatbot, và agent" |
| 9 | logistics | `M2247` | — | "xem bài tập thực hành lab day 2 chiều nay ở đaau" |
| 10 | ngoài phạm vi (③) | `M2041` | `U0105` | "trả lời câu hỏi này" (nhờ AI làm hộ bài tập trên slide) |

Ví dụ 9 và 10 là hai loại câu chúng tôi phải xử lý khác nhau: 9 = logistics, sai thì học viên nộp muộn; 10 = nhờ làm hộ bài, phải từ chối mà vẫn hữu ích.

## Giới hạn của bằng chứng này (khai trước khi bị hỏi)

1. **Khác bề mặt.** Chatlog là AI tutor trong trang học, không phải forum Discord. Ở Discord câu hỏi dài hơn, có tiêu đề, và có thread thảo luận — nên tỉ lệ trùng thật ở Discord có thể cao hơn (hỏi lại vì không tìm thấy post cũ) hoặc thấp hơn (đã có người search trước).
2. **Ngưỡng là lựa chọn của nhóm**, không phải chân lý — xem §Phương pháp.
3. **Nhãn `typed` còn nhiễu:** vài dòng bắt đầu bằng ký tự rác (`") Giải thích đoạn bôi đen...`) không khớp regex template nên bị đếm là `typed` (thấy ở cụm 5 trong output thô). Ảnh hưởng ước lượng < 1% và làm số 17,1% **cao hơn thực tế một chút** — chúng tôi để nguyên thay vì tinh chỉnh regex cho số đẹp.
4. **Cụm lớn nhất không phải câu hỏi kiến thức** mà là lệnh "tóm tắt slide" — nó chứng minh "cùng một yêu cầu lặp lại rất nhiều lần", chứ không chứng minh "câu hỏi khó bị hỏi lại". Hai cái này khác nhau và chúng tôi không gộp.

## Còn thiếu — ai làm, khi nào

- [ ] **Đếm trực tiếp trong Discord** khu `#hỏi-đáp`: tổng số post, số post có tag Solved, số post trùng chủ đề. → `evidence/discord/discord-mining-log.md` (chưa chạy — cần quyền đọc lịch sử channel).
- [ ] **Khảo sát ≥20 người** ngoài nhóm theo mẫu `evidence/survey/SURVEY.md` (chưa chạy).
