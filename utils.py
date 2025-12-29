import asyncio
import re
from datetime import datetime
from hydrogram.errors import FloodWait
from hydrogram import enums
from hydrogram.types import InlineKeyboardButton

from info import ADMINS, IS_PREMIUM, TIME_ZONE
from database.users_chats_db import db


# ─────────────────────────────────────────────
# 🧠 TEMP RUNTIME STORAGE
# ─────────────────────────────────────────────
class temp(object):
    START_TIME = 0
    BANNED_USERS = []
    BANNED_CHATS = []
    ME = None
    CANCEL = False
    U_NAME = None
    B_NAME = None
    SETTINGS = {}
    FILES = {}
    USERS_CANCEL = False
    GROUPS_CANCEL = False
    BOT = None
    PREMIUM = {}


# ─────────────────────────────────────────────
# 👮 ADMIN CHECK
# ─────────────────────────────────────────────
async def is_check_admin(bot, chat_id, user_id):
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in (
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER
        )
    except Exception:
        return False


# ─────────────────────────────────────────────
# 💎 PREMIUM SYSTEM
# ─────────────────────────────────────────────
async def is_premium(user_id, bot):
    if not IS_PREMIUM:
        return True
    if user_id in ADMINS:
        return True

    mp = db.get_plan(user_id)
    if mp.get("premium"):
        if mp.get("expire") and mp["expire"] < datetime.now():
            try:
                await bot.send_message(
                    user_id,
                    f"Your premium {mp.get('plan')} plan has expired."
                )
            except Exception:
                pass

            mp.update({
                "expire": "",
                "plan": "",
                "premium": False
            })
            db.update_plan(user_id, mp)
            return False
        return True
    return False


async def check_premium(bot):
    while True:
        for p in db.get_premium_users():
            mp = p.get("status", {})
            if mp.get("premium") and mp.get("expire") < datetime.now():
                try:
                    await bot.send_message(
                        p["id"],
                        f"Your premium {mp.get('plan')} plan has expired."
                    )
                except Exception:
                    pass

                mp.update({
                    "expire": "",
                    "plan": "",
                    "premium": False
                })
                db.update_plan(p["id"], mp)

        await asyncio.sleep(1200)


# ─────────────────────────────────────────────
# 📢 BROADCAST
# ─────────────────────────────────────────────
async def broadcast_messages(user_id, message, pin=False):
    try:
        msg = await message.copy(chat_id=user_id)
        if pin:
            await msg.pin(both_sides=True)
        return "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await broadcast_messages(user_id, message, pin)
    except Exception:
        await db.delete_user(int(user_id))
        return "Error"


async def groups_broadcast_messages(chat_id, message, pin=False):
    try:
        msg = await message.copy(chat_id=chat_id)
        if pin:
            try:
                await msg.pin()
            except Exception:
                pass
        return "Success"
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await groups_broadcast_messages(chat_id, message, pin)
    except Exception:
        await db.delete_chat(chat_id)
        return "Error"


# ─────────────────────────────────────────────
# ⚙️ GROUP SETTINGS (CACHE)
# ─────────────────────────────────────────────
async def get_settings(group_id):
    settings = temp.SETTINGS.get(group_id)
    if not settings:
        settings = await db.get_settings(group_id)
        temp.SETTINGS[group_id] = settings
    return settings


async def save_group_settings(group_id, key, value):
    current = await get_settings(group_id)
    current[key] = value
    temp.SETTINGS[group_id] = current
    await db.update_settings(group_id, current)


# ─────────────────────────────────────────────
# 📦 UTILS
# ─────────────────────────────────────────────
def get_size(size):
    units = ["Bytes", "KB", "MB", "GB", "TB"]
    size = float(size)
    i = 0
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{size:.2f} {units[i]}"


def get_readable_time(seconds):
    periods = [('d', 86400), ('h', 3600), ('m', 60), ('s', 1)]
    result = ''
    for name, sec in periods:
        if seconds >= sec:
            val, seconds = divmod(seconds, sec)
            result += f"{int(val)}{name}"
    return result or "0s"


def get_wish():
    hour = datetime.now().hour
    if hour < 12:
        return "ɢᴏᴏᴅ ᴍᴏʀɴɪɴɢ 🌞"
    elif hour < 18:
        return "ɢᴏᴏᴅ ᴀꜰᴛᴇʀɴᴏᴏɴ 🌗"
    return "ɢᴏᴏᴅ ᴇᴠᴇɴɪɴɢ 🌘"


async def get_seconds(time_string):
    match = re.match(r"(\d+)(s|min|hour|day|month|year)", time_string)
    if not match:
        return 0

    value, unit = int(match.group(1)), match.group(2)

    return {
        "s": value,
        "min": value * 60,
        "hour": value * 3600,
        "day": value * 86400,
        "month": value * 86400 * 30,
        "year": value * 86400 * 365
    }.get(unit, 0)
