import asyncio
import time
from datetime import datetime, timedelta
from hydrogram import Client, filters, enums
from hydrogram.types import ChatPermissions
from database.users_chats_db import db

# =========================
# SMART CACHE (AUTO CLEAR)
# =========================
SETTINGS_CACHE = {}
CACHE_TTL = 300  # 5 मिनट बाद Cache Expire हो जाएगा

async def get_settings(chat_id):
    current_time = time.time()
    # अगर Cache मौजूद है और 5 मिनट से पुराना नहीं है, तो वही यूज़ करो
    if chat_id in SETTINGS_CACHE:
        data, timestamp = SETTINGS_CACHE[chat_id]
        if current_time - timestamp < CACHE_TTL:
            return data

    # वरना DB से लाओ और टाइमस्टैम्प के साथ सेव करो
    data = await db.get_settings(chat_id) or {}
    SETTINGS_CACHE[chat_id] = (data, current_time)
    return data

async def update_local_settings(chat_id, data):
    # अपडेट करते वक्त टाइमस्टैम्प भी रिसेट करो
    SETTINGS_CACHE[chat_id] = (data, time.time())
    await db.update_settings(chat_id, data)

async def is_admin(c, chat_id, user_id):
    try:
        m = await c.get_chat_member(chat_id, user_id)
        return m.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER)
    except:
        return False

# =========================
# ADMIN ACTIONS
# =========================

@Client.on_message(filters.group & filters.reply & filters.command(["mute", "unmute", "ban", "warn", "resetwarn"]))
async def admin_action(c, m):
    if not await is_admin(c, m.chat.id, m.from_user.id): return
    
    cmd = m.command[0]
    user = m.reply_to_message.from_user
    chat_id = m.chat.id

    if cmd == "mute":
        until = datetime.utcnow() + timedelta(seconds=600)
        await c.restrict_chat_member(chat_id, user.id, ChatPermissions(), until_date=until)
        await m.reply(f"🔇 {user.mention} muted for 10m.")

    elif cmd == "unmute":
        await c.restrict_chat_member(chat_id, user.id, ChatPermissions(can_send_messages=True))
        await m.reply(f"🔊 {user.mention} unmuted.")

    elif cmd == "ban":
        await c.ban_chat_member(chat_id, user.id)
        await m.reply(f"🚫 {user.mention} banned.")

    elif cmd == "warn":
        data = await db.get_warn(user.id, chat_id) or {"count": 0}
        data["count"] += 1
        await db.set_warn(user.id, chat_id, data)
        await m.reply(f"⚠️ {user.mention} warned ({data['count']}/3).")

    elif cmd == "resetwarn":
        await db.clear_warn(user.id, chat_id)
        await m.reply(f"♻️ Warnings reset for {user.mention}.")

# =========================
# CONFIGURATION
# =========================

@Client.on_message(filters.group & filters.command(["addblacklist", "removeblacklist", "dlink", "removedlink"]))
async def config_handler(c, m):
    if not await is_admin(c, m.chat.id, m.from_user.id): return
    if len(m.command) < 2: return

    cmd = m.command[0]
    data = await get_settings(m.chat.id)
    args = m.text.split(None, 1)[1] if len(m.text.split()) > 1 else ""
    
    # --- Blacklist Logic ---
    if "blacklist" in cmd:
        bl = data.get("blacklist", [])
        word = args.lower()
        if cmd == "addblacklist":
            if word not in bl: bl.append(word)
            msg = f"➕ Added `{word}` to blacklist."
        else:
            if word in bl: bl.remove(word)
            msg = f"➖ Removed `{word}` from blacklist."   
        data["blacklist"] = bl
        await update_local_settings(m.chat.id, data)
        await m.reply(msg)

    # --- DLink Logic ---
    elif "dlink" in cmd:
        dl = data.get("dlink", {})
        if cmd == "dlink":
            parts = m.text.split()
            delay = 300 
            idx = 1
            if len(parts) > 2 and parts[1][-1] in "mh" and parts[1][:-1].isdigit():
                delay = int(parts[1][:-1]) * (60 if parts[1][-1] == "m" else 3600)
                idx = 2
            word = " ".join(parts[idx:]).lower()
            dl[word] = delay
            msg = f"🕒 DLink set: `{word}` -> {delay}s (For Everyone)"
        else:
            word = args.lower()
            dl.pop(word, None)
            msg = f"🗑️ DLink removed: `{word}`"
        data["dlink"] = dl
        await update_local_settings(m.chat.id, data)
        await m.reply(msg)

@Client.on_message(filters.group & filters.command(["blacklist", "dlinklist"]))
async def view_lists(c, m):
    if not await is_admin(c, m.chat.id, m.from_user.id): return
    data = await get_settings(m.chat.id)
    
    if "blacklist" in m.command[0]:
        items = data.get("blacklist", [])
        text = "\n".join(f"• `{w}`" for w in items) or "📭 Empty"
        await m.reply(f"🚫 **Blacklist:**\n{text}")
    else:
        items = data.get("dlink", {})
        text = "\n".join(f"• `{k}` ({v}s)" for k, v in items.items()) or "📭 Empty"
        await m.reply(f"🕒 **DLinks:**\n{text}")

# =========================
# SMART WATCHER (UPDATED)
# =========================

async def delayed_delete(msg, delay):
    await asyncio.sleep(delay)
    try: await msg.delete()
    except: pass

@Client.on_message(filters.group & filters.text, group=10)
async def chat_watcher(c, m):
    if not m.from_user: return
    
    # 1. डेटा लाओ (Auto Cache Check)
    data = await get_settings(m.chat.id)
    text = m.text.lower()
    
    # 2. Check if Admin (सिर्फ Blacklist के लिए चेक करेंगे)
    is_adm = await is_admin(c, m.chat.id, m.from_user.id)

    # --- BLOCK A: DLink (APPLIES TO EVERYONE - Even Admins) ---
    dlinks = data.get("dlink", {})
    for w, delay in dlinks.items():
        if w in text or (w.endswith("*") and text.startswith(w[:-1])):
            asyncio.create_task(delayed_delete(m, delay))
            # अगर Dlink मिल गया, तो हम यहीं रुक सकते हैं या Blacklist चेक कर सकते हैं।
            # आमतौर पर अगर मैसेज डिलीट होना है, तो Blacklist चेक करने की जरूरत नहीं।
            return 

    # --- BLOCK B: Blacklist (APPLIES TO MEMBERS ONLY) ---
    if not is_adm: # अगर एडमिन नहीं है, तभी ब्लैकलिस्ट चेक करो
        blacklist = data.get("blacklist", [])
        for w in blacklist:
            if w in text or (w.endswith("*") and text.startswith(w[:-1])):
                await m.delete()
                return

# =========================
# ANTI BOT & HELP
# =========================

@Client.on_message(filters.new_chat_members)
async def anti_bot(c, m):
    for u in m.new_chat_members:
        if u.is_bot and not await is_admin(c, m.chat.id, m.from_user.id):
            await c.ban_chat_member(m.chat.id, u.id)

@Client.on_message(filters.group & filters.command("help"))
async def help_cmd(c, m):
    if await is_admin(c, m.chat.id, m.from_user.id):
        await m.reply(
            "🛠️ **Admin Menu**\n"
            "• `/mute`, `/unmute`, `/ban`, `/warn`\n"
            "• `/addblacklist`, `/removeblacklist`\n"
            "• `/dlink <word>` (Deletes for Admins too!)\n"
            "• `/removedlink`, `/dlinklist`"
        )

