"""Admin commands — only available to ids listed in ADMIN_IDS env var."""

from __future__ import annotations

from datetime import timedelta

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bots.news.config import BOT_TYPE
from shared.config import get_settings
from shared.db import get_session
from shared.db.repositories import (
    ArticleRepository,
    SourceRepository,
    UserRepository,
)
from shared.utils.text import escape_html
from shared.utils.time import utcnow

router = Router(name="news.admin")


def _is_admin(user_id: int) -> bool:
    return user_id in set(get_settings().admin_ids)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return

    day_start = utcnow() - timedelta(days=1)
    async with get_session() as session:
        art_counts = await ArticleRepository(session).count_today(BOT_TYPE, day_start)
        active = await UserRepository(session).count_active(BOT_TYPE, day_start)
        sources = await SourceRepository(session).list_all(BOT_TYPE)

    enabled_count = sum(1 for s in sources if s.enabled)
    lines = [
        "<b>📊 آمار ۲۴ ساعت اخیر</b>",
        f"• دریافت‌شده: {sum(art_counts.values())}",
        f"  - منتشرشده: {art_counts.get('published', 0)}",
        f"  - خلاصه‌شده: {art_counts.get('summarized', 0)}",
        f"  - ناموفق: {art_counts.get('failed', 0)}",
        f"• کاربران فعال: {active}",
        f"• منابع فعال: {enabled_count}/{len(sources)}",
    ]
    await message.answer("\n".join(lines))


@router.message(Command("add_source"))
async def cmd_add_source(message: Message, command: CommandObject) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    arg = (command.args or "").strip()
    if not arg:
        await message.answer("استفاده: <code>/add_source @username</code> یا <code>/add_source -100123...</code>")
        return
    async with get_session() as session:
        row = await SourceRepository(session).add(BOT_TYPE, arg)
    await message.answer(f"✅ منبع اضافه شد: <code>{escape_html(row.channel_username_or_id)}</code>")


@router.message(Command("list_sources"))
async def cmd_list_sources(message: Message) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    async with get_session() as session:
        sources = await SourceRepository(session).list_all(BOT_TYPE)
    if not sources:
        await message.answer("هیچ منبعی ثبت نشده است.")
        return
    lines = ["<b>منابع:</b>"]
    for s in sources:
        marker = "🟢" if s.enabled else "🔴"
        label = escape_html(s.title or s.channel_username_or_id)
        lines.append(f"{marker} <code>{s.id}</code> — {label}")
    await message.answer("\n".join(lines))


@router.message(Command("toggle_source"))
async def cmd_toggle_source(message: Message, command: CommandObject) -> None:
    if not message.from_user or not _is_admin(message.from_user.id):
        return
    import uuid as _uuid

    arg = (command.args or "").strip()
    try:
        source_id = _uuid.UUID(arg)
    except ValueError:
        await message.answer("استفاده: <code>/toggle_source &lt;uuid&gt;</code>")
        return

    async with get_session() as session:
        repo = SourceRepository(session)
        row = await repo.get(source_id)
        if row is None:
            await message.answer("منبع یافت نشد.")
            return
        await repo.set_enabled(source_id, not row.enabled)
    await message.answer("🟢 فعال شد." if not row.enabled else "🔴 غیرفعال شد.")
