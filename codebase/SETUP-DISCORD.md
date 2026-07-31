# Dựng bot Discord — từ số 0 tới `/hoi` chạy được

Ước lượng: **30–45 phút** nếu chưa từng làm bot Discord. Toàn bộ làm trên **server test của bạn** — không cần xin quyền ai.

> **Chỉ chạy trên server bạn tự tạo.** Thêm bot vào server không thuộc quyền sở hữu cần quyền *Manage Server* trên server đó — chỉ chủ server hoặc admin mới cấp được. Discord chặn ở phía server, không có cách vòng.

---

## Bước 1 — Tạo server test

Discord → dấu **+** ở thanh bên trái → **Create My Own** → đặt tên bất kỳ.

Trong server: **+** cạnh mục Text Channels → chọn kiểu **Forum** → đặt tên `hỏi-đáp`.

> Phải là **Forum**, không phải Text channel. Forum cho mỗi post là một thread riêng kèm tag — khớp đúng cấu trúc mock data. Script seed sẽ báo lỗi nếu bạn tạo nhầm kiểu.

---

## Bước 2 — Tạo bot

1. Vào https://discord.com/developers/applications → **New Application** → đặt tên
2. Tab **Bot** → **Reset Token** → copy (chỉ hiện đúng một lần)
3. Vẫn ở tab **Bot**, kéo xuống **Privileged Gateway Intents**, bật **cả hai**:

| Intent | Dùng để làm gì |
|---|---|
| **MESSAGE CONTENT INTENT** | Đọc nội dung tin nhắn trong thread |
| **SERVER MEMBERS INTENT** | Đọc role → phân biệt TA / Lab Coach / học viên |

Intent thứ hai **không phải trang trí**: [system_prompt.md:38](prompts/system_prompt.md#L38) ép `confidence ≤ medium` khi câu trả lời logistics chỉ do học viên nói. Không có role thì luật này chết.

Bot dưới 100 server tự bật được, Discord không cần duyệt.

---

## Bước 3 — Mời bot vào server

Tab **OAuth2** → **URL Generator**:

**Scopes:** `bot` · `applications.commands`

**Bot Permissions:**

| Quyền | Vì sao |
|---|---|
| View Channels | Thấy forum |
| Read Message History | Đọc thread cũ — **thiếu cái này index sẽ rỗng** |
| Send Messages | Trả lời |
| Send Messages in Threads | Auto-reply, nếu bật |
| Manage Webhooks | Chỉ cần cho `seed_forum.py` |
| Manage Threads | Gắn tag cho thread lúc seed |

Copy URL sinh ra ở cuối trang → mở → chọn server test → **Authorize**.

---

## Bước 4 — Điền `.env`

Lấy ID: Discord → **User Settings → Advanced → Developer Mode: ON**, rồi chuột phải vào server / channel → **Copy Server ID** / **Copy Channel ID**.

```ini
# codebase/.env
OPENROUTER_API_KEY=sk-or-v1-...

DISCORD_BOT_TOKEN=<token bước 2>
DISCORD_GUILD_ID=<id server>
DISCORD_QNA_CHANNEL_ID=<id forum channel>
```

`DISCORD_GUILD_ID` không bắt buộc nhưng **nên có**: có thì lệnh slash hiện ngay, không có thì Discord sync global và có thể mất tới 1 tiếng.

---

## Bước 5 — Cài thư viện

```bash
pip install -r codebase/requirements-discord.txt
```

Chỉ một gói: `discord.py`. Web UI và CLI vẫn chạy stdlib thuần, không cần bước này.

---

## Bước 6 — Đổ dữ liệu vào forum

```bash
python codebase/seed_forum.py --channel hỏi-đáp --dry-run   # xem trước, không ghi gì
python codebase/seed_forum.py --channel hỏi-đáp             # ghi thật
```

Tạo 23 thread · 70 tin nhắn · mất ~2 phút (có nghỉ giữa các lần gửi để tránh rate limit).

Script dùng **webhook** để mỗi tin nhắn hiện đúng tên người nói khác nhau — bot thường chỉ đăng được dưới một danh tính. Tên được đặt tiền tố `TA_` / `LabCoach_` để bot suy lại đúng vai.

> ⚠️ **Chạy hai lần sẽ ra 46 post trùng.** Script chỉ tạo, không dọn.

Sau khi xong, mở forum kiểm tra: phải thấy 23 post, có tag màu, post gắn `Solved` chiếm phần lớn.

---

## Bước 7 — Chạy bot

```bash
python codebase/discord_bot.py
```

Log mong đợi:

```
  Bot     : QnA Assistant#1234
  Server  : Server test cua ban
  Model   : google/gemini-3.5-flash-lite
  An danh : BAT
  Lenh    : da sync rieng cho guild (hien ngay)
  [index] 23 post · bo qua 0 · tag=['AI/LLM', ...]

  San sang. /hoi de dung.  Auto-reply: TAT
```

---

## Bước 8 — Thử

Gõ trong bất kỳ channel nào:

```
/hoi noi_dung: Em định nghĩa tool rồi mà model cứ trả lời thẳng, không chịu gọi tool
```

Kết quả đúng: badge **📝 Nên đăng post mới**, nguồn `P-1007` gắn **🟡 in_progress** — dù trên forum post đó mang tag `Solved`. Đó là bẫy chính, và là thứ đáng demo nhất.

Ba lệnh có sẵn:

| Lệnh | Việc |
|---|---|
| `/hoi` | Hỏi trước khi đăng — trả lời **ephemeral**, chỉ bạn thấy |
| `/trangthai` | Index đang có bao nhiêu post, dựng lúc nào |
| `/reindex` | Quét lại forum ngay (cần *Manage Server*) |

---

## Sự cố hay gặp

| Triệu chứng | Nguyên nhân |
|---|---|
| Không thấy lệnh `/hoi` | Thiếu `DISCORD_GUILD_ID` → đang sync global. Điền vào rồi chạy lại |
| `[index] 0 post` | Thiếu **Read Message History**, hoặc channel là Text chứ không phải Forum |
| `PrivilegedIntentsRequired` | Chưa bật 2 intent ở Bước 2 |
| Mọi người đều thành `student` | Chưa bật **SERVER MEMBERS INTENT**, hoặc tên role không khớp `DISCORD_TA_ROLES` |
| `The application did not respond` | Agent chạy > 15 phút — gần như chắc chắn là provider treo, xem log terminal |
| `seed_forum` báo không phải Forum channel | Tạo lại channel kiểu **Forum** |

---

## Hai điều nên biết trước khi mang lên server thật

**① `/hoi` và auto-reply là hai lát cắt khác nhau.** `/hoi` = hỏi **trước** khi đăng, đúng thời điểm can thiệp đã khai trong spec. `DISCORD_AUTO_REPLY=1` = bot rep **sau** khi đã đăng — tiện demo nhưng đổi nghĩa lát cắt. Đừng nhầm hai cái khi trình bày.

**② Nội dung thread được gửi sang LLM bên thứ ba.** Trên server test toàn data giả thì không sao. Trên Discord thật của khoá thì đây là đúng thứ [README.md:92](../README.md#L92) dặn phải cẩn trọng — API free tier có thể dùng dữ liệu để huấn luyện. Mặc định `DISCORD_ANONYMIZE=1` đã thay tên người bằng hash, nhưng **nội dung câu hỏi vẫn đi nguyên văn**. Muốn dùng thật thì phải bật Zero Data Retention hoặc dùng endpoint trả phí có cam kết không train.
