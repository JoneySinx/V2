import asyncio
import re
import math
from time import time as time_now
from datetime import datetime, timedelta

from hydrogram import Client, filters, enums
from hydrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InputMediaPhoto
)

from Script import script
from info import (
    PICS, ADMINS, LOG_CHANNEL, DELETE_TIME,
    MAX_BTN, BIN_CHANNEL, URL
)

from utils import (
    is_premium,
    get_size,
    is_check_admin,
    get_wish,
    get_readable_time,
    temp,
    get_settings,
    save_group_settings,
    is_subscribed
)

from database.users_chats_db import db
from database.ia_filterdb import (
    get_search_results,
    delete_files,
    db_count_documents
)

from plugins.commands import get_grp_stg

BUTTONS = {}
CAP = {}

# ─────────────────────────────────────────────
# 🔍 PRIVATE SEARCH
# ─────────────────────────────────────────────
@Client.on_message(filters.private & filters.text & filters.incoming)
async def pm_search(client, message):
    if message.text.startswith("/"):
        return

    if not await is_premium(message.from_user.id, client) and message.from_user.id not in ADMINS:
        return await message.reply_text(
            "❌ This bot is only for Premium users and Admins!"
        )

    stg = db.get_bot_sttgs()
    if not stg.get("PM_SEARCH"):
        return await message.reply_text("PM search was disabled!")

    if not stg.get("AUTO_FILTER"):
        return await message.reply_text("Auto filter was disabled!")

    s = await message.reply(
        f"<b><i>⚠️ `{message.text}` searching...</i></b>",
        quote=True
    )
    await auto_filter(client, message, s)

