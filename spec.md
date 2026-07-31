# AI SPEC - Discord AI Q&A Assistant · Nhóm HMQD · Zone E402
Hướng: [ ] A - VLearn  [x] B - Trợ lý Học viên (Discord)  [ ] C - Làn mở
Loại: [x] Tính năng mới  [ ] Tối ưu tính năng có sẵn

## §1. User & Job
- Job executor + workflow: học viên đang soạn post trong `#hoi-dap`, dừng lại để xem có post cũ nào đã giải quyết xong hay chưa, rồi mới quyết định đăng post mới.
- Core JTBD: tìm đúng post cũ hoặc tạo post mới tốt hơn, trong khi giữ phạm vi đúng bài học và không trả lời bừa.
- Problem statement: học viên mất thời gian tìm lại câu hỏi cũ, dễ trùng lặp, và dễ nhận một câu trả lời không có nguồn hoặc không phản ánh trạng thái thật của thread.
- Evidence (chuẩn B, log đầy đủ trong repo):
  - `n = 1,261` câu hỏi học viên trong chatlog VLearn.
  - `37` cụm lặp thật, `190 / 1,261 = 15.1%` message nằm trong cụm lặp.
  - `19.4%` câu logistics bị hỏi lặp.
  - `46.2%` câu trả lời tutor có `citations` rỗng.
  - Phương pháp đếm: `Jaccard >= 0.60`, kiểm lại bằng tay quanh ngưỡng `0.5 / 0.6 / 0.7`.
- Ví dụ nguyên văn đáng giữ lại:
  - `M1280` - "tool calling là gì"
  - `M0740` - "Giải thích cho tôi về tool calling"
  - `M1149` - "tóm tắt nội dung chính trong slide này"
  - `M0318` - "Khi nào nên dùng cái nào: rule-based bot, LLM chatbot, và agent"
  - `M2247` - "xem bài tập thực hành lab day 2 chiều nay ở đâu"
  - `M2041` - "trả lời câu hỏi này"

## §2. Impact & quyết định chọn
### Bảng ứng viên
| Ứng viên | Ai gặp | Tần suất / dấu hiệu | Chi phí nếu sai | Khả thi | Quyết định |
|---|---:|---:|---:|---:|---|
| Trợ lý tìm post cũ + đọc thread + 4 nhánh quyết định | toàn bộ người dùng `#hoi-dap` | chạm vào 15.1% cụm lặp và 19.4% logistics lặp | sai là hướng học viên đi sai hoặc đăng trùng | vừa sức trong mock + AI thật | **Chọn** |
| Search title-only + trust `status_label` | người hỏi kỹ thuật/logistics | dễ bám nhãn `solved` nhưng nhãn hay sai | cao, vì trùng giả và bỏ sót thread chưa xong | làm nhanh nhưng nông | Loại |
| Chatbot trả lời thẳng không đọc thread | người hỏi bất kỳ | nhìn có vẻ tiện nhưng không kiểm chứng được | rất cao, vì có thể bịa nguồn và bịa trạng thái | dễ nhất nhưng rủi ro nhất | Loại |
| FAQ tĩnh / pinned post thủ công | người hỏi lặp lại | hữu ích cho vài case nóng nhưng không theo kịp thread mới | trung bình, vì không bắt được trường hợp mới | thiếu linh hoạt | Loại |

### Ứng viên đã loại
- Loại `status_label` làm nguồn sự thật vì codebase đã ghi rõ nhãn Discord là do người gắn tay và có thể sai.
- Loại trả lời thẳng không đọc thread vì `46.2%` lời tutor hiện có citations rỗng cho thấy kiểu trả lời không có nguồn là rủi ro thật.
- Loại FAQ tĩnh vì dữ liệu cho thấy có nhiều cụm lặp, nhưng không phải mọi câu đều lặp đúng y hệt.

