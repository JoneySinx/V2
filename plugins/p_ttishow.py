import random
import os
import sys
import asyncio
from hydrogram import Client, filters, enums
from hydrogram.errors import MessageTooLong
from info import ADMINS, LOG_CHANNEL, PICS
from database.users_chats_db import db
from utils import temp, get_settings
from Script import script

# ======================================================
# 👋 WELCOME MESSAGE
# ======================================================
@Client.on_chat_member_updated()
async def welcome(bot, message):
    if message.chat.type not in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        return
    
    if message.new_chat_member and not message.old_chat_member:
        # Bot Added to New Group
        if message.new_chat_member.user.id == temp.ME:
            user = message.from_user.mention if message.from_user else "Admin"
            await bot.send_photo(
                chat_id=message.chat.id, 
                photo=random.choice(PICS), 
                caption=f"👋 Hello {user},\n\nThanks for adding me to **{message.chat.title}**!\nDon't forget to make me Admin."
            )
            
            # Save to DB if not exists
            if not await db.get_chat(message.chat.id):
                total = await bot.get_chat_members_count(message.chat.id)
                username = f'@{message.chat.username}' if message.chat.username else 'Private'
                await bot.send_message(
                    LOG_CHANNEL, 
                    script.NEW_GROUP_TXT.format(message.chat.title, message.chat.id, username, total)
                )       
                await db.add_chat(message.chat.id, message.chat.title)
            return
        
        # User Joined Group
        settings = await get_settings(message.chat.id)
        if settings.get("welcome", True):
            # Default welcome logic if needed, currently just logging
            pass


# ======================================================
# 🔄 RESTART
# ======================================================
@Client.on_message(filters.command('restart') & filters.user(ADMINS))
async def restart_bot(bot, message):
    msg = await message.reply("🔄 Restarting...")
    with open('restart.txt', 'w+') as file:
        file.write(f"{msg.chat.id} {msg.id}")
    os.execl(sys.executable, sys.executable, "bot.py")


# ======================================================
# 🚪 LEAVE CHAT
# ======================================================
@Client.on_message(filters.command('leave') & filters.user(ADMINS))
async def leave_a_chat(bot, message):
    if len(message.command) < 2:
        return await message.reply('Usage: `/leave chat_id`')
    
    chat_id = message.command[1]
    try:
        await bot.leave_chat(int(chat_id))
        await message.reply(f"✅ Left chat `{chat_id}`")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")


# ======================================================
# 🚫 BAN / UNBAN CHAT (Blacklist Group)
# ======================================================
@Client.on_message(filters.command('ban_grp') & filters.user(ADMINS))
async def disable_chat(bot, message):
    if len(message.command) < 2:
        return await message.reply('Usage: `/ban_grp chat_id reason`')
    
    chat_id = message.command[1]
    reason = " ".join(message.command[2:]) or "Violation of Rules"
    
    try:
        chat_id = int(chat_id)
    except:
        return await message.reply("Invalid Chat ID")
    
    chat_data = await db.get_chat(chat_id)
    if not chat_data:
        return await message.reply("Chat not found in DB.")
    
    if chat_data.get('is_disabled'):
        return await message.reply("Chat already disabled.")
    
    await db.disable_chat(chat_id, reason)
    temp.BANNED_CHATS.append(chat_id)
    
    await message.reply(f"✅ Chat `{chat_id}` disabled.\nReason: {reason}")
    try:
        await bot.leave_chat(chat_id)
    except:
        pass


@Client.on_message(filters.command('unban_grp') & filters.user(ADMINS))
async def re_enable_chat(bot, message):
    if len(message.command) < 2:
        return await message.reply('Usage: `/unban_grp chat_id`')
    
    try:
        chat_id = int(message.command[1])
    except:
        return await message.reply("Invalid Chat ID")
    
    chat_data = await db.get_chat(chat_id)
    if not chat_data:
        return await message.reply("Chat not found in DB.")
        
    if not chat_data.get('is_disabled'):
        return await message.reply("Chat is not disabled.")
    
    await db.re_enable_chat(chat_id)
    if chat_id in temp.BANNED_CHATS:
        temp.BANNED_CHATS.remove(chat_id)
        
    await message.reply(f"✅ Chat `{chat_id}` re-enabled.")


