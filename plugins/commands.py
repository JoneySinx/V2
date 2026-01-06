import os
import random
import asyncio
from datetime import datetime
from time import time as time_now
from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Script import script
# Note: Media is imported but not used for search logic anymore
from database.ia_filterdb import db_count_documents, get_file_details, delete_files
from database.users_chats_db import db

from info import (
    IS_PREMIUM, URL, BIN_CHANNEL, STICKERS, ADMINS, 
    LOG_CHANNEL, PICS, IS_STREAM, REACTIONS, PM_FILE_DELETE_TIME
)
from utils import (
    is_premium, get_settings, get_size, temp, 
    get_readable_time, get_wish
)

# ─────────────────────────
# HELPERS
# ─────────────────────────
async def del_stk(s):
    await asyncio.sleep(3)
    try: await s.delete()
    except: pass

async def auto_delete_messages(msg_ids, chat_id, client, delay):
    await asyncio.sleep(delay)
    try: await client.delete_messages(chat_id=chat_id, message_ids=msg_ids)
    except: pass

# ─────────────────────────
# /start COMMAND
# ─────────────────────────
@Client.on_message(filters.command("start") & filters.incoming)
async def start(client, message):
    
    # 1. GROUP HANDLING
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        if not await db.get_chat(message.chat.id):
            total = await client.get_chat_members_count(message.chat.id)
            user = message.chat.username or "Private"
            await client.send_message(
                LOG_CHANNEL,
                script.NEW_GROUP_TXT.format(message.chat.title, message.chat.id, f"@{user}", total)
            )
            await db.add_chat(message.chat.id, message.chat.title)
        return await message.reply(
            f"<b>Hey {message.from_user.mention}, <i>{get_wish()}</i>\nHow can I help you?</b>"
        )

    # 2. PRIVATE HANDLING
    if REACTIONS:
        try: await message.react(random.choice(REACTIONS), big=True)
        except: pass
    if STICKERS:
        try:
            stk = await client.send_sticker(message.chat.id, random.choice(STICKERS))
            asyncio.create_task(del_stk(stk))
        except: pass

    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        await client.send_message(
            LOG_CHANNEL,
            script.NEW_USER_TXT.format(message.from_user.mention, message.from_user.id)
        )

    if IS_PREMIUM and not await is_premium(message.from_user.id, client):
        return await message.reply_photo(
            random.choice(PICS),
            caption="🔒 **Premium Required**\n\nBot is only for Premium users.\nUse /plan to buy.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💎 Buy Premium", callback_data="activate_plan")]])
        )

    # 3. FILE HANDLING (start=file_id)
    if len(message.command) > 1 and message.command[1] != "premium":
        try:
            data = message.command[1]
            parts = data.split("_")
            
            if len(parts) >= 3:
                try: await message.delete()
                except: pass
                
                grp_id = int(parts[1])
                file_id = parts[2]
                
                # 🔥 FIXED: Use the robust get_file_details from ia_filterdb
                file = await get_file_details(file_id)
                
                if not file:
                    return await message.reply("❌ **File Not Found!**\n\nThe file may have been deleted or the link is invalid.")
                
                settings = await get_settings(grp_id)
                cap_template = settings.get('caption', '{file_name}\n\n💾 Size: {file_size}')
                
                caption = cap_template.format(
                    file_name=file.get('file_name', 'File'),
                    file_size=get_size(file.get('file_size', 0)),
                    file_caption=file.get('caption', '')
                )
                
                btn = [[InlineKeyboardButton('❌ Close', callback_data='close_data')]]
                if IS_STREAM:
                    # Use str(_id) to ensure it works for both string and ObjectId
                    btn.insert(0, [InlineKeyboardButton("▶️ Watch / Download", callback_data=f"stream#{str(file['_id'])}")])

                msg = await client.send_cached_media(
                    chat_id=message.chat.id,
                    file_id=file['file_id'],
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(btn)
                )

                if PM_FILE_DELETE_TIME > 0:
                    del_msg = await msg.reply(
                        f"⚠️ This message will delete in {get_readable_time(PM_FILE_DELETE_TIME)}."
                    )
                    asyncio.create_task(
                        auto_delete_messages([msg.id, del_msg.id], message.chat.id, client, PM_FILE_DELETE_TIME)
                    )
                    if not hasattr(temp, 'PM_FILES'): temp.PM_FILES = {}
                    temp.PM_FILES[msg.id] = {'file_msg': msg.id, 'note_msg': del_msg.id}
                return

        except Exception as e:
            print(f"Start Error: {e}")
            return await message.reply("❌ Error fetching file.")

    # 4. DEFAULT START MESSAGE
    await message.reply_photo(
        random.choice(PICS),
        caption=script.START_TXT.format(message.from_user.mention, get_wish()),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👨‍🚒 Help", callback_data="help")]
        ])
    )

