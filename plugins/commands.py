import os
import random
import asyncio
from time import time as time_now
from datetime import datetime

from Script import script
from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.ia_filterdb import (
    db_count_documents,
    get_file_details,
    delete_files
)
from database.users_chats_db import db

from info import (
    IS_PREMIUM,
    URL,
    BIN_CHANNEL,
    STICKERS,
    ADMINS,
    DELETE_TIME,
    LOG_CHANNEL,
    PICS,
    IS_STREAM,
    REACTIONS,
    PM_FILE_DELETE_TIME
)

from utils import (
    is_premium,
    get_settings,
    get_size,
    is_check_admin,
    temp,
    get_readable_time,
    get_wish
)

# ─────────────────────────
# HELPERS
# ─────────────────────────
def progress_bar(v, t, s=10):
    if t <= 0:
        return "░" * s
    f = int((v / t) * s)
    return "█" * f + "░" * (s - f)

async def del_stk(s):
    await asyncio.sleep(3)
    try:
        await s.delete()
    except:
        pass

async def auto_delete_messages(msg_ids, chat_id, client, delay):
    """Auto delete multiple messages after delay"""
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id=chat_id, message_ids=msg_ids)
    except Exception as e:
        print(f"Auto delete error: {e}")

# ─────────────────────────
# /start
# ─────────────────────────
@Client.on_message(filters.command("start") & filters.incoming)
async def start(client, message):

    # GROUP
    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        if not await db.get_chat(message.chat.id):
            total = await client.get_chat_members_count(message.chat.id)
            username = f'@{message.chat.username}' if message.chat.username else 'Private'
            await client.send_message(
                LOG_CHANNEL,
                script.NEW_GROUP_TXT.format(
                    message.chat.title,
                    message.chat.id,
                    username,
                    total
                )
            )
            await db.add_chat(message.chat.id, message.chat.title)

        await message.reply(
            f"<b>ʜᴇʏ {message.from_user.mention}, <i>{get_wish()}</i>\n"
            f"ʜᴏᴡ ᴄᴀɴ ɪ ʜᴇʟᴘ ʏᴏᴜ??</b>",
            parse_mode=enums.ParseMode.HTML
        )
        return

    # PRIVATE
    try:
        if REACTIONS:
            await message.react(random.choice(REACTIONS), big=True)
    except:
        pass

    if STICKERS:
        try:
            stk = await client.send_sticker(
                message.chat.id,
                random.choice(STICKERS)
            )
            asyncio.create_task(del_stk(stk))
        except:
            pass

    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        await client.send_message(
            LOG_CHANNEL,
            script.NEW_USER_TXT.format(
                message.from_user.mention,
                message.from_user.id
            )
        )

    if not await is_premium(message.from_user.id, client) and message.from_user.id not in ADMINS:
        return await message.reply_photo(
            random.choice(PICS),
            caption="❌ This bot is only for Premium users and Admins!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "🤑 Buy Premium",
                    url=f"https://t.me/{temp.U_NAME}?start=premium"
                )
            ]])
        )

    # Handle /start with file_id parameter
    if len(message.command) > 1:
        mc = message.command[1]
        
        # Parse: files_grp_id_file_id or file_grp_id_file_id
        try:
            parts = mc.split("_")
            if len(parts) >= 3:
                # Delete /start command message immediately
                try:
                    await message.delete()
                except:
                    pass
                
                # Extract grp_id and file_id
                grp_id = parts[1]
                file_id = parts[2]
                
                # Get file details from database
                files_ = await get_file_details(file_id)
                if not files_:
                    temp_msg = await client.send_message(
                        message.chat.id,
                        '❌ No Such File Exist!'
                    )
                    await asyncio.sleep(5)
                    await temp_msg.delete()
                    return
                
                files = files_
                settings = await get_settings(int(grp_id))
                
                # Build caption
                CAPTION = settings.get('caption', '{file_name}\n\n💾 Size: {file_size}')
                f_caption = CAPTION.format(
                    file_name=files.get('file_name', 'File'),
                    file_size=get_size(files.get('file_size', 0)),
                    file_caption=files.get('caption', '')
                )
                
                # Build buttons based on IS_STREAM setting
                if IS_STREAM:
                    btn = [[
                        InlineKeyboardButton("✛ ᴡᴀᴛᴄʜ & ᴅᴏᴡɴʟᴏᴀᴅ ✛", callback_data=f"stream#{file_id}")
                    ],[
                        InlineKeyboardButton('⁉️ ᴄʟᴏsᴇ ⁉️', callback_data='close_data')
                    ]]
                else:
                    btn = [[
                        InlineKeyboardButton('⁉️ ᴄʟᴏsᴇ ⁉️', callback_data='close_data')
                    ]]
                
                # Send file directly
                vp = await client.send_cached_media(
                    chat_id=message.chat.id,
                    file_id=file_id,
                    caption=f_caption,
                    protect_content=False,
                    reply_markup=InlineKeyboardMarkup(btn)
                )
                
                # Send copyright notice and store message IDs
                if PM_FILE_DELETE_TIME and PM_FILE_DELETE_TIME > 0:
                    time = get_readable_time(PM_FILE_DELETE_TIME)
                    msg = await vp.reply(
                        f"Nᴏᴛᴇ: Tʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇ ɪɴ {time} ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛs."
                    )
                    
                    # Store message IDs in temp for close button
                    temp.PM_FILES[vp.id] = {
                        'file_msg': vp.id,
                        'note_msg': msg.id,
                        'chat_id': message.chat.id
                    }
                    
                    # Schedule auto delete
                    asyncio.create_task(
                        auto_delete_messages([vp.id, msg.id], message.chat.id, client, PM_FILE_DELETE_TIME)
                    )
                return
        except Exception as e:
            print(f"Error parsing start command: {e}")
            import traceback
            traceback.print_exc()
    
    # Default /start response
    if len(message.command) == 1:
        await message.reply_photo(
            random.choice(PICS),
            caption=script.START_TXT.format(
                message.from_user.mention,
                get_wish()
            ),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "+ ADD ME TO YOUR GROUP +",
                        url=f"https://t.me/{temp.U_NAME}?startgroup=start"
                    )
                ],
                [
                    InlineKeyboardButton("👨‍🚒 HELP", callback_data="help"),
                    InlineKeyboardButton("📚 ABOUT", callback_data="about")
                ]
            ])
        )