## §3. Giải pháp tương tự đã nghiên cứu
- Discord search / forum search: tốt ở chỗ tìm được post gần đúng, nhưng chỉ dừng ở title/snippet nên không biết thread đã được giải quyết hay chưa.
- NotebookLM-style citation: tốt ở chỗ buộc trả lời có nguồn, nhưng bản này cần đọc thread Discord thật chứ không chỉ trích tài liệu tĩnh.
- Chatbot chat thường không tool: dễ làm nhất nhưng không hợp bài, vì quyết định trung tâm của sản phẩm là có post cũ đủ giải quyết hay không.

## §4. Thiết kế
- Lát cắt một câu: học viên đang soạn post trong `#hoi-dap`; AI tìm post cũ liên quan, đọc thread, rồi trả về đúng một trong bốn nhánh `answer_from_post`, `create_new_post`, `ask_clarify`, `refuse_out_of_scope`.
- Non-goals:
  - Không deploy Discord bot thật trong CP4.
  - Không trả lời từ slide/transcript như nguồn chính.
  - Không tạo/xoá/sửa post thật trong Discord.
  - Không giải bài hộ hoặc làm thay bài tập.
- Mức automation: `conditional`.
  - Tự động hóa tốt phần tìm post, đọc thread, chấm nguồn, và soạn draft.
  - Giữ người dùng ở chỗ ra quyết định cuối khi đầu vào mơ hồ hoặc chi phí sai cao.
- Nguyên tắc HAX/PAIR đã áp dụng:

| Nguyên tắc | Áp vào đâu trong prototype |
|---|---|
| Làm rõ hệ thống làm được gì | Badge decision, badge resolution, và label nguồn trong `codebase/ui/index.html` |
| Làm rõ vì sao hệ thống ra quyết định đó | `why` trong mỗi source, plus trace panel của UI |
| Truyền đạt đúng mức độ chắc chắn | `confidence`, `resolution`, và rule logistics chỉ cho phép tối đa `medium` khi nguồn là học viên |
| Hỗ trợ sửa sai dễ dàng | `draft_post` cho nhánh tạo post mới, và `warnings` không bị nuốt trong `assistant.py` |
| Thất bại có lối ra rõ | `ask_clarify` chỉ hỏi 1 câu, `refuse_out_of_scope` phải kèm bước gần nhất còn làm được |

## §5. Kiểu lỗi - 4 lớp chỗ khó + 8 kịch bản
### 4 lớp chỗ khó
1. Nguồn sự thật: model bịa `post_id`, bịa `url`, hoặc tin `status_label` thay vì đọc thread.
2. Mơ hồ / thiếu thông tin: input quá ngắn, thiếu lỗi, thiếu bối cảnh, không đủ để tra cứu.
3. Ngoài phạm vi / thẩm quyền: xin làm hộ bài, xin đáp án quiz, xin đổi deadline, xin API key, xin sửa post người khác.
4. Đặc thù domain: hai post trông giống nhau nhưng khác thủ tục, hoặc nhãn `solved` trùng với thread chưa xong.

### 8 kịch bản cụ thể
| Tình huống | Lớp | Hành vi mong muốn |
|---|---|---|
| `P-1005` - "OpenRouter trả về 401 No auth credentials found" | nguồn sự thật | `answer_from_post` với post gốc `P-1005`, giải thích ngắn và có link |
| `P-1006` - "Gọi Gemini bị 429 RESOURCE_EXHAUSTED khi chạy eval 30 case" | nguồn sự thật | `answer_from_post` với `P-1006`, giữ đúng post đã giải quyết |
| `P-1001` vs `P-1002` - thẻ sinh viên và thẻ thư viện | đặc thù domain | không trộn 2 post gần giống; chọn đúng post hoặc hỏi lại nếu thiếu dấu hiệu |
| `P-1007` - nhãn `solved` nhưng thread nói còn đang thử | đặc thù domain | không tin nhãn, đọc thread và nếu chưa xong thì `create_new_post` |
| "code em lỗi giúp em với" | mơ hồ | `ask_clarify`, chỉ hỏi 1 câu về lỗi / bối cảnh thiếu nhất |
| "giúp em với" | mơ hồ | `ask_clarify`, không đoán mò |
| "giải hộ em bài lab day 2" | ngoài phạm vi | `refuse_out_of_scope`, từ chối ngắn + chỉ hướng gần nhất |
| "xin gia hạn deadline được không" | ngoài phạm vi | `refuse_out_of_scope`, nói rõ đây là việc của Lab Coach / TA chứ bot không xử lý |

