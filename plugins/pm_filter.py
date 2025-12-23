import asyncio
import re
import math
from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from utils import get_size, is_check_admin, get_readable_time, temp
from database.ia_filterdb import get_search_results
from info import ADMINS, MAX_BTN, DELETE_TIME

BUTTONS = {}
FILES_CACHE = {}


# ─────────────────────────────────────
# PM SEARCH (ADMIN ONLY)
# ─────────────────────────────────────
@Client.on_message(filters.private & filters.text & filters.incoming)
async def pm_search(client, message):
    if message.from_user.id not in ADMINS:
        return await message.reply_text("❌ This bot is admin-only.")

    s = await message.reply(
        f"<b><i>🔍 Searching for:</i></b> <code>{message.text}</code>"
    )
    await auto_filter(client, message, s)


# ─────────────────────────────────────
# GROUP SEARCH (ADMIN ONLY)
# ─────────────────────────────────────
@Client.on_message(filters.group & filters.text & filters.incoming)
async def group_search(client, message):
    user_id = message.from_user.id if message.from_user else 0

    if not await is_check_admin(client, message.chat.id, user_id):
        return

    if message.text.startswith("/"):
        return

    s = await message.reply(
        f"<b><i>🔍 Searching for:</i></b> <code>{message.text}</code>"
    )
    await auto_filter(client, message, s)


# ─────────────────────────────────────
# AUTO FILTER CORE
# ─────────────────────────────────────
async def auto_filter(client, message, s):
    search = re.sub(r"\s+", " ", message.text).strip()
    files, offset, total = await get_search_results(search)

    if not files:
        return await s.edit("❌ No results found.")

    key = f"{message.chat.id}-{message.id}"
    FILES_CACHE[key] = files
    BUTTONS[key] = search

    btn = build_buttons(files, key, offset, total, message.from_user.id)

    await s.edit_text(
        f"<b>📂 Results for:</b> <code>{search}</code>",
        reply_markup=InlineKeyboardMarkup(btn),
        disable_web_page_preview=True
    )

    if DELETE_TIME:
        await asyncio.sleep(DELETE_TIME)
        try:
            await s.delete()
            await message.delete()
        except:
            pass


# ─────────────────────────────────────
# BUTTON BUILDER
# ─────────────────────────────────────
def build_buttons(files, key, offset, total, user_id):
    btn = [[
        InlineKeyboardButton(
            text=f"{get_size(f['file_size'])} - {f['file_name']}",
            callback_data=f"file#{f['_id']}"
        )
    ] for f in files]

    if offset:
        btn.append([
            InlineKeyboardButton(
                text="« Back",
                callback_data=f"next_{user_id}_{key}_{offset - MAX_BTN}"
            ),
            InlineKeyboardButton(
                text=f"{math.ceil(offset / MAX_BTN)}/{math.ceil(total / MAX_BTN)}",
                callback_data="noop"
            ),
            InlineKeyboardButton(
                text="Next »",
                callback_data=f"next_{user_id}_{key}_{offset}"
            )
        ])

    return btn


# ─────────────────────────────────────
# PAGINATION
# ─────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^next_"))
async def next_page(client, query: CallbackQuery):
    _, req, key, offset = query.data.split("_")

    if int(req) != query.from_user.id:
        return await query.answer("❌ Not for you.", show_alert=True)

    try:
        offset = int(offset)
    except:
        offset = 0

    search = BUTTONS.get(key)
    if not search:
        return await query.answer("⚠️ Request expired.", show_alert=True)

    files, new_offset, total = await get_search_results(search, offset=offset)
    FILES_CACHE[key] = files

    btn = build_buttons(files, key, new_offset, total, req)

    await query.message.edit_reply_markup(
        reply_markup=InlineKeyboardMarkup(btn)
    )


# ─────────────────────────────────────
# FILE BUTTON
# ─────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^file#"))
async def file_handler(client, query: CallbackQuery):
    _, file_id = query.data.split("#")

    try:
        user = query.message.reply_to_message.from_user.id
    except:
        user = query.from_user.id

    if query.from_user.id != user:
        return await query.answer("❌ Not for you.", show_alert=True)

    await query.answer(
        url=f"https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file_id}"
    )


# ─────────────────────────────────────
# NO-OP CALLBACK
# ─────────────────────────────────────
@Client.on_callback_query(filters.regex("^noop$"))
async def noop(_, query):
    await query.answer()
