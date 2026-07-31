# Mock data — khu `#hỏi-đáp` giả lập

`qna_posts.json` là **dữ liệu giả 100%**, nhóm tự viết. Không có dòng nào lấy từ Discord thật, không có tên người thật, mọi link `discord.com/channels/9001/...` đều bịa. Lý do dùng data giả: đề bài hướng B không cấp data pack, và luật hackathon cấm đưa dữ liệu thật của người thật vào repo.

**Prototype này là mức Mock:** 23 post giả là nguồn sự thật duy nhất, hardcode trong file JSON. Phần chạy thật là quyết định của AI (xem `codebase/README.md`).

## Cấu trúc một post

| Field | Ý nghĩa |
|---|---|
| `post_id`, `url`, `title`, `body`, `author`, `created_at` | metadata post |
| `tags` | tag người đăng/Lab Coach gắn — lấy trong `tag_vocabulary` |
| `status_label` | `"solved"` \| `null` — **nhãn người gắn tay trên Discord** |
| `messages[]` | toàn bộ hội thoại trong thread (`role`: student / ta / lab_coach) |
| `reactions` | emoji đếm được |

## Điểm quan trọng nhất: `status_label` KHÔNG phải sự thật

Trợ lý **không được** đọc `status_label` rồi kết luận. Nó phải đọc `messages[]` và tự phán trạng thái thật:

- `resolved` — có cách sửa cụ thể **và** người hỏi xác nhận xong.
- `in_progress` — có hướng nhưng người hỏi báo vẫn chưa chạy / còn lỗi mới.
- `unclear` — không có cách sửa cụ thể, hoặc các câu trả lời trái nhau, hoặc không ai xác nhận.

Đây chính là quyết định AI trung tâm của lát cắt, và là chỗ `status_label` bẫy được cả người lẫn máy.

## Bảng bẫy đã gài (dùng cho golden set)

| Post | Nhãn trên Discord | Trạng thái THẬT | Bẫy gì |
|---|---|---|---|
| `P-1007` Model không gọi tool | `solved` | **in_progress** | Nhãn nói xong, thread kết ở *"Đang thử cách phân loại intent, chưa xong"*. Tin nhãn là trả lời sai. |
| `P-1018` Supabase RLS chặn insert | `solved` | **in_progress** | Sửa được ở SQL editor nhưng gọi từ client vẫn 403. Giải quyết một nửa. |
| `P-1004` Nộp reflection ở đâu | `null` | **unclear** | Hai học viên trả lời trái nhau, không ai có thẩm quyền. Câu logistics — trả lời sai là học viên nộp sai chỗ. |
| `P-1019` Alembic multiple heads | `null` | **unclear** | Câu trả lời duy nhất là *"hình như có lệnh merge heads"* — không phải cách sửa. |
| `P-1013` Streamlit hay Gradio | `null` | **unclear** | Câu hỏi ý kiến, hai luồng, kết bằng *"cái nào cũng được"*. |
| `P-1023` Tutor không trích trang | `null` | **in_progress** | TA xác nhận là hạn chế đã biết, chỉ có workaround. |
| `P-1001` vs `P-1002` | cả hai `solved` | resolved | **Cặp gần trùng:** thẻ sinh viên (One-Stop, 100k) vs thẻ thư viện (quầy thủ thư, miễn phí). Trộn hai post là trả lời sai. |
| `P-1005` vs `P-1006` | cả hai `solved` | resolved | Đều là lỗi gọi API nhưng nguyên nhân khác hẳn (401 do .env vs 429 do rate limit). |

## Chủ đề nào KHÔNG có trong data (dùng để test đường "tạo post mới")

Cố tình không có post nào về: deploy Cloudflare Workers · WebSocket / realtime · LangGraph · fine-tune model · Redis cache · React Native · thanh toán/Stripe · xin nghỉ học có phép.

Hỏi những chủ đề này thì trợ lý **phải** đi đường `create_new_post`, không được ghép bừa vào một post gần gần.

## Phân bố

23 post · 70 tin nhắn · tag: AI/LLM 7 · Logistics 6 · Backend 5 · Frontend 4 · Database 4 (một số post nhiều tag).
`status_label == "solved"`: **19** · `null`: **4**.

Đếm lại bằng máy:

```bash
python -c "import json,collections;d=json.load(open('codebase/data/qna_posts.json',encoding='utf-8'));print(collections.Counter(str(p.get('status_label')) for p in d['posts']))"
```

Tỉ lệ nhãn `solved` cao (19/23) là **chủ ý**: trên Discord thật người ta gắn nhãn rộng tay,
và đúng chỗ đó mới sinh ra bẫy — 3 trong 19 post gắn `solved` thực ra chưa xong.
