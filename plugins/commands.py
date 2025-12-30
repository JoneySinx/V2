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
    get_wish,
    get_premium_button
)

# ─────────────────────────
# HELPERS
# ─────────────────────────
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

    # ✅ Add user to database
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        await client.send_message(
            LOG_CHANNEL,
            script.NEW_USER_TXT.format(
                message.from_user.mention,
                message.from_user.id
            )
        )

    # ✅ Premium check (synced with Premium.py)
    if IS_PREMIUM and not await is_premium(message.from_user.id, client):
        return await message.reply_photo(
            random.choice(PICS),
            caption="🔒 <b>Premium Required</b>\n\n"
                    "This bot is only for Premium users!\n\n"
                    "Use /plan to activate premium subscription.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 Buy Premium", callback_data="activate_plan")
            ]]),
            parse_mode=enums.ParseMode.HTML
        )

    # Handle /start premium (from button clicks)
    if len(message.command) > 1 and message.command[1] == "premium":
        return await message.reply_photo(
            random.choice(PICS),
            caption=script.PLAN_TXT.format(
                "Contact admin for pricing",
                temp.U_NAME
            ) if hasattr(script, 'PLAN_TXT') else "💎 Premium Plans\n\nContact admin for details.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Activate Plan", callback_data="activate_plan")],
                [InlineKeyboardButton("📊 My Plan", callback_data="myplan")]
            ]),
            parse_mode=enums.ParseMode.HTML
        )

    # Handle /start with file_id parameter
    if len(message.command) > 1:
        mc = message.command[1]
        
        try:
            parts = mc.split("_")
            if len(parts) >= 3:
                try:
                    await message.delete()
                except:
                    pass
                
                grp_id = parts[1]
                file_id = parts[2]
                
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
                
                CAPTION = settings.get('caption', '{file_name}\n\n💾 Size: {file_size}')
                f_caption = CAPTION.format(
                    file_name=files.get('file_name', 'File'),
                    file_size=get_size(files.get('file_size', 0)),
                    file_caption=files.get('caption', '')
                )
                
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
                
                vp = await client.send_cached_media(
                    chat_id=message.chat.id,
                    file_id=file_id,
                    caption=f_caption,
                    protect_content=False,
                    reply_markup=InlineKeyboardMarkup(btn)
                )
                
                if PM_FILE_DELETE_TIME and PM_FILE_DELETE_TIME > 0:
                    time = get_readable_time(PM_FILE_DELETE_TIME)
                    msg = await vp.reply(
                        f"Nᴏᴛᴇ: Tʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴅᴇʟᴇᴛᴇ ɪɴ {time} ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛs."
                    )
                    
                    if not hasattr(temp, 'PM_FILES'):
                        temp.PM_FILES = {}
                    
                    temp.PM_FILES[vp.id] = {
                        'file_msg': vp.id,
                        'note_msg': msg.id,
                        'chat_id': message.chat.id
                    }
                    
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
                ],
                [
                    InlineKeyboardButton("💎 PREMIUM", callback_data="myplan")
                ]
            ])
        )

# ─────────────────────────
# /stats - CLEAN FORMAT
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

👥 <b>Users</b>   : <code>{users}</code>
👥 <b>Groups</b>  : <code>{chats}</code>
💎 <b>Premium</b> : <code>{premium}</code>

📁 <b>Files Database</b>

📂 Primary   : <code>{primary}</code>
☁️ Cloud     : <code>{cloud}</code>
🗄 Archive   : <code>{archive}</code>

