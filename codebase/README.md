# Prototype — Trợ lý #hỏi-đáp

Mức prototype: **Mock**. Nguồn dữ liệu post là file JSON hardcode (`data/qna_posts.json`, xem
[MOCK-DATA.md](data/MOCK-DATA.md)); **quyết định là AI chạy thật** — mọi lượt đều gọi model qua
`provider.py`, không có nhánh nào hardcode câu trả lời.

## Chạy

```bash
# 1. Điền API key
cp codebase/.env.example codebase/.env      # Windows: copy codebase\.env.example codebase\.env
#    rồi mở .env điền OPENROUTER_API_KEY

# 2. Bật UI
python codebase/app.py        # tự mở http://127.0.0.1:8000
```

Không cần `pip install` — toàn bộ dùng stdlib Python 3.11+.

Chạy một lượt từ dòng lệnh (dùng cho eval):

```bash
python codebase/assistant.py --title "Lỗi 401" --body "Em gọi API trả về 401" --trace
```

## File nào làm gì

| File | Vai trò |
|---|---|
| `app.py` | Web server stdlib: phục vụ `ui/index.html` + `POST /api/ask` → `assistant.run()`. Không chứa logic quyết định. |
| `ui/index.html` | Giao diện chat. Hiện decision, confidence, nguồn kèm `resolution`, post nháp, tag, cảnh báo và trace. |
| `assistant.py` | Vòng lặp agent: model → tool call → JSON. `normalize_output()` ép output về hợp đồng và **ghi lại mọi chỗ phải sửa** vào `warnings`. |
| `provider.py` | Gọi API thật, endpoint OpenAI-compatible. Có retry cho 429/5xx. |
| `tools.py` | `search_qna_posts` (metadata + snippet) và `read_post_thread` (toàn bộ hội thoại). Tách 2 tool để buộc model đọc thread trước khi kết luận. |
| `prompts/system_prompt.md` | 4 quyết định + luật cứng (không bịa nguồn, không tin `status_label`, không trộn 2 post gần giống). |
| `data/qna_posts.json` | 23 post giả 100% — nguồn sự thật duy nhất của bản Mock. |

## Cấu hình

Đặt trong `codebase/.env` hoặc biến môi trường:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `QA_BASE_URL` | `https://openrouter.ai/api/v1` | Endpoint OpenAI-compatible |
| `QA_MODEL` | `google/gemini-3.5-flash-lite` | Model |
| `QA_API_KEY_ENV` | `OPENROUTER_API_KEY` | Tên biến chứa key |
| `QA_MAX_TOKENS` | `1200` | Output là 1 khối JSON ngắn — để cao thì free tier trả 402 |
| `QA_UI_PORT` | `8000` | Cổng web UI |

`.env` không bao giờ được commit (đã chặn trong `.gitignore`).
