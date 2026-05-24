"""Inline keyboard callbacks."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bots.news.config import BOT_TYPE
from bots.news.keyboards import back_to_menu, main_menu
from shared.db import get_session
from shared.db.repositories import ArticleRepository
from shared.publishers.formatters import format_article_html
from shared.utils.text import truncate

router = Router(name="news.callbacks")


@router.callback_query(F.data == "news:menu")
async def cb_menu(cb: CallbackQuery) -> None:
    if cb.message:
        await cb.message.edit_text("منوی اصلی:", reply_markup=main_menu())
    await cb.answer()


@router.callback_query(F.data == "news:help")
async def cb_help(cb: CallbackQuery) -> None:
    if cb.message:
        await cb.message.edit_text(
            "<b>راهنما</b>\n\n"
            "از /latest برای دیدن آخرین خبرها استفاده کنید.",
            reply_markup=back_to_menu(),
        )
    await cb.answer()


@router.callback_query(F.data == "news:latest")
async def cb_latest(cb: CallbackQuery) -> None:
    async with get_session() as session:
        articles = await ArticleRepository(session).latest_published(BOT_TYPE, limit=5)
    await cb.answer()

    if not articles or cb.message is None:
        if cb.message:
            await cb.message.answer("هنوز خبری منتشر نشده است.")
        return

    for art in articles:
        text = format_article_html(art)
        await cb.message.answer(truncate(text, 4000))