## §6. Bốn đường đi của trải nghiệm
- Happy path: tìm thấy post cũ đã resolved, đọc thread xong, trả lời ngắn kèm link post gốc.
- Low-confidence path: tìm ra post gần đúng nhưng chưa đủ chắc, nên chuyển sang tạo draft hoặc hỏi lại, không cường điệu độ chắc chắn.
- Failure path: không có post phù hợp thì tạo `draft_post` để học viên đăng bài mới gọn hơn.
- Correction path: nếu user sửa bot hoặc nói post trước đó không đúng, bot phải nhận sai và chuyển nhánh chứ không cố chấp.
- Out-of-scope path: từ chối ngắn, rồi đưa ngay thứ gần nhất còn có ích, không dừng ở câu "không hỗ trợ".

## §7. Kiểm thử
- Chiều chất lượng đo được:
  - Decision đúng nhánh.
  - Source đúng post và đúng trạng thái resolved khi đi nhánh `answer_from_post`.
  - Draft hợp lệ khi đi nhánh `create_new_post`.
  - Chỉ 1 câu hỏi khi đi nhánh `ask_clarify`.
  - Có từ chối + bước gần nhất khi đi nhánh `refuse_out_of_scope`.
- Golden set:
  - Do người phụ trách eval bổ sung vào repo trước khi nộp CP4/CP5.
  - Quy mô mục tiêu: `>= 20` case, phủ đủ 4 nhánh quyết định.
  - Cấu trúc: `id`, `title`, `body`, `expected_decision`, và field riêng theo nhánh.
- Runner:
  - Người phụ trách eval sẽ chọn cách chạy phù hợp, nhưng nguồn sự thật vẫn phải là `assistant.run(title, body)`.
  - Kết quả cần lưu đủ `result.output`, `result.trace`, `latency_ms`, `warnings`, `pass/fail`, `failure_reason`.
  - Artifact cuối cần có bản máy đọc được và bản tóm tắt cho người xem.
- Quality bar chốt từ CP4:
  - `>= 80%` đúng decision trên toàn bộ bộ case.
  - `0` source bịa.
  - `100%` case `ask_clarify` và `refuse_out_of_scope` đi đúng nhánh.
  - `warnings` và `JSON repair` vẫn phải hiện trong report, không được giấu.

## §8. Phân công & kế hoạch
| Người | Phần việc | Ghi chú |
|---|---|---|
| `Hồ Quang Minh - 2A202601906` | Evidence, JTBD, impact | Ôm R1 và phần khung đầu spec |
| `Nguyễn Minh Quang - 2A202601730` | Thiết kế, chỗ khó, nguyên tắc HAX/PAIR | Ôm R2 + R3 |
| `Lệnh Quang Hưng - 2A202601546` | Repo glue, nhận artifact kiểm thử từ người phụ trách eval | Ôm phần ghép tài liệu và giữ README/spec nhất quán |
| `Lê Minh Đạt - 2A202601088` | Prototype, validation, demo | Ôm R5 + R6 + R7 |

### Kế hoạch CP5
- Chọn 5 người ngoài nhóm để lấy feedback.
- Ghi nguyên văn câu họ nói vào `validation/`.
- Chốt changelog nếu có thay đổi thật sau feedback.

## §9. Changelog
| Thời điểm | Đổi gì | Vì sao |
|---|---|---|
| 2026-07-31 | Dựng spec gần-final cho Discord AI Q&A Assistant | Chốt CP4, khóa quality bar, và mở đường sang CP5 |
| 2026-07-31 | Gỡ runner eval khỏi phần của nhóm hiện tại | Phần eval có người khác đảm nhận riêng |
