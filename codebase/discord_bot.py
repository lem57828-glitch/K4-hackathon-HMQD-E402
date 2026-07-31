"""Bot Discord — trợ lý #hỏi-đáp chạy trên forum thật.

    pip install -r codebase/requirements-discord.txt
    python codebase/discord_bot.py

Lệnh:
    /hoi        soạn câu hỏi -> trợ lý trả lời RIÊNG (ephemeral), chưa đăng gì lên forum
    /trangthai  xem index đang có bao nhiêu post, dựng lúc nào
    /reindex    quét lại forum (cần quyền Manage Server)

Vì sao là slash command chứ không phải bot tự rep:
    Lát cắt khai trong spec là "ngay lúc học viên ĐANG SOẠN post mới". Discord
    không có hook trước khi bấm đăng, nên `/hoi` là cách duy nhất giữ đúng thời
    điểm can thiệp: hỏi trước, thấy có post cũ trả lời rồi thì khỏi đăng.
    Bật DISCORD_AUTO_REPLY=1 sẽ chuyển sang chế độ rep sau khi đăng — tiện demo
    nhưng ĐÓ LÀ LÁT CẮT KHÁC, đừng nhầm hai cái khi trình bày.

Ba điều đáng chú ý về mặt kỹ thuật:
    1. Discord bắt trả lời interaction trong 3 giây, agent chạy 5-7 giây
       -> bắt buộc defer() trước rồi followup.send() sau.
    2. assistant.run() là blocking (urllib + time.sleep) -> phải asyncio.to_thread,
       không thì treo cả event loop, bot chết cứng với mọi người khác.
    3. Tên người mặc định được ẩn danh trước khi gửi sang LLM (DISCORD_ANONYMIZE).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from env_loader import load_env  # noqa: E402

load_env()
os.environ["QA_TOOL_BACKEND"] = "discord"  # phải set TRƯỚC khi import assistant

try:
    import discord
    from discord import app_commands
    from discord.ext import tasks
except ImportError:
    raise SystemExit(
        "Thieu discord.py. Chay:  pip install -r codebase/requirements-discord.txt"
    )

import tools_discord  # noqa: E402
from assistant import run  # noqa: E402
from provider import ChatProvider  # noqa: E402

# ---------------------------------------------------------------- cấu hình

TOKEN = os.getenv("DISCORD_BOT_TOKEN") or ""
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID") or 0)
CHANNEL_ID = int(os.getenv("DISCORD_QNA_CHANNEL_ID") or 0)
CHANNEL_NAME = os.getenv("DISCORD_QNA_CHANNEL_NAME", "hỏi-đáp")

TA_ROLES = {r.strip().lower() for r in (os.getenv("DISCORD_TA_ROLES") or "TA,Trợ giảng").split(",") if r.strip()}
COACH_ROLES = {r.strip().lower() for r in (os.getenv("DISCORD_LAB_COACH_ROLES") or "Lab Coach,Giảng viên,Mentor").split(",") if r.strip()}
SOLVED_TAGS = {t.strip().lower() for t in (os.getenv("DISCORD_SOLVED_TAGS") or "Solved,Đã giải quyết").split(",") if t.strip()}

ANONYMIZE = (os.getenv("DISCORD_ANONYMIZE") or "1") not in ("0", "false", "no")
AUTO_REPLY = (os.getenv("DISCORD_AUTO_REPLY") or "0") in ("1", "true", "yes")
REFRESH_MINUTES = max(1, int(os.getenv("DISCORD_INDEX_REFRESH_MIN") or 15))
MAX_THREADS = int(os.getenv("DISCORD_MAX_THREADS") or 300)
MAX_MESSAGES_PER_THREAD = int(os.getenv("DISCORD_MAX_MESSAGES") or 60)
MAX_CHARS_PER_MESSAGE = int(os.getenv("DISCORD_MAX_MSG_CHARS") or 1500)

COLORS = {
    "answer_from_post": 0x3FB950,
    "create_new_post": 0x58A6FF,
    "ask_clarify": 0xD29922,
    "refuse_out_of_scope": 0xF85149,
}
LABELS = {
    "answer_from_post": "✅ Đã có post cũ trả lời",
    "create_new_post": "📝 Nên đăng post mới",
    "ask_clarify": "❓ Cần thêm thông tin",
    "refuse_out_of_scope": "⛔ Ngoài phạm vi trợ lý",
}
RESOLUTION_ICON = {"resolved": "✅", "in_progress": "🟡", "unclear": "⬜"}

# ---------------------------------------------------------------- tiện ích


def cut(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def resolve_role(message: "discord.Message") -> str:
    """Xác định vai người nói. Quan trọng về mặt hành vi, không phải trang trí:
    luật logistics trong system prompt ép confidence <= medium khi câu trả lời
    do học viên nói chứ không phải TA/Lab Coach."""
    if message.webhook_id:
        # Data seed bằng webhook (seed_forum.py) — suy vai từ tiền tố tên.
        name = (message.author.name or "").lower()
        if name.startswith("labcoach"):
            return "lab_coach"
        if name.startswith("ta_"):
            return "ta"
        return "student"

    role_names = {role.name.lower() for role in getattr(message.author, "roles", [])}
    if role_names & COACH_ROLES:
        return "lab_coach"
    if role_names & TA_ROLES:
        return "ta"
    return "student"


def display_author(message: "discord.Message", role: str) -> str:
    if not ANONYMIZE:
        return message.author.display_name
    digest = hashlib.sha1(str(message.author.id).encode()).hexdigest()[:4]
    prefix = {"ta": "TA", "lab_coach": "LabCoach", "student": "hocvien"}[role]
    return f"{prefix}_{digest}"


def iso(moment: datetime | None) -> str:
    return (moment or datetime.now(timezone.utc)).isoformat()


# ---------------------------------------------------------------- dựng index


async def collect_threads(channel) -> list:
    threads = list(getattr(channel, "threads", []))
    seen = {thread.id for thread in threads}
    try:
        async for thread in channel.archived_threads(limit=MAX_THREADS):
            if thread.id not in seen:
                threads.append(thread)
                seen.add(thread.id)
    except (discord.Forbidden, AttributeError):
        # Thiếu Read Message History, hoặc text channel không có archived_threads.
        pass
    return threads[:MAX_THREADS]


async def build_index(channel) -> dict:
    """Quét forum -> list post cùng cấu trúc với data/qna_posts.json."""
    available = [tag.name for tag in getattr(channel, "available_tags", [])]
    vocabulary = [name for name in available if name.lower() not in SOLVED_TAGS]

    threads = await collect_threads(channel)
    threads.sort(key=lambda t: t.created_at or datetime.now(timezone.utc))

    posts: list[dict] = []
    skipped = 0
    for offset, thread in enumerate(threads):
        try:
            history = [m async for m in thread.history(limit=MAX_MESSAGES_PER_THREAD, oldest_first=True)]
        except discord.Forbidden:
            skipped += 1
            continue

        # Bỏ tin của chính bot — trả lời của trợ lý không phải bằng chứng.
        history = [m for m in history if not m.author.bot or m.webhook_id]
        if not history:
            skipped += 1
            continue

        applied = [tag.name for tag in getattr(thread, "applied_tags", [])]
        status_label = "solved" if {t.lower() for t in applied} & SOLVED_TAGS else None
        tags = [name for name in applied if name.lower() not in SOLVED_TAGS]

        messages = []
        for message in history:
            role = resolve_role(message)
            messages.append({
                "author": display_author(message, role),
                "role": role,
                "at": iso(message.created_at),
                "content": cut(message.content, MAX_CHARS_PER_MESSAGE),
            })

        starter = history[0]
        reactions = {str(r.emoji): r.count for r in starter.reactions} if starter.reactions else {}

        posts.append({
            # ID ngắn, đánh số theo thứ tự tạo thread. Cố tình KHÔNG dùng snowflake
            # 19 chữ số: model phải đọc lại id để gọi read_post_thread, số dài dễ gõ sai.
            "post_id": f"P-{1001 + offset}",
            "thread_id": thread.id,
            "url": f"https://discord.com/channels/{channel.guild.id}/{thread.id}",
            "title": thread.name,
            "body": cut(starter.content, MAX_CHARS_PER_MESSAGE),
            "author": messages[0]["author"],
            "created_at": iso(thread.created_at),
            "tags": tags,
            "status_label": status_label,
            "reactions": reactions,
            "messages": messages,
        })

    tools_discord.set_index(
        posts,
        vocabulary or tools_discord.DEFAULT_TAGS,
        guild_id=channel.guild.id,
        channel_id=channel.id,
        built_at=iso(datetime.now(timezone.utc)),
    )
    return {"posts": len(posts), "skipped": skipped, "tags": vocabulary}


# ---------------------------------------------------------------- embed


def build_embed(result) -> "discord.Embed":
    if not result.ok:
        embed = discord.Embed(
            title="⚠️ Trợ lý gặp lỗi",
            description=cut(result.error or "Không rõ lỗi", 3000),
            color=0xF85149,
        )
        embed.set_footer(text="Lỗi được hiện nguyên văn, không che.")
        return embed

    out = result.output
    decision = out["decision"]
    body = out.get("answer") or out.get("clarify_question") or "—"

    embed = discord.Embed(
        title=LABELS.get(decision, decision),
        description=cut(body, 3500),
        color=COLORS.get(decision, 0x808080),
    )

    for source in (out.get("sources") or [])[:3]:
        icon = RESOLUTION_ICON.get(source["resolution"], "⬜")
        embed.add_field(
            name=f"{icon} {source['post_id']} · {source['resolution']}",
            value=cut(f"[{source['title']}]({source['url']})\n{source.get('why', '')}", 1000),
            inline=False,
        )

    draft = out.get("draft_post")
    if draft:
        embed.add_field(
            name="📝 Post nháp gợi ý",
            value=cut(f"**{draft['title']}**\n{draft['body']}", 1000),
            inline=False,
        )

    if out.get("suggested_tags"):
        embed.add_field(name="🏷️ Tag", value=" · ".join(out["suggested_tags"]), inline=True)

    embed.add_field(name="📊 Độ tin cậy", value=out.get("confidence", "?"), inline=True)

    if out.get("next_step"):
        embed.add_field(name="→ Bước tiếp", value=cut(out["next_step"], 1000), inline=False)

    if out.get("warnings"):
        embed.add_field(
            name=f"⚠️ Cảnh báo hợp đồng output ({len(out['warnings'])})",
            value=cut("\n".join(f"• {w}" for w in out["warnings"]), 1000),
            inline=False,
        )

    trace = result.trace
    embed.set_footer(
        text=f"{trace.model} · {trace.latency_ms} ms · {len(trace.tool_calls)} tool call"
        + (" · đã phải sửa JSON" if trace.repair_used else "")
    )
    return embed


# ---------------------------------------------------------------- bot

intents = discord.Intents.default()
intents.message_content = True   # privileged — đọc nội dung thread
intents.members = True           # privileged — đọc role để phân biệt TA / học viên

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

_channel = None


async def find_channel() -> object | None:
    if CHANNEL_ID:
        channel = client.get_channel(CHANNEL_ID)
        if channel:
            return channel
        try:
            return await client.fetch_channel(CHANNEL_ID)
        except discord.HTTPException:
            return None
    for guild in client.guilds:
        for channel in guild.channels:
            if channel.name.lower() == CHANNEL_NAME.lower():
                return channel
    return None


@tasks.loop(minutes=REFRESH_MINUTES)
async def refresh_index() -> None:
    global _channel
    if _channel is None:
        _channel = await find_channel()
    if _channel is None:
        print(f"  [index] chua tim thay channel '{CHANNEL_NAME}'")
        return
    try:
        stats = await build_index(_channel)
        print(f"  [index] {stats['posts']} post · bo qua {stats['skipped']} · tag={stats['tags']}")
    except discord.Forbidden as exc:
        print(f"  [index] THIEU QUYEN: {exc}")


@client.event
async def on_ready() -> None:
    print(f"\n  Bot     : {client.user}")
    print(f"  Server  : {', '.join(g.name for g in client.guilds) or 'chua vao server nao'}")
    print(f"  Model   : {ChatProvider().model}")
    print(f"  An danh : {'BAT' if ANONYMIZE else 'TAT'}")

    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        print("  Lenh    : da sync rieng cho guild (hien ngay)")
    else:
        await tree.sync()
        print("  Lenh    : sync global (Discord co the mat toi 1 gio moi hien)")

    if not refresh_index.is_running():
        refresh_index.start()
    print(f"\n  San sang. /hoi de dung.  Auto-reply: {'BAT' if AUTO_REPLY else 'TAT'}\n")


@tree.command(name="hoi", description="Hỏi trợ lý trước khi đăng post mới — chỉ bạn thấy câu trả lời")
@app_commands.describe(
    noi_dung="Nội dung câu hỏi bạn định đăng",
    tieu_de="Tiêu đề dự kiến (không bắt buộc)",
)
async def hoi(interaction: "discord.Interaction", noi_dung: str, tieu_de: str = "") -> None:
    # Discord chỉ cho 3 giây để phản hồi, agent chạy 5-7 giây -> defer ngay.
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        result = await asyncio.to_thread(run, tieu_de, noi_dung)
    except Exception as exc:  # noqa: BLE001 — lỗi lạ vẫn phải hiện, không nuốt
        await interaction.followup.send(f"⚠️ `{type(exc).__name__}`: {exc}", ephemeral=True)
        return
    await interaction.followup.send(embed=build_embed(result), ephemeral=True)


@tree.command(name="trangthai", description="Xem index trợ lý đang đọc được bao nhiêu post")
async def trangthai(interaction: "discord.Interaction") -> None:
    stats = tools_discord.index_stats()
    embed = discord.Embed(title="📊 Trạng thái index", color=0x58A6FF)
    embed.add_field(name="Nguồn", value=stats["source"], inline=True)
    embed.add_field(name="Số post", value=str(stats["post_count"]), inline=True)
    embed.add_field(name="Số tin nhắn", value=str(stats["message_count"]), inline=True)
    embed.add_field(name="Gắn nhãn solved", value=str(stats["solved_label_count"]), inline=True)
    embed.add_field(name="Tag", value=" · ".join(stats["tag_vocabulary"]) or "—", inline=False)
    embed.set_footer(text=f"Dựng lúc {stats['built_at'] or '—'} · làm mới mỗi {REFRESH_MINUTES} phút")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="reindex", description="Quét lại forum ngay (cần quyền Manage Server)")
async def reindex(interaction: "discord.Interaction") -> None:
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("Lệnh này cần quyền Manage Server.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    global _channel
    _channel = await find_channel()
    if _channel is None:
        await interaction.followup.send(f"Không tìm thấy channel `{CHANNEL_NAME}`.", ephemeral=True)
        return
    stats = await build_index(_channel)
    await interaction.followup.send(
        f"✅ Đã quét lại: **{stats['posts']} post**, bỏ qua {stats['skipped']}.", ephemeral=True
    )


@client.event
async def on_thread_create(thread: "discord.Thread") -> None:
    if _channel is None or thread.parent_id != _channel.id:
        return
    await asyncio.sleep(3)  # chờ starter message xuất hiện
    await build_index(_channel)

    if not AUTO_REPLY:
        return
    # CHÚ Ý: đây là lát cắt KHÁC với /hoi — trả lời SAU khi đã đăng, công khai.
    try:
        starter = await thread.fetch_message(thread.id)
        result = await asyncio.to_thread(run, thread.name, starter.content)
        await thread.send(embed=build_embed(result))
    except Exception as exc:  # noqa: BLE001
        print(f"  [auto-reply] loi: {type(exc).__name__}: {exc}")


def main() -> None:
    if not TOKEN:
        raise SystemExit(
            "Thieu DISCORD_BOT_TOKEN trong codebase/.env\n"
            "Xem huong dan: codebase/SETUP-DISCORD.md"
        )
    client.run(TOKEN, log_handler=None)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