# ─────────────────────────
# /stats
# ─────────────────────────
@Client.on_message(filters.command("stats") & filters.user(ADMINS))
async def stats(_, message):

    files = db_count_documents()
    primary = files.get("primary", 0)
    cloud = files.get("cloud", 0)
    archive = files.get("archive", 0)
    total = files.get("total", 0)

    users = await db.total_users_count()
    chats = await db.total_chat_count()
    premium = db.get_premium_count()

    text = f"""
📊 <b>Bot Statistics</b>

👥 Users   : {users}
👥 Groups  : {chats}
💎 Premium : {premium}

📁 <b>Files</b>

Primary   {progress_bar(primary,total)} {primary}
Cloud     {progress_bar(cloud,total)} {cloud}
Archive   {progress_bar(archive,total)} {archive}

🧮 Total Files : {total}
⏱ Uptime : {get_readable_time(time_now() - temp.START_TIME)}
"""

    await message.reply_text(text, parse_mode=enums.ParseMode.HTML)

# ─────────────────────────
# STREAM CALLBACK → Generate Watch/Download Links
# ─────────────────────────
@Client.on_callback_query(filters.regex(r"^stream#"))
async def stream_cb(client, query):
    """When user clicks 'Watch & Download' button"""
    try:
        file_id = query.data.split("#", 1)[1]
        
        await query.answer("⏳ Generating links...", show_alert=False)

        # Get file details
        files = await get_file_details(file_id)
        if not files:
            return await query.answer("❌ File not found!", show_alert=True)
        
        # Handle both list and dict response
        file = files[0] if isinstance(files, list) else files
        
        # Send file to BIN_CHANNEL to get message_id for streaming
        msg = await client.send_cached_media(
            chat_id=BIN_CHANNEL,
            file_id=file_id
        )

        # Generate streaming URLs
        watch = f"{URL}watch/{msg.id}"
        download = f"{URL}download/{msg.id}"

        # Create buttons with links
        buttons = [
            [
                InlineKeyboardButton("▶️ ᴡᴀᴛᴄʜ ᴏɴʟɪɴᴇ", url=watch),
                InlineKeyboardButton("⬇️ ꜰᴀsᴛ ᴅᴏᴡɴʟᴏᴀᴅ", url=download)
            ],
            [
                InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close_data")
            ]
        ]

        # Try to edit the message buttons
        try:
            await query.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception as e:
            # If edit fails, send new message
            print(f"Failed to edit markup: {e}")
            await query.message.reply_text(
                "🎬 <b>Your Links Are Ready:</b>\n\n"
                "▶️ Click <b>Watch Online</b> to stream\n"
                "⬇️ Click <b>Fast Download</b> to save",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=enums.ParseMode.HTML
            )
        
    except Exception as e:
        print(f"❌ Error in stream_cb: {e}")
        import traceback
        traceback.print_exc()
        await query.answer("❌ Error generating links!", show_alert=True)

# ─────────────────────────
# CLOSE BUTTON (Delete file + copyright notice)
# ─────────────────────────
@Client.on_callback_query(filters.regex("^close_data$"))
async def close_cb(client, query):
    """Delete both file message and copyright notice"""
    try:
        if not query.message:
            return await query.answer("Already deleted", show_alert=False)
        
        msg_id = query.message.id
        chat_id = query.message.chat.id
        
        # Check if we have stored message IDs for this file
        msgs_to_delete = [msg_id]
        
        if hasattr(temp, 'PM_FILES') and msg_id in temp.PM_FILES:
            # Get associated note message
            data = temp.PM_FILES[msg_id]
            msgs_to_delete.append(data['note_msg'])
            # Clean up temp storage
            del temp.PM_FILES[msg_id]
        else:
            # Try to delete the message below (copyright notice)
            try:
                # Get next message (copyright notice is usually reply to file)
                msgs_to_delete.append(msg_id + 1)
            except:
                pass
        
        # Delete all messages
        try:
            await client.delete_messages(
                chat_id=chat_id,
                message_ids=msgs_to_delete
            )
            await query.answer("✅ Deleted", show_alert=False)
        except Exception as e:
            print(f"Delete error: {e}")
            # Try deleting one by one
            for m_id in msgs_to_delete:
                try:
                    await client.delete_messages(chat_id=chat_id, message_ids=m_id)
                except:
                    pass
            await query.answer("✅ Deleted", show_alert=False)
            
    except Exception as e:
        print(f"Error in close_cb: {e}")
        import traceback
        traceback.print_exc()
        try:
            await query.answer()
        except:
            pass
