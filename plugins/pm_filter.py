import asyncio
import re
from time import time as time_now
import math
from hydrogram.errors import ListenerTimeout
from Script import script
from datetime import datetime, timedelta
from info import PICS, ADMINS, LOG_CHANNEL, DELETE_TIME, MAX_BTN
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto
from hydrogram import Client, filters, enums
from utils import is_premium, get_size, is_check_admin, get_wish, get_readable_time, temp, get_settings, save_group_settings, is_subscribed
from database.users_chats_db import db
from database.ia_filterdb import get_search_results, delete_files, db_count_documents, second_db_count_documents
from plugins.commands import get_grp_stg

BUTTONS = {}
CAP = {}

@Client.on_message(filters.private & filters.text & filters.incoming)
async def pm_search(client, message):
    if message.text.startswith("/"):
        return
    
    # Check if user is premium or admin
    if not await is_premium(message.from_user.id, client) and message.from_user.id not in ADMINS:
        return await message.reply_text('❌ This bot is only for Premium users and Admins!\n\nContact admin for access.')
    
    stg = db.get_bot_sttgs()
    if not stg.get('PM_SEARCH'):
        return await message.reply_text('PM search was disabled!')
    
    if not stg.get('AUTO_FILTER'):
        return await message.reply_text('Auto filter was disabled!')
    
    s = await message.reply(f"<b><i>⚠️ `{message.text}` searching...</i></b>", quote=True)
    await auto_filter(client, message, s)

@Client.on_message(filters.group & filters.text & filters.incoming)
async def group_search(client, message):
    chat_id = message.chat.id
    user_id = message.from_user.id if message and message.from_user else 0
    stg = db.get_bot_sttgs()
    
    if stg.get('AUTO_FILTER'):
        if not user_id:
            await message.reply("I'm not working for anonymous admin!")
            return
        
        # Check if user is premium or admin
        if not await is_premium(user_id, client) and user_id not in ADMINS:
            return await message.reply_text('❌ This bot is only for Premium users and Admins!')
        
        if message.text.startswith("/"):
            return
            
        elif '@admin' in message.text.lower() or '@admins' in message.text.lower():
            if await is_check_admin(client, message.chat.id, message.from_user.id):
                return
            admins = []
            async for member in client.get_chat_members(chat_id=message.chat.id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
                if not member.user.is_bot:
                    admins.append(member.user.id)
                    if member.status == enums.ChatMemberStatus.OWNER:
                        if message.reply_to_message:
                            try:
                                sent_msg = await message.reply_to_message.forward(member.user.id)
                                await sent_msg.reply_text(f"#Attention\n★ User: {message.from_user.mention}\n★ Group: {message.chat.title}\n\n★ <a href={message.reply_to_message.link}>Go to message</a>", disable_web_page_preview=True)
                            except:
                                pass
                        else:
                            try:
                                sent_msg = await message.forward(member.user.id)
                                await sent_msg.reply_text(f"#Attention\n★ User: {message.from_user.mention}\n★ Group: {message.chat.title}\n\n★ <a href={message.link}>Go to message</a>", disable_web_page_preview=True)
                            except:
                                pass
            hidden_mentions = (f'[\u2064](tg://user?id={user_id})' for user_id in admins)
            await message.reply_text('Report sent!' + ''.join(hidden_mentions))
            return

        elif re.findall(r'https?://\S+|www\.\S+|t\.me/\S+|@\w+', message.text):
            if await is_check_admin(client, message.chat.id, message.from_user.id):
                return
            await message.delete()
            return await message.reply('Links not allowed here!')
        
        elif '#request' in message.text.lower():
            if message.from_user.id in ADMINS:
                return
            await client.send_message(LOG_CHANNEL, f"#Request\n★ User: {message.from_user.mention}\n★ Group: {message.chat.title}\n\n★ Message: {re.sub(r'#request', '', message.text.lower())}")
            await message.reply_text("Request sent!")
            return  
        else:
            s = await message.reply(f"<b><i>⚠️ `{message.text}` searching...</i></b>")
            await auto_filter(client, message, s)
    else:
        k = await message.reply_text('Auto Filter Off! ❌')
        await asyncio.sleep(5)
        await k.delete()
        try:
            await message.delete()
        except:
            pass

@Client.on_callback_query(filters.regex(r"^next"))
async def next_page(bot, query):
    ident, req, key, offset = query.data.split("_")
    if int(req) not in [query.from_user.id, 0]:
        return await query.answer(f"Hello {query.from_user.first_name},\nDon't Click Other Results!", show_alert=True)
    
    try:
        offset = int(offset)
    except:
        offset = 0
    
    search = BUTTONS.get(key)
    cap = CAP.get(key)
    if not search:
        await query.answer(f"Hello {query.from_user.first_name},\nSend New Request Again!", show_alert=True)
        return

    files, n_offset, total = await get_search_results(search, offset=offset)
    try:
        n_offset = int(n_offset)
    except:
        n_offset = 0

    if not files:
        return
    
    temp.FILES[key] = files
    settings = await get_settings(query.message.chat.id)
    del_msg = f"\n\n<b>⚠️ ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴀꜰᴛᴇʀ <code>{get_readable_time(DELETE_TIME)}</code> ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs</b>" if settings["auto_delete"] else ''
    
    # Simple file links format
    files_text = f"<b>📁 Found {total} Files</b>\n\n"
    for file_num, file in enumerate(files, start=offset+1):
        files_text += f"{file_num}. <a href='https://t.me/{temp.U_NAME}?start=file_{query.message.chat.id}_{file['_id']}'>{file['file_name']}</a> - {get_size(file['file_size'])}\n"

    # Navigation buttons
    btn = []
    if 0 < offset <= MAX_BTN:
        off_set = 0
    elif offset == 0:
        off_set = None
    else:
        off_set = offset - MAX_BTN
        
    if n_offset == 0:
        btn.append(
            [InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data=f"next_{req}_{key}_{off_set}"),
             InlineKeyboardButton(f"{math.ceil(int(offset) / MAX_BTN) + 1}/{math.ceil(total / MAX_BTN)}", callback_data="buttons")]
        )
    elif off_set is None:
        btn.append(
            [InlineKeyboardButton(f"{math.ceil(int(offset) / MAX_BTN) + 1}/{math.ceil(total / MAX_BTN)}", callback_data="buttons"),
             InlineKeyboardButton("ɴᴇxᴛ »", callback_data=f"next_{req}_{key}_{n_offset}")])
    else:
        btn.append(
            [
                InlineKeyboardButton("« ʙᴀᴄᴋ", callback_data=f"next_{req}_{key}_{off_set}"),
                InlineKeyboardButton(f"{math.ceil(int(offset) / MAX_BTN) + 1}/{math.ceil(total / MAX_BTN)}", callback_data="buttons"),
                InlineKeyboardButton("ɴᴇxᴛ »", callback_data=f"next_{req}_{key}_{n_offset}")
            ]
        )
    
    btn.append([InlineKeyboardButton("♻️ sᴇɴᴅ ᴀʟʟ", callback_data=f"send_all#{key}#{req}")])
    btn.append([InlineKeyboardButton('❌ ᴄʟᴏsᴇ', callback_data='close_data')])
    
    await query.message.edit_text(cap + "\n\n" + files_text + del_msg, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)