# ======================================================
# 🔗 GENERATE INVITE LINK
# ======================================================
@Client.on_message(filters.command('invite_link') & filters.user(ADMINS))
async def gen_invite_link(bot, message):
    if len(message.command) < 2:
        return await message.reply('Usage: `/invite_link chat_id`')
    
    try:
        chat_id = int(message.command[1])
        link = await bot.create_chat_invite_link(chat_id)
        await message.reply(f"🔗 Invite Link: {link.invite_link}")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")


# ======================================================
# 🚫 BAN / UNBAN USER (Blacklist User)
# ======================================================
@Client.on_message(filters.command('ban_user') & filters.user(ADMINS))
async def ban_a_user(bot, message):
    if len(message.command) < 2:
        return await message.reply('Usage: `/ban_user user_id reason`')
    
    try:
        user_id = int(message.command[1])
        reason = " ".join(message.command[2:]) or "Banned by Admin"
    except:
        return await message.reply("Invalid User ID")
        
    if user_id in ADMINS:
        return await message.reply("❌ Cannot ban Admin!")
        
    ban_status = await db.get_ban_status(user_id)
    if ban_status.get('is_banned'):
        return await message.reply("User already banned.")
        
    await db.ban_user(user_id, reason)
    temp.BANNED_USERS.append(user_id)
    await message.reply(f"✅ User `{user_id}` Banned.\nReason: {reason}")


@Client.on_message(filters.command('unban_user') & filters.user(ADMINS))
async def unban_a_user(bot, message):
    if len(message.command) < 2:
        return await message.reply('Usage: `/unban_user user_id`')
    
    try:
        user_id = int(message.command[1])
    except:
        return await message.reply("Invalid User ID")
        
    ban_status = await db.get_ban_status(user_id)
    if not ban_status.get('is_banned'):
        return await message.reply("User is not banned.")
        
    await db.unban_user(user_id)
    if user_id in temp.BANNED_USERS:
        temp.BANNED_USERS.remove(user_id)
        
    await message.reply(f"✅ User `{user_id}` Unbanned.")


# ======================================================
# 📜 LIST USERS & CHATS (Optimized File Gen)
# ======================================================
@Client.on_message(filters.command('users') & filters.user(ADMINS))
async def list_users(bot, message):
    msg = await message.reply('🔄 Generating User List...')
    
    # Direct Async Iteration (Memory Efficient)
    count = 0
    with open('users.txt', 'w') as f:
        async for user in db.users.find({}):
            f.write(f"ID: {user['id']} | Name: {user.get('name', 'N/A')}\n")
            count += 1
            
    if count == 0:
        await msg.edit("📭 Database Empty.")
        os.remove('users.txt')
        return

    await message.reply_document(
        'users.txt', 
        caption=f"👥 Total Users: {count}"
    )
    await msg.delete()
    os.remove('users.txt')


@Client.on_message(filters.command('chats') & filters.user(ADMINS))
async def list_chats(bot, message):
    msg = await message.reply('🔄 Generating Chat List...')
    
    count = 0
    with open('chats.txt', 'w') as f:
        async for chat in db.groups.find({}):
            f.write(f"ID: {chat['id']} | Title: {chat.get('title', 'N/A')}\n")
            count += 1
            
    if count == 0:
        await msg.edit("📭 Database Empty.")
        os.remove('chats.txt')
        return

    await message.reply_document(
        'chats.txt', 
        caption=f"👥 Total Chats: {count}"
    )
    await msg.delete()
    os.remove('chats.txt')

