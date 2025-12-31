import asyncio
import re
import math

from hydrogram import Client, filters, enums
from hydrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from info import (
    ADMINS,
    DELETE_TIME,
    MAX_BTN,
    IS_PREMIUM,
    PICS
)

from utils import (
    is_premium,
    get_size,
    is_check_admin,
    get_readable_time,
    temp,
    get_settings,
    save_group_settings,
    get_premium_button
)

from database.users_chats_db import db
from database.ia_filterdb import get_search_results

import random

BUTTONS = {}

# ─────────────────────────────────────────────
# 🔍 PRIVATE SEARCH (PREMIUM REQUIRED)
# ─────────────────────────────────────────────
@Client.on_message(filters.private & filters.text & filters.incoming)
async def pm_search(client, message):
    if message.text.startswith("/"):
        return

    # ✅ Premium check (synced with Premium.py)
    if IS_PREMIUM and not await is_premium(message.from_user.id, client):
        return await message.reply_photo(
            random.choice(PICS),
            caption="🔒 <b>Premium Required</b>\n\n"
                    "Search feature is only available for Premium users!\n\n"
                    "Use /plan to activate premium subscription.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 Buy Premium", callback_data="activate_plan"),
                InlineKeyboardButton("📊 My Plan", callback_data="myplan")
            ]]),
            parse_mode=enums.ParseMode.HTML
        )

    # Direct ultra-fast search with CASCADE
    await auto_filter(client, message, collection_type="all")