@Client.on_callback_query()
async def cb_handler(client: Client, query: CallbackQuery):
    if query.data == "close_data":
        try:
            user = query.message.reply_to_message.from_user.id
        except:
            user = query.from_user.id
        if int(user) != 0 and query.from_user.id != int(user):
            return await query.answer(f"Hello {query.from_user.first_name},\nThis Is Not For You!", show_alert=True)
        await query.answer("Closed!")
        await query.message.delete()
        try:
            await query.message.reply_to_message.delete()
        except:
            pass
  


    elif query.data == "buttons":
        await query.answer()

    elif query.data == "start":
        buttons = [[
            InlineKeyboardButton("+ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ +", url=f'http://t.me/{temp.U_NAME}?startgroup=start')
        ],[
            InlineKeyboardButton('👨‍🚒 ʜᴇʟᴘ', callback_data='help'),
            InlineKeyboardButton('📚 ᴀʙᴏᴜᴛ', callback_data='about')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_media(
            InputMediaPhoto(PICS[0] if PICS else "https://graph.org/file/placeholder.jpg", caption=script.START_TXT.format(query.from_user.mention, get_wish())),
            reply_markup=reply_markup
        )
        
    elif query.data == "about":
        buttons = [[
            InlineKeyboardButton('📊 sᴛᴀᴛᴜs', callback_data='stats')
        ],[
            InlineKeyboardButton('« ʙᴀᴄᴋ', callback_data='start')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_media(
            InputMediaPhoto(PICS[0] if PICS else "https://graph.org/file/placeholder.jpg", caption=script.MY_ABOUT_TXT),
            reply_markup=reply_markup
        )

    elif query.data == "stats":
        if query.from_user.id not in ADMINS:
            return await query.answer("ADMINS Only!", show_alert=True)
        files = db_count_documents()
        users = await db.total_users_count()
        chats = await db.total_chat_count()
        prm = db.get_premium_count()
        used_files_db_size = get_size(await db.get_files_db_size())
        used_data_db_size = get_size(await db.get_data_db_size())
        uptime = get_readable_time(time_now() - temp.START_TIME)
        
        buttons = [[InlineKeyboardButton('« ʙᴀᴄᴋ', callback_data='about')]]
        await query.edit_message_media(
            InputMediaPhoto(PICS[0] if PICS else "https://graph.org/file/placeholder.jpg", 
                          caption=f"<b>📊 Bot Statistics</b>\n\n👥 Users: {users}\n💎 Premium: {prm}\n👥 Chats: {chats}\n📁 Files: {files}\n💾 DB Size: {used_data_db_size}\n⏰ Uptime: {uptime}"),
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        
    elif query.data == "help":
        buttons = [[
            InlineKeyboardButton('User Command', callback_data='user_command'),
            InlineKeyboardButton('Admin Command', callback_data='admin_command')
        ],[
            InlineKeyboardButton('« ʙᴀᴄᴋ', callback_data='start')
        ]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_media(
            InputMediaPhoto(PICS[0] if PICS else "https://graph.org/file/placeholder.jpg", caption=script.HELP_TXT.format(query.from_user.mention)),
            reply_markup=reply_markup
        )

    elif query.data == "user_command":
        buttons = [[InlineKeyboardButton('« ʙᴀᴄᴋ', callback_data='help')]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_media(
            InputMediaPhoto(PICS[0] if PICS else "https://graph.org/file/placeholder.jpg", caption=script.USER_COMMAND_TXT),
            reply_markup=reply_markup
        )
        
    elif query.data == "admin_command":
        if query.from_user.id not in ADMINS:
            return await query.answer("ADMINS Only!", show_alert=True)
        buttons = [[InlineKeyboardButton('« ʙᴀᴄᴋ', callback_data='help')]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_media(
            InputMediaPhoto(PICS[0] if PICS else "https://graph.org/file/placeholder.jpg", caption=script.ADMIN_COMMAND_TXT),
            reply_markup=reply_markup
        )
     
    elif query.data.startswith("send_all"):
        ident, key, req = query.data.split("#")
        if int(req) != query.from_user.id:
            return await query.answer(f"Hello {query.from_user.first_name},\nDon't Click Other Results!", show_alert=True)        
        files = temp.FILES.get(key)
        if not files:
            await query.answer(f"Hello {query.from_user.first_name},\nSend New Request Again!", show_alert=True)
            return        
        await query.answer(url=f"https://t.me/{temp.U_NAME}?start=all_{query.message.chat.id}_{key}")

    elif query.data.startswith("delete"):
        _, query_ = query.data.split("_", 1)
        await query.message.edit('Deleting...')
        deleted = await delete_files(query_)
        await query.message.edit(f'Deleted {deleted} files in your database in your query {query_}')

async def auto_filter(client, msg, s, spoll=False):
    message = msg
    settings = await get_settings(message.chat.id)
    search = re.sub(r"\s+", " ", re.sub(r"[-:\"';!]", " ", message.text)).strip()
    files, offset, total_results = await get_search_results(search)
    
    if not files:
        await s.edit(f'❌ I cant find <b>{search}</b>')
        return
    
    req = message.from_user.id if message and message.from_user else 0
    key = f"{message.chat.id}-{message.id}"
    temp.FILES[key] = files
    BUTTONS[key] = search
    
    # Simple file links
    files_text = f"<b>📁 Found {total_results} Files</b>\n\n"
    for file_num, file in enumerate(files[:10], start=1):
        files_text += f"{file_num}. <a href='https://t.me/{temp.U_NAME}?start=file_{message.chat.id}_{file['_id']}'>{file['file_name']}</a> - {get_size(file['file_size'])}\n"
    
    btn = []
    if offset != "":
        btn.append(
            [InlineKeyboardButton(text=f"1/{math.ceil(int(total_results) / MAX_BTN)}", callback_data="buttons"),
             InlineKeyboardButton(text="ɴᴇxᴛ »", callback_data=f"next_{req}_{key}_{offset}")]
        )
    
    btn.append([InlineKeyboardButton("♻️ sᴇɴᴅ ᴀʟʟ", callback_data=f"send_all#{key}#{req}")])
    btn.append([InlineKeyboardButton('❌ ᴄʟᴏsᴇ', callback_data='close_data')])
    
    cap = f"<b>💭 ʜᴇʏ {message.from_user.mention},\n♻️ ʜᴇʀᴇ ɪ ꜰᴏᴜɴᴅ ꜰᴏʀ ʏᴏᴜʀ sᴇᴀʀᴄʜ {search}...</b>"
    CAP[key] = cap
    del_msg = f"\n\n<b>⚠️ ᴛʜɪs ᴍᴇssᴀɢᴇ ᴡɪʟʟ ʙᴇ ᴀᴜᴛᴏ ᴅᴇʟᴇᴛᴇ ᴀꜰᴛᴇʀ <code>{get_readable_time(DELETE_TIME)}</code> ᴛᴏ ᴀᴠᴏɪᴅ ᴄᴏᴘʏʀɪɢʜᴛ ɪssᴜᴇs</b>" if settings["auto_delete"] else ''
    
    k = await s.edit_text(cap + "\n\n" + files_text + del_msg, reply_markup=InlineKeyboardMarkup(btn), disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)
    
    if settings["auto_delete"]:
        await asyncio.sleep(DELETE_TIME)
        await k.delete()
        try:
            await message.delete()
        except:
            pass