🧮 <b>Total Files</b> : <code>{total}</code>
⏱ <b>Uptime</b> : <code>{get_readable_time(time_now() - temp.START_TIME)}</code>
"""

    await message.reply_text(text, parse_mode=enums.ParseMode.HTML)

# ─────────────────────────
# /delete - DELETE BY FILE NAME
# ─────────────────────────
@Client.on_message(filters.command("delete") & filters.user(ADMINS))
async def delete_file(client, message):
    """
    Usage: /delete <storage_type> <file_name>
    
    Examples:
    /delete primary Avengers.mkv
    /delete cloud Spider-Man.mp4
    /delete archive Batman.pdf
    """
    
    if len(message.command) < 3:
        return await message.reply_text(
            "❌ <b>Invalid Format!</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/delete [storage] [filename]</code>\n\n"
            "<b>Storage Options:</b>\n"
            "• <code>primary</code>\n"
            "• <code>cloud</code>\n"
            "• <code>archive</code>\n\n"
            "<b>Example:</b>\n"
            "<code>/delete primary Avengers.mkv</code>",
            parse_mode=enums.ParseMode.HTML
        )
    
    storage_type = message.command[1].lower()
    file_name = " ".join(message.command[2:])
    
    if storage_type not in ["primary", "cloud", "archive"]:
        return await message.reply_text(
            "❌ <b>Invalid Storage!</b>\n\n"
            "Choose: <code>primary</code>, <code>cloud</code>, or <code>archive</code>",
            parse_mode=enums.ParseMode.HTML
        )
    
    sts = await message.reply_text("🔍 Searching...")
    
    try:
        deleted_count = await delete_files(file_name, storage_type)
        
        if deleted_count > 0:
            await sts.edit_text(
                f"✅ <b>Deleted Successfully!</b>\n\n"
                f"📂 <b>Storage:</b> <code>{storage_type.upper()}</code>\n"
                f"📄 <b>File:</b> <code>{file_name}</code>\n"
                f"🗑 <b>Deleted:</b> <code>{deleted_count}</code> file(s)",
                parse_mode=enums.ParseMode.HTML
            )
        else:
            await sts.edit_text(
                f"❌ <b>Not Found!</b>\n\n"
                f"📂 <b>Storage:</b> <code>{storage_type.upper()}</code>\n"
                f"📄 <b>File:</b> <code>{file_name}</code>",
                parse_mode=enums.ParseMode.HTML
            )
    
    except Exception as e:
        await sts.edit_text(f"❌ Error: {str(e)}")
        print(f"Delete error: {e}")

# ─────────────────────────
# /delete_all - DELETE ALL FROM STORAGE
# ─────────────────────────
@Client.on_message(filters.command("delete_all") & filters.user(ADMINS))
async def delete_all_files(client, message):
    """
    Usage: /delete_all <storage_type>
    
    Examples:
    /delete_all primary
    /delete_all cloud
    /delete_all archive
    /delete_all all
    """
    
    if len(message.command) < 2:
        return await message.reply_text(
            "❌ <b>Invalid Format!</b>\n\n"
            "<b>Usage:</b>\n"
            "<code>/delete_all [storage]</code>\n\n"
            "<b>Storage Options:</b>\n"
            "• <code>primary</code> - Delete Primary files\n"
            "• <code>cloud</code> - Delete Cloud files\n"
            "• <code>archive</code> - Delete Archive files\n"
            "• <code>all</code> - Delete ALL (⚠️ Dangerous)\n\n"
            "<b>Example:</b>\n"
            "<code>/delete_all primary</code>",
            parse_mode=enums.ParseMode.HTML
        )
    
    storage_type = message.command[1].lower()
    
    if storage_type not in ["primary", "cloud", "archive", "all"]:
        return await message.reply_text(
            "❌ <b>Invalid Storage!</b>\n\n"
            "Choose: <code>primary</code>, <code>cloud</code>, <code>archive</code>, <code>all</code>",
            parse_mode=enums.ParseMode.HTML
        )
    
    # Confirmation
    buttons = [
        [
            InlineKeyboardButton("✅ YES DELETE", callback_data=f"confirm_del#{storage_type}"),
            InlineKeyboardButton("❌ CANCEL", callback_data="cancel_del")
        ]
    ]
    
    if storage_type == "all":
        warning = (
            "⚠️ <b>DANGER WARNING!</b> ⚠️\n\n"
            "Delete <b>ALL FILES</b> from:\n"
            "• Primary Storage\n"
            "• Cloud Storage\n"
            "• Archive Storage\n\n"
            "🚨 <b>CANNOT BE UNDONE!</b>\n\n"
            "Confirm?"
        )
    else:
        warning = (
            f"⚠️ <b>WARNING!</b>\n\n"
            f"Delete <b>ALL FILES</b> from:\n"
            f"📂 <code>{storage_type.upper()}</code>\n\n"
            f"Cannot be undone!\n\n"
            f"Confirm?"
        )
    
    await message.reply_text(
        warning,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=enums.ParseMode.HTML
    )

# ─────────────────────────
# CALLBACK: Confirm Delete All
# ─────────────────────────
@Client.on_callback_query(filters.regex(r"^confirm_del#"))
async def confirm_delete_cb(client, query):
    storage = query.data.split("#")[1]
    
    await query.message.edit_text("🗑 Deleting... Please wait...")
    
    try:
        if storage == "all":
            # Delete from all storages
            p_del = await delete_files("*", "primary")
            c_del = await delete_files("*", "cloud")
            a_del = await delete_files("*", "archive")
            
            result = (
                "✅ <b>All Files Deleted!</b>\n\n"
                f"📂 Primary: <code>{p_del}</code>\n"
                f"☁️ Cloud: <code>{c_del}</code>\n"
                f"🗄 Archive: <code>{a_del}</code>\n\n"
                f"🗑 Total: <code>{p_del + c_del + a_del}</code>"
            )
        else:
            # Delete from specific storage
            deleted = await delete_files("*", storage)
            result = (
                f"✅ <b>Files Deleted!</b>\n\n"
                f"📂 Storage: <code>{storage.upper()}</code>\n"
                f"🗑 Deleted: <code>{deleted}</code> files"
            )
        
        await query.message.edit_text(result, parse_mode=enums.ParseMode.HTML)
        
    except Exception as e:
        await query.message.edit_text(f"❌ Error: {str(e)}")

@Client.on_callback_query(filters.regex("^cancel_del$"))
async def cancel_delete_cb(client, query):
    await query.message.edit_text(
        "❌ <b>Cancelled</b>",
        parse_mode=enums.ParseMode.HTML
    )

# ─────────────────────────
# CALLBACK: My Plan
# ─────────────────────────
@Client.on_callback_query(filters.regex("^myplan$"))
async def myplan_cb(client, query):
    """Handle myplan button callback"""
    from plugins.premium import TRIAL_ENABLED
    
    if not IS_PREMIUM:
        return await query.answer('Premium feature was disabled by admin', show_alert=True)
    
    mp = db.get_plan(query.from_user.id)
    
    if not await is_premium(query.from_user.id, client):
        btn = []
        
        # Only show trial button if enabled
        if TRIAL_ENABLED:
            btn.append([
                InlineKeyboardButton('🎁 Activate Trial', callback_data='activate_trial'),
                InlineKeyboardButton('💎 Activate Plan', callback_data='activate_plan')
            ])
        else:
            btn.append([
                InlineKeyboardButton('💎 Activate Plan', callback_data='activate_plan')
            ])
        
        return await query.message.edit_text(
            '❌ You dont have any premium plan.\n\nUse /plan to activate premium subscription.', 
            reply_markup=InlineKeyboardMarkup(btn)
        )
    
    # ✅ Handle expire_time properly (can be string or datetime)
    expire_time = mp.get('expire')
    
    # Convert string to datetime if needed
    if isinstance(expire_time, str):
        try:
            from dateutil import parser
            expire_time = parser.parse(expire_time)
        except:
            # Fallback: show without time calculation
            return await query.message.edit_text(
                f"✅ <b>Your Premium Status</b>\n\n"
                f"📦 Plan: {mp.get('plan', 'Unknown')}\n"
                f"⏰ Status: Active\n\n"
                f"💡 Use /plan to extend your subscription.",
                parse_mode=enums.ParseMode.HTML
            )
    
    # Calculate time left
    time_left = expire_time - datetime.now()
    days_left = max(0, time_left.days)
    hours_left = max(0, time_left.seconds // 3600)
    
    await query.message.edit_text(
        f"✅ <b>Your Premium Status</b>\n\n"
        f"📦 Plan: {mp.get('plan', 'Unknown')}\n"
        f"⏰ Expires: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⏳ Time Left: {days_left} days {hours_left} hours\n\n"
        f"💡 Use /plan to extend your subscription.",
        parse_mode=enums.ParseMode.HTML
    )

# ─────────────────────────
# STREAM CALLBACK
# ─────────────────────────
@Client.on_callback_query(filters.regex(r"^stream#"))
async def stream_cb(client, query):
    try:
        file_id = query.data.split("#", 1)[1]
        
        await query.answer("⏳ Generating...", show_alert=False)

        files = await get_file_details(file_id)
        if not files:
            return await query.answer("❌ Not found!", show_alert=True)
        
        file = files[0] if isinstance(files, list) else files
        
        msg = await client.send_cached_media(
            chat_id=BIN_CHANNEL,
            file_id=file_id
        )

        watch = f"{URL}watch/{msg.id}"
        download = f"{URL}download/{msg.id}"

        buttons = [
            [
                InlineKeyboardButton("▶️ ᴡᴀᴛᴄʜ", url=watch),
                InlineKeyboardButton("⬇️ ᴅᴏᴡɴʟᴏᴀᴅ", url=download)
            ],
            [
                InlineKeyboardButton("❌ ᴄʟᴏsᴇ", callback_data="close_data")
            ]
        ]

        try:
            await query.message.edit_reply_markup(
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except:
            await query.message.reply_text(
                "🎬 <b>Links Ready:</b>",
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=enums.ParseMode.HTML
            )
        
    except Exception as e:
        print(f"Stream error: {e}")
        await query.answer("❌ Error!", show_alert=True)

# ─────────────────────────
# CLOSE BUTTON
# ─────────────────────────
@Client.on_callback_query(filters.regex("^close_data$"))
async def close_cb(client, query):
    try:
        if not query.message:
            return await query.answer("Deleted", show_alert=False)
        
        msg_id = query.message.id
        chat_id = query.message.chat.id
        msgs = [msg_id]
        
        if hasattr(temp, 'PM_FILES') and msg_id in temp.PM_FILES:
            data = temp.PM_FILES[msg_id]
            msgs.append(data['note_msg'])
            del temp.PM_FILES[msg_id]
        else:
            try:
                msgs.append(msg_id + 1)
            except:
                pass
        
        try:
            await client.delete_messages(chat_id=chat_id, message_ids=msgs)
            await query.answer("✅ Deleted", show_alert=False)
        except:
            for m in msgs:
                try:
                    await client.delete_messages(chat_id=chat_id, message_ids=m)
                except:
                    pass
            await query.answer("✅ Deleted", show_alert=False)
            
    except Exception as e:
        print(f"Close error: {e}")
        try:
            await query.answer()
        except:
            pass