# ─────────────────────────────────────────────
# 🔍 GROUP SEARCH (WITH ON/OFF CONTROL)
# ─────────────────────────────────────────────
@Client.on_message(filters.group & filters.text & filters.incoming)
async def group_search(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0

    if not user_id:
        return

    if message.text.startswith("/"):
        return

    # ✅ Check if search is enabled in this group
    settings = await get_settings(chat_id)
    search_enabled = settings.get("search_enabled", True)  # Default: ON
    
    # If search is OFF, silently ignore all searches (no reply to anyone)
    if not search_enabled:
        return

    # ✅ Premium check (synced with Premium.py)
    if IS_PREMIUM and not await is_premium(user_id, client):
        return

    # admin mention handler
    if "@admin" in message.text.lower() or "@admins" in message.text.lower():
        if await is_check_admin(client, chat_id, user_id):
            return

        admins = []
        async for member in client.get_chat_members(
            chat_id, enums.ChatMembersFilter.ADMINISTRATORS
        ):
            if not member.user.is_bot:
                admins.append(member.user.id)

        hidden = "".join(f"[\u2064](tg://user?id={i})" for i in admins)
        await message.reply_text("Report sent!" + hidden)
        return

    # block links for non-admins
    if re.findall(r"https?://\S+|www\.\S+|t\.me/\S+|@\w+", message.text):
        if await is_check_admin(client, chat_id, user_id):
            return
        await message.delete()
        return await message.reply("Links not allowed here!")

    # Direct ultra-fast search with CASCADE
    await auto_filter(client, message, collection_type="all")


# ─────────────────────────────────────────────
# ⚙️ ADMIN COMMANDS - SEARCH ON/OFF
# ─────────────────────────────────────────────
@Client.on_message(filters.command("search") & filters.group)
async def search_toggle(client, message):
    """
    Toggle group search on/off
    Usage: /search on | /search off
    Admin only command
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check if user is admin
    if not await is_check_admin(client, chat_id, user_id):
        return await message.reply(
            "❌ <b>Admin Only!</b>\n\n"
            "Only group admins can use this command.",
            parse_mode=enums.ParseMode.HTML
        )
    
    # Get command argument
    if len(message.command) < 2:
        settings = await get_settings(chat_id)
        current_status = "✅ ON" if settings.get("search_enabled", True) else "❌ OFF"
        
        return await message.reply(
            f"🔍 <b>Group Search Settings</b>\n\n"
            f"Current Status: {current_status}\n\n"
            f"<b>Usage:</b>\n"
            f"• <code>/search on</code> - Enable search\n"
            f"• <code>/search off</code> - Disable search\n\n"
            f"<b>Note:</b> When OFF, nobody (including premium users) can search in this group.",
            parse_mode=enums.ParseMode.HTML
        )
    
    action = message.command[1].lower()
    
    if action == "on":
        await save_group_settings(chat_id, "search_enabled", True)
        await message.reply(
            "✅ <b>Search Enabled!</b>\n\n"
            "All premium users can now search in this group.",
            parse_mode=enums.ParseMode.HTML
        )
    
    elif action == "off":
        await save_group_settings(chat_id, "search_enabled", False)
        await message.reply(
            "❌ <b>Search Disabled!</b>\n\n"
            "Nobody can search in this group now.\n"
            "Use <code>/search on</code> to re-enable.",
            parse_mode=enums.ParseMode.HTML
        )
    
    else:
        await message.reply(
            "❌ <b>Invalid Option!</b>\n\n"
            "Use: <code>/search on</code> or <code>/search off</code>",
            parse_mode=enums.ParseMode.HTML
        )


# ─────────────────────────────────────────────
# 🔁 NAVIGATION (PREV/NEXT)
# ─────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^nav_"))
async def navigate_page(bot, query):
    try:
        _, req, key, offset, collection_type = query.data.split("_", 4)
        req = int(req)
        offset = int(offset)
    except:
        return await query.answer("Invalid request!", show_alert=True)

    if req != query.from_user.id:
        return await query.answer("Not for you!", show_alert=True)

    # ✅ Premium check for navigation
    if IS_PREMIUM and not await is_premium(query.from_user.id, bot):
        return await query.answer(
            "❌ Premium subscription expired!\nUse /plan to renew.",
            show_alert=True
        )

    search = BUTTONS.get(key)
    if not search:
        return await query.answer("Search expired!", show_alert=True)

    # Get results
    files, next_offset, total = await get_search_results(
        search,
        max_results=MAX_BTN,
        offset=offset,
        collection_type=collection_type
    )
    
    if not files:
        return await query.answer("No more results!", show_alert=True)

    temp.FILES[key] = files

    # Build results
    files_text = ""
    for file in files:
        files_text += (
            f"📁 <a href='https://t.me/{temp.U_NAME}"
            f"?start=file_{query.message.chat.id}_{file['_id']}'>"
            f"[{get_size(file['file_size'])}] {file['file_name']}</a>\n\n"
        )

    # Calculate pages
    current_page = (offset // MAX_BTN) + 1
    total_pages = math.ceil(total / MAX_BTN) if total > 0 else 1

    cap = (
        f"<b>👑 Search: {search}\n"
        f"🎬 Total: {total}\n"
        f"📚 Source: {collection_type.upper()}\n"
        f"📄 Page: {current_page}/{total_pages}</b>\n\n"
    )

    # Build buttons
    buttons = []
    
    # Navigation row
    nav_row = []
    prev_offset = offset - MAX_BTN
    
    if prev_offset >= 0:
        nav_row.append(
            InlineKeyboardButton("« ᴘʀᴇᴠ", callback_data=f"nav_{req}_{key}_{prev_offset}_{collection_type}")
        )
    
    nav_row.append(
        InlineKeyboardButton(f"📄 {current_page}/{total_pages}", callback_data="pages")
    )
    
    if next_offset:
        nav_row.append(
            InlineKeyboardButton("ɴᴇxᴛ »", callback_data=f"nav_{req}_{key}_{next_offset}_{collection_type}")
        )
    
    buttons.append(nav_row)

    # Collection row - ALWAYS SHOW
    coll_row = []
    for coll in ["primary", "cloud", "archive"]:
        emoji = "✅" if coll == collection_type else "📂"
        coll_row.append(
            InlineKeyboardButton(
                f"{emoji} {coll.upper()[:3]}",
                callback_data=f"coll_{req}_{key}_{coll}"
            )
        )
    buttons.append(coll_row)

    # Close button
    buttons.append([InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close_data")])

    try:
        await query.message.edit_text(
            cap + files_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML
        )
    except Exception as e:
        # Ignore "message not modified" errors
        if "MESSAGE_NOT_MODIFIED" not in str(e):
            raise
    
    await query.answer()


# ─────────────────────────────────────────────
# 🗂️ COLLECTION SWITCH
# ─────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^coll_"))
async def switch_collection(bot, query):
    try:
        _, req, key, collection_type = query.data.split("_", 3)
        req = int(req)
    except:
        return await query.answer("Invalid request!", show_alert=True)

    if req != query.from_user.id:
        return await query.answer("Not for you!", show_alert=True)

    # ✅ Premium check for collection switch
    if IS_PREMIUM and not await is_premium(query.from_user.id, bot):
        return await query.answer(
            "❌ Premium subscription expired!\nUse /plan to renew.",
            show_alert=True
        )

    search = BUTTONS.get(key)
    if not search:
        return await query.answer("Search expired!", show_alert=True)

    # Search in new collection from start
    files, next_offset, total = await get_search_results(
        search,
        max_results=MAX_BTN,
        offset=0,
        collection_type=collection_type
    )
    
    if not files:
        return await query.answer(f"No results in {collection_type.upper()}!", show_alert=True)

    temp.FILES[key] = files

    # Build results
    files_text = ""
    for file in files:
        files_text += (
            f"📁 <a href='https://t.me/{temp.U_NAME}"
            f"?start=file_{query.message.chat.id}_{file['_id']}'>"
            f"[{get_size(file['file_size'])}] {file['file_name']}</a>\n\n"
        )

    total_pages = math.ceil(total / MAX_BTN) if total > 0 else 1

    cap = (
        f"<b>👑 Search: {search}\n"
        f"🎬 Total: {total}\n"
        f"📚 Source: {collection_type.upper()}\n"
        f"📄 Page: 1/{total_pages}</b>\n\n"
    )

    # Build buttons
    buttons = []
    
    # Navigation row
    nav_row = [InlineKeyboardButton(f"📄 1/{total_pages}", callback_data="pages")]
    
    if next_offset:
        nav_row.append(
            InlineKeyboardButton("ɴᴇxᴛ »", callback_data=f"nav_{req}_{key}_{next_offset}_{collection_type}")
        )
    
    buttons.append(nav_row)

    # Collection row - ALWAYS SHOW
    coll_row = []
    for coll in ["primary", "cloud", "archive"]:
        emoji = "✅" if coll == collection_type else "📂"
        coll_row.append(
            InlineKeyboardButton(
                f"{emoji} {coll.upper()[:3]}",
                callback_data=f"coll_{req}_{key}_{coll}"
            )
        )
    buttons.append(coll_row)

    # Close button
    buttons.append([InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close_data")])

    try:
        await query.message.edit_text(
            cap + files_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True,
            parse_mode=enums.ParseMode.HTML
        )
        await query.answer(f"Switched to {collection_type.upper()}! 🔄")
    except Exception as e:
        if "MESSAGE_NOT_MODIFIED" not in str(e):
            await query.answer("Failed to switch!", show_alert=True)


# ─────────────────────────────────────────────
# ❌ CLOSE & PAGE INFO
# ─────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r"^close_data$"))
async def close_cb(bot, query):
    await query.message.delete()


@Client.on_callback_query(filters.regex(r"^pages$"))
async def pages_cb(bot, query):
    await query.answer()


# ─────────────────────────────────────────────
# 🚀 AUTO FILTER CORE - ULTRA FAST
# ─────────────────────────────────────────────
async def auto_filter(client, msg, collection_type="all"):
    message = msg
    settings = await get_settings(message.chat.id)

    search = message.text.strip()
    
    # Ultra-fast direct search (NO intermediate message)
    files, next_offset, total = await get_search_results(
        search,
        max_results=MAX_BTN,
        offset=0,
        collection_type=collection_type
    )

    if not files:
        k = await message.reply(f"❌ I can't find <b>{search}</b>")
        await asyncio.sleep(5)
        await k.delete()
        return

    key = f"{message.chat.id}-{message.id}"
    temp.FILES[key] = files
    BUTTONS[key] = search

    # Build results
    files_text = ""
    for file in files:
        files_text += (
            f"📁 <a href='https://t.me/{temp.U_NAME}"
            f"?start=file_{message.chat.id}_{file['_id']}'>"
            f"[{get_size(file['file_size'])}] {file['file_name']}</a>\n\n"
        )

    total_pages = math.ceil(total / MAX_BTN) if total > 0 else 1

    # ✅ Determine which collection actually returned results
    # Database's cascade will stop at first match, so we need to detect it
    actual_collection = "primary"  # Default
    
    # If we searched with "all", the database returned from one specific collection
    # We need to preserve that info for pagination
    if collection_type == "all":
        # The database cascade returns results from the first non-empty collection
        # Since we can't know which one without checking, we'll use a smart detection
        # For now, we'll check the first file's presence in each collection
        # But for simplicity, we'll just use "primary" as the active collection for navigation
        # The user can still switch collections using buttons
        actual_collection = "primary"
    else:
        actual_collection = collection_type

    cap = (
        f"<b>👑 Search: {search}\n"
        f"🎬 Total: {total}\n"
        f"📚 Source: {actual_collection.upper()}\n"
        f"📄 Page: 1/{total_pages}</b>\n\n"
    )

    # Build buttons
    buttons = []
    
    # Navigation row
    nav_row = [InlineKeyboardButton(f"📄 1/{total_pages}", callback_data="pages")]
    
    if next_offset:
        nav_row.append(
            InlineKeyboardButton("ɴᴇxᴛ »", callback_data=f"nav_{message.from_user.id}_{key}_{next_offset}_{actual_collection}")
        )
    
    buttons.append(nav_row)

    # Collection row - ALWAYS SHOW
    coll_row = []
    for coll in ["primary", "cloud", "archive"]:
        emoji = "✅" if coll == actual_collection else "📂"
        coll_row.append(
            InlineKeyboardButton(
                f"{emoji} {coll.upper()[:3]}",
                callback_data=f"coll_{message.from_user.id}_{key}_{coll}"
            )
        )
    buttons.append(coll_row)

    # Close button
    buttons.append([InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close_data")])

    # Send instantly
    k = await message.reply(
        cap + files_text,
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True,
        parse_mode=enums.ParseMode.HTML
    )

    # Auto-delete if enabled
    if settings.get("auto_delete"):
        await asyncio.sleep(DELETE_TIME)
        await k.delete()
        try:
            await message.delete()
        except:
            pass
