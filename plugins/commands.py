import os
import random
import asyncio
from bson.objectid import ObjectId  # 🔥 ये Import जरूरी है ID फिक्स के लिए
from datetime import datetime
from time import time as time_now
from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Script import script
# 🔥 Media को इम्पोर्ट किया ताकि हम सीधे डेटाबेस में ढूंढ सकें
from database.ia_filterdb import db_count_documents, get_file_details, delete_files, Media
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
# /start COMMAND (Fixed ID Issue)
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
                
                # 🔥 ID MATCHING FIX (String vs ObjectId)
                file = None
                
                # A. Try Finding as String (Standard)
                try:
                    file = await Media.find_one({"_id": file_id})
                except: pass

                # B. Try Finding as ObjectId (Old Files)
                if not file:
                    try:
                        file = await Media.find_one({"_id": ObjectId(file_id)})
                    except: pass
                
                # C. Deep Search in Collections (If still not found)
                if not file:
                    for collection in ["cloud", "archive"]:
                        try:
                            # Try String
                            file = await Media.find_one({"_id": file_id, "collection_type": collection})
                            if file: break
                            # Try ObjectId
                            file = await Media.find_one({"_id": ObjectId(file_id), "collection_type": collection})
                            if file: break
                        except: continue

                if not file:
                    return await message.reply("❌ **File Not Found!**\n\nIt seems the file was deleted or the ID is invalid.")
                
                settings = await get_settings(grp_id)
                cap_template = settings.get('caption', '{file_name}\n\n💾 Size: {file_size}')
                
                caption = cap_template.format(
                    file_name=file.get('file_name', 'File'),
                    file_size=get_size(file.get('file_size', 0)),
                    file_caption=file.get('caption', '')
                )
                
                btn = [[InlineKeyboardButton('❌ Close', callback_data='close_data')]]
                if IS_STREAM:
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
            return await message.reply("❌ Error fetching file details.")

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
        return await message.reply("⚠️ **Please reply to a file** to generate a link.")
    
    reply = message.reply_to_message
    media = reply.document or reply.video or reply.audio
    
    if not media:
        return await message.reply("⚠️ This is not a valid media file.")
    
    msg = await message.reply("🔗 **Generating Link...**", quote=True)
    
    try:
        log_msg = await client.send_cached_media(
            chat_id=BIN_CHANNEL,
            file_id=media.file_id
        )
        
        stream_link = f"{URL}watch/{log_msg.id}"
        download_link = f"{URL}download/{log_msg.id}"
        
        btn = [
            [InlineKeyboardButton("▶️ Watch Online", url=stream_link)],
            [InlineKeyboardButton("⬇️ Fast Download", url=download_link)]
        ]
        
        file_name = media.file_name if hasattr(media, 'file_name') else "Unknown File"
        file_size = get_size(media.file_size)
        
        await msg.edit(
            f"<b>✅ Link Generated!</b>\n\n"
            f"📂 <b>File:</b> {file_name}\n"
            f"💾 <b>Size:</b> {file_size}\n\n"
            f"<b>🔗 Stream:</b> {stream_link}\n"
            f"<b>📥 Download:</b> {download_link}",
            reply_markup=InlineKeyboardMarkup(btn),
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await msg.edit(f"❌ **Error:** `{str(e)}`")


# ─────────────────────────
# /stats COMMAND
# ─────────────────────────
@Client.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats(_, message):
    msg = await message.reply("🔄 Fetching Stats...")
    
    files = await db_count_documents()
    users = await db.total_users_count()
    chats = await db.total_chat_count()
    premium = await db.premium.count_documents({"status.premium": True})

    text = f"""
📊 <b>Bot Statistics</b>

👥 <b>Users:</b> `{users}`
👥 <b>Groups:</b> `{chats}`
💎 <b>Premium:</b> `{premium}`

📁 <b>Files:</b> `{files['total']}`
 • Primary: `{files['primary']}`
 • Cloud: `{files['cloud']}`
 • Archive: `{files['archive']}`

⏱ <b>Uptime:</b> `{get_readable_time(time_now() - temp.START_TIME)}`
"""
    await msg.edit(text)

# ─────────────────────────
# /delete COMMAND
# ─────────────────────────
@Client.on_message(filters.command("delete") & filters.user(ADMINS))
async def delete_file_cmd(client, message):
    if len(message.command) < 3:
        return await message.reply("Usage: `/delete primary Avengers.mkv`")
    
    storage = message.command[1].lower()
    query = " ".join(message.command[2:])
    
    if storage not in ["primary", "cloud", "archive"]:
        return await message.reply("❌ Invalid Storage! Use: primary, cloud, archive")
    
    msg = await message.reply("🗑 Deleting...")
    count = await delete_files(query, storage)
    
    if count: await msg.edit(f"✅ Deleted `{count}` files from `{storage}`.")
    else: await msg.edit("❌ No files found.")

# ─────────────────────────
# /delete_all COMMAND
# ─────────────────────────
@Client.on_message(filters.command("delete_all") & filters.user(ADMINS))
async def delete_all_cmd(client, message):
    if len(message.command) < 2:
        return await message.reply("Usage: `/delete_all primary` or `/delete_all all`")
    
    storage = message.command[1].lower()
    if storage not in ["primary", "cloud", "archive", "all"]:
        return await message.reply("❌ Invalid Storage!")
    
    btn = [[
        InlineKeyboardButton("✅ CONFIRM DELETE", callback_data=f"confirm_del#{storage}"),
        InlineKeyboardButton("❌ CANCEL", callback_data="close_data")
    ]]
    
    await message.reply(
        f"⚠️ <b>WARNING!</b>\n\nDeleting ALL files from `{storage}`.\nConfirm?",
        reply_markup=InlineKeyboardMarkup(btn)
    )

@Client.on_callback_query(filters.regex(r"^confirm_del#"))
async def confirm_del(client, query):
    storage = query.data.split("#")[1]
    await query.message.edit("🗑 Processing... This may take time.")
    
    count = await delete_files("*", storage)
    await query.message.edit(f"✅ Deleted `{count}` files from `{storage}`.")

# ─────────────────────────
# CALLBACKS
# ─────────────────────────
@Client.on_callback_query(filters.regex("^myplan$"))
async def myplan_cb(client, query):
    if not IS_PREMIUM: return await query.answer("Premium disabled.", show_alert=True)
    
    mp = await db.get_plan(query.from_user.id)
    if not mp.get('premium'):
        btn = [[InlineKeyboardButton('💎 Buy Premium', callback_data='activate_plan')]]
        return await query.message.edit("❌ No active plan.", reply_markup=InlineKeyboardMarkup(btn))
    
    expire = mp.get('expire')
    if isinstance(expire, str):
        try: expire = datetime.strptime(expire, "%Y-%m-%d %H:%M:%S")
        except: expire = None
        
    left = "Unknown"
    if expire:
        diff = expire - datetime.now()
        left = f"{diff.days} days, {diff.seconds//3600} hours"

    await query.message.edit(
        f"💎 <b>Premium Status</b>\n\n"
        f"📦 Plan: {mp.get('plan')}\n"
        f"⏳ Expires: {expire}\n"
        f"⏱ Left: {left}\n\n"
        f"Use /plan to extend."
    )

@Client.on_callback_query(filters.regex(r"^stream#"))
async def stream_cb(client, query):
    file_id = query.data.split("#")[1]
    await query.answer("🔗 Generating Links...")
    
    try:
        msg = await client.send_cached_media(BIN_CHANNEL, file_id)
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
    try:
        await q.message.delete()
        if hasattr(temp, 'PM_FILES') and q.message.id in temp.PM_FILES:
            try:
                note_id = temp.PM_FILES[q.message.id]['note_msg']
                await c.delete_messages(q.message.chat.id, note_id)
                del temp.PM_FILES[q.message.id]
            except: pass
    except: pass

