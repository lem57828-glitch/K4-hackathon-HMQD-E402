"""Đổ 23 post trong data/qna_posts.json thành forum thật trên server test.

    python codebase/seed_forum.py --channel hỏi-đáp
    python codebase/seed_forum.py --channel hỏi-đáp --dry-run

Vì sao cần script này: bộ mock không phải data ngẫu nhiên — nó gài sẵn các bẫy
(nhãn `solved` nhưng thread chưa xong, cặp post gần trùng, câu hỏi ý kiến không
kết luận). Gõ tay 23 thread × 3-4 tin nhắn là mất cả buổi và gõ sai bẫy thì mất
luôn phần đáng demo nhất.

Cách làm: dùng **webhook** để mỗi tin nhắn hiện đúng tên người nói khác nhau —
bot thường chỉ đăng được dưới một danh tính. Tên webhook được đặt tiền tố
`TA_` / `LabCoach_` để `discord_bot.resolve_role()` suy lại đúng vai; role quyết
định hành vi thật (luật logistics ép confidence <= medium khi người trả lời chỉ
là học viên), không phải trang trí.

CHỈ CHẠY TRÊN SERVER TEST CỦA BẠN. Script này tạo thread mới, không xoá gì,
nhưng chạy hai lần thì có 46 post trùng nhau.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from env_loader import load_env  # noqa: E402

load_env()

try:
    import discord
except ImportError:
    raise SystemExit("Thieu discord.py. Chay:  pip install -r codebase/requirements-discord.txt")

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "qna_posts.json"
SOLVED_TAG = "Solved"
WEBHOOK_NAME = "qna-seeder"
PAUSE = 0.8  # giây giữa mỗi lần gửi, tránh rate limit


def webhook_username(author: str, role: str) -> str:
    """Tên phải mang tiền tố khớp resolve_role() trong discord_bot.py."""
    if role == "lab_coach":
        return author if author.lower().startswith("labcoach") else f"LabCoach_{author}"
    if role == "ta":
        return author if author.lower().startswith("ta_") else f"TA_{author}"
    return author


async def ensure_tags(channel: "discord.ForumChannel", wanted: list[str]) -> dict[str, object]:
    existing = {tag.name: tag for tag in channel.available_tags}
    missing = [name for name in wanted if name not in existing]
    if missing:
        print(f"  Tao {len(missing)} tag: {', '.join(missing)}")
        new_tags = list(channel.available_tags) + [discord.ForumTag(name=name) for name in missing]
        channel = await channel.edit(available_tags=new_tags)
        existing = {tag.name: tag for tag in channel.available_tags}
    return existing


async def wipe_threads(channel: "discord.ForumChannel") -> int:
    """Xoá sạch thread trong forum. Chỉ dùng trên server test."""
    targets = list(channel.threads)
    seen = {t.id for t in targets}
    async for thread in channel.archived_threads(limit=500):
        if thread.id not in seen:
            targets.append(thread)
            seen.add(thread.id)

    removed = 0
    for thread in targets:
        try:
            await thread.delete()
            removed += 1
            await asyncio.sleep(0.4)
        except discord.HTTPException as exc:
            print(f"    khong xoa duoc '{thread.name}': {exc}")
    return removed


async def seed(client: "discord.Client", channel_name: str, clean: bool, dry_run: bool) -> None:
    dataset = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    posts = dataset["posts"]
    vocabulary = list(dataset["tag_vocabulary"])

    channel = None
    for guild in client.guilds:
        for candidate in guild.channels:
            if candidate.name.lower() == channel_name.lower():
                channel = candidate
                break

    if channel is None:
        raise SystemExit(f"Khong tim thay channel '{channel_name}'. Tao Forum channel truoc da.")
    if not isinstance(channel, discord.ForumChannel):
        raise SystemExit(
            f"'{channel_name}' la {type(channel).__name__}, khong phai Forum channel.\n"
            "Tao channel kieu FORUM: Server -> + -> Forum."
        )

    print(f"  Server  : {channel.guild.name}")
    print(f"  Channel : #{channel.name}  (forum)")
    print(f"  Se tao  : {len(posts)} post · {sum(len(p['messages']) for p in posts)} tin nhan")

    existing = len(channel.threads)
    if existing and not clean:
        print(f"\n  ⚠ Forum dang co {existing}+ thread. Chay tiep se tao TRUNG.")
        print("    Muon xoa sach roi seed lai:  --clean\n")

    if dry_run:
        print("\n  --dry-run: khong ghi gi len Discord.\n")
        for post in posts:
            label = post.get("status_label") or "—"
            print(f"    {post['post_id']}  [{label:6s}] {post['title'][:60]}")
        return

    if clean:
        print("\n  Dang xoa thread cu...")
        removed = await wipe_threads(channel)
        print(f"  Da xoa {removed} thread.")

    tag_map = await ensure_tags(channel, vocabulary + [SOLVED_TAG])

    webhook = None
    for existing in await channel.webhooks():
        if existing.name == WEBHOOK_NAME:
            webhook = existing
            break
    if webhook is None:
        webhook = await channel.create_webhook(name=WEBHOOK_NAME)
        print(f"  Webhook : da tao '{WEBHOOK_NAME}'")

    print()
    for index, post in enumerate(posts, start=1):
        messages = post["messages"]
        starter = messages[0]
        username = webhook_username(starter["author"], starter["role"])

        applied = [tag_map[name] for name in post.get("tags", []) if name in tag_map]
        if post.get("status_label") == "solved" and SOLVED_TAG in tag_map:
            applied.append(tag_map[SOLVED_TAG])

        # Gắn tag ngay lúc tạo thread — Webhook.send nhận applied_tags cho forum,
        # khỏi phải thread.edit() sau (bớt 1 API call, bớt 1 chỗ hỏng).
        created = await webhook.send(
            content=post["body"][:1900],
            username=username,
            thread_name=post["title"][:100],
            applied_tags=applied[:5],
            wait=True,
        )

        # Message KHÔNG có .channel_id — phải lấy qua .channel.id.
        # Thread vừa tạo thường chưa vào cache nên dùng Object(id=...) cho tham
        # số thread=, không cần fetch về đối tượng Thread đầy đủ.
        thread = discord.Object(id=created.channel.id)

        for message in messages[1:]:
            await asyncio.sleep(PAUSE)
            await webhook.send(
                content=message["content"][:1900],
                username=webhook_username(message["author"], message["role"]),
                thread=thread,
            )

        for emoji in (post.get("reactions") or {}):
            try:
                await created.add_reaction(emoji)
            except discord.HTTPException:
                pass  # emoji lạ / thiếu quyền — không đáng dừng cả script

        label = post.get("status_label") or "—"
        print(f"  [{index:2d}/{len(posts)}] {post['post_id']} [{label:6s}] {post['title'][:52]}")
        await asyncio.sleep(PAUSE)

    print(f"\n  Xong. Chay bot:  python codebase/discord_bot.py\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed forum #hoi-dap tu mock data")
    parser.add_argument("--channel", default="hỏi-đáp", help="Ten forum channel")
    parser.add_argument("--dry-run", action="store_true", help="Chi in ra, khong ghi len Discord")
    parser.add_argument("--clean", action="store_true", help="Xoa sach thread cu truoc khi seed")
    args = parser.parse_args()

    token = __import__("os").getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("Thieu DISCORD_BOT_TOKEN trong codebase/.env")

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready() -> None:
        # discord.py NUỐT exception trong event handler và chỉ log qua logger.
        # Không bắt ở đây thì script chết im lặng, không traceback, không gì cả.
        try:
            await seed(client, args.channel, args.clean, args.dry_run)
        except Exception:
            import traceback
            print("\n===== LOI TRONG LUC SEED =====")
            traceback.print_exc()
        finally:
            await client.close()

    client.run(token, log_handler=None)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