# ─────────────────────────────────────────────
# 🔍 GROUP SEARCH
# ─────────────────────────────────────────────
@Client.on_message(filters.group & filters.text & filters.incoming)
async def group_search(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    stg = db.get_bot_sttgs()

    if not stg.get("AUTO_FILTER"):
        return

    if not user_id:
        return await message.reply("I'm not working for anonymous admin!")

    if not await is_premium(user_id, client) and user_id not in ADMINS:
        return

    if message.text.startswith("/"):
        return

    # admin mention handler
    if "@admin" in message.text.lower() or "@admins" in message.text.lower():
        if await is_check_admin(client, chat_id, user_id):
            return

        admins = []
        async for member in client.get_chat_members(chat_id, enums.ChatMembersFilter.ADMINISTRATORS):
            if not member.user.is_bot:
                admins.append(member.user.id)

        hidden = "".join(f"[\u2064](tg://user?id={i})" for i in admins)
        await message.reply_text("Report sent!" + hidden)
        return

    # block links
    if re.findall(r"https?://\S+|www\.\S+|t\.me/\S+|@\w+", message.text):
        if await is_check_admin(client, chat_id, user_id):
            return
        await message.delete()
        return await message.reply("Links not allowed here!")

    s = await message.reply(
        f"<b><i>⚠️ `{message.text}` searching...</i></b>"
    )
    await auto_filter(client, message, s)

# ─────────────────────────────────────────────
# 📂 COLLECTION FILTER
# ─────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^coll_filter"))
async def collection_filter(bot, query):
    _, coll_type, key, req, offset = query.data.split("#")

    if int(req) != query.from_user.id:
        return await query.answer("Not for you!", show_alert=True)

    search = BUTTONS.get(key)
    if not search:
        return await query.answer("Send new request!", show_alert=True)

    files, n_offset, total = await get_search_results(
        search, collection_type=coll_type
    )

    if not files:
        return await query.answer("No files found!", show_alert=True)

    temp.FILES[key] = files
    settings = await get_settings(query.message.chat.id)

    files_text = ""
    for file in files:
        files_text += (
            f"📁 <a href='https://t.me/{temp.U_NAME}"
            f"?start=file_{query.message.chat.id}_{file['_id']}'>"
            f"[{get_size(file['file_size'])}] {file['file_name']}</a>\n\n"
        )

    cap = (
        f"<b>👑 Search: {search}\n"
        f"📚 Collection: {coll_type.title()}\n"
        f"🎬 Total Files: {total}\n"
        f"📄 Page: 1 / {math.ceil(total / MAX_BTN) if total else 1}</b>\n\n"
    )

    btn = []
    if n_offset not in ("", None):
        btn.append([
            InlineKeyboardButton("ɴᴇxᴛ »", callback_data=f"coll_next#{coll_type}#{key}#{req}#{n_offset}")
        ])

    btn.append([InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close_data")])

    await query.message.edit_text(
        cap + files_text,
        reply_markup=InlineKeyboardMarkup(btn),
        disable_web_page_preview=True,
        parse_mode=enums.ParseMode.HTML
    )

# ─────────────────────────────────────────────
# 🔁 NEXT PAGE
# ─────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^next"))
async def next_page(bot, query):
    _, req, key, offset = query.data.split("_")

    if int(req) != query.from_user.id:
        return await query.answer("Not for you!", show_alert=True)

    try:
        offset = int(offset)
    except:
        offset = 0

    search = BUTTONS.get(key)
    cap = CAP.get(key)

    files, n_offset, total = await get_search_results(search, offset=offset)
    if not files:
        return

    temp.FILES[key] = files

    files_text = ""
    for file in files:
        files_text += (
            f"📁 <a href='https://t.me/{temp.U_NAME}"
            f"?start=file_{query.message.chat.id}_{file['_id']}'>"
            f"[{get_size(file['file_size'])}] {file['file_name']}</a>\n\n"
        )

    btn = []
    if n_offset not in ("", None):
        btn.append([
            InlineKeyboardButton("ɴᴇxᴛ »", callback_data=f"next_{req}_{key}_{n_offset}")
        ])

    btn.append([InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close_data")])

    await query.message.edit_text(
        cap + "\n\n" + files_text,
        reply_markup=InlineKeyboardMarkup(btn),
        disable_web_page_preview=True,
        parse_mode=enums.ParseMode.HTML
    )

# ─────────────────────────────────────────────
# ❌ CLOSE
# ─────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^close_data$"))
async def close_cb(bot, query):
    await query.message.delete()

# ─────────────────────────────────────────────
# 🚀 AUTO FILTER CORE
# ─────────────────────────────────────────────
async def auto_filter(client, msg, s):
    message = msg
    settings = await get_settings(message.chat.id)

    search = message.text.strip()
    files, offset, total = await get_search_results(search)

    if not files:
        return await s.edit(f"❌ I can't find <b>{search}</b>")

    key = f"{message.chat.id}-{message.id}"
    temp.FILES[key] = files
    BUTTONS[key] = search

    files_text = ""
    for file in files:
        files_text += (
            f"📁 <a href='https://t.me/{temp.U_NAME}"
            f"?start=file_{message.chat.id}_{file['_id']}'>"
            f"[{get_size(file['file_size'])}] {file['file_name']}</a>\n\n"
        )

    cap = (
        f"<b>👑 Search: {search}\n"
        f"🎬 Total Files: {total}\n"
        f"📄 Page: 1 / {math.ceil(total / MAX_BTN)}</b>\n\n"
    )
    CAP[key] = cap

    btn = []
    if offset not in ("", None):
        btn.append([
            InlineKeyboardButton("ɴᴇxᴛ »", callback_data=f"next_{message.from_user.id}_{key}_{offset}")
        ])

    btn.append([InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close_data")])

    k = await s.edit_text(
        cap + files_text,
        reply_markup=InlineKeyboardMarkup(btn),
        disable_web_page_preview=True,
        parse_mode=enums.ParseMode.HTML
    )

    if settings.get("auto_delete"):
        await asyncio.sleep(DELETE_TIME)
        await k.delete()