# ─────────────────────────
# /link COMMAND
# ─────────────────────────
@Client.on_message(filters.command("link") & filters.incoming)
async def link_command(client, message):
    if not message.reply_to_message:
        return await message.reply("⚠️ Reply to a file.")
    
    reply = message.reply_to_message
    media = reply.document or reply.video or reply.audio
    if not media: return await message.reply("⚠️ Not a valid media.")
    
    msg = await message.reply("🔗 Generating...", quote=True)
    try:
        log_msg = await client.send_cached_media(BIN_CHANNEL, media.file_id)
        stream = f"{URL}watch/{log_msg.id}"
        dl = f"{URL}download/{log_msg.id}"
        
        await msg.edit(
            f"<b>✅ Link Generated!</b>\n\n<b>🔗 Stream:</b> {stream}\n<b>📥 Download:</b> {dl}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Watch", url=stream), InlineKeyboardButton("⬇️ Download", url=dl)]
            ]),
            disable_web_page_preview=True
        )
    except Exception as e:
        await msg.edit(f"❌ Error: {e}")

# ─────────────────────────
# /stats COMMAND
# ─────────────────────────
@Client.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats(_, message):
    msg = await message.reply("🔄 Fetching...")
    files = await db_count_documents()
    users = await db.total_users_count()
    chats = await db.total_chat_count()
    premium = await db.premium.count_documents({"status.premium": True})

    await msg.edit(f"""
📊 <b>Status</b>
👥 Users: `{users}` | Chats: `{chats}`
💎 Premium: `{premium}`
📁 Files: `{files['total']}`
 • Pri: `{files['primary']}` | Cld: `{files['cloud']}` | Arc: `{files['archive']}`
""")

# ─────────────────────────
# CALLBACKS & DELETE (Standard)
# ─────────────────────────
# (बाकी फंक्शन्स वैसे ही रखें जैसे पिछले कोड में थे, वो सही हैं)
@Client.on_callback_query(filters.regex(r"^stream#"))
async def stream_cb(client, query):
    file_id = query.data.split("#")[1]
    await query.answer("🔗 Generating...")
    try:
        # Use new get_file_details to ensure we get the file even if passed ID format differs
        file = await get_file_details(file_id)
        if not file: return await query.answer("File not found!", show_alert=True)
        
        msg = await client.send_cached_media(BIN_CHANNEL, file['file_id'])
        watch = f"{URL}watch/{msg.id}"
        dl = f"{URL}download/{msg.id}"
        
        btn = [
            [InlineKeyboardButton("▶️ Watch", url=watch), InlineKeyboardButton("⬇️ Download", url=dl)],
            [InlineKeyboardButton("❌ Close", callback_data="close_data")]
        ]
        await query.message.edit_reply_markup(InlineKeyboardMarkup(btn))
    except Exception as e:
        await query.message.edit(f"❌ Error: {e}")

@Client.on_callback_query(filters.regex("^close_data$"))
async def close_cb(c, q):
    try: await q.message.delete()
    except: pass

