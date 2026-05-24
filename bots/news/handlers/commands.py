"""Public user-facing commands. Thin — all work goes through repos/services."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bots.news.config import BOT_TYPE
from bots.news.keyboards import main_menu
from shared.db import get_session
from shared.db.repositories import ArticleRepository
from shared.publishers.formatters import format_article_html
from shared.utils.text import truncate

router = Router(name="news.commands")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "سلام! به ربات اخبار خوش آمدید.\n"
        "از منوی زیر استفاده کنید یا /help را بزنید.",
        reply_markup=main_menu(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>راهنما</b>\n\n"
        "/latest — ۵ خبر آخر\n"
        "/start — منوی اصلی\n"
    )


@router.message(Command("latest"))
async def cmd_latest(message: Message) -> None:
    async with get_session() as session:
        articles = await ArticleRepository(session).latest_published(BOT_TYPE, limit=5)

    if not articles:
        await message.answer("هنوز خبری منتشر نشده است.")
        return

    for art in articles:
        text = format_article_html(art)
        await message.answer(truncate(text, 4000), disable_web_page_preview=False)
