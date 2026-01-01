import os
import qrcode
import asyncio
from datetime import datetime, timedelta
from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from database.users_chats_db import db
from info import (
    IS_PREMIUM, 
    PRE_DAY_AMOUNT, 
    RECEIPT_SEND_USERNAME, 
    UPI_ID, 
    UPI_NAME, 
    ADMINS,
    LOG_CHANNEL
)
from Script import script
from utils import temp

# =========================
# 🔧 FAST HELPER
# =========================
def parse_expire_time(expire):
    if not expire: return None
    if isinstance(expire, datetime): return expire
    if isinstance(expire, str):
        try: return datetime.strptime(expire, "%Y-%m-%d %H:%M:%S")
        except: return None
    return None

# =========================
# 💎 PREMIUM CHECKER
# =========================
async def is_premium(user_id, bot):
    if not IS_PREMIUM or user_id in ADMINS: return True
    
    mp = await db.get_plan(user_id) # Async Call
    if mp.get("premium"):
        expire_dt = parse_expire_time(mp.get("expire"))
        
        # Check Expiry
        if expire_dt and expire_dt < datetime.now():
            try:
                await bot.send_message(user_id, "❌ **Plan Expired!**\nRenew with /plan")
            except: pass
            
            await db.update_plan(user_id, {
                "expire": "", "plan": "", "premium": False,
                "reminded_24h": False, "reminded_6h": False, "reminded_1h": False
            })
            return False
        return True
    return False

# =========================
# ⏰ BACKGROUND TASK
# =========================
async def check_premium_expired(bot):
    while True:
        try:
            now = datetime.now()
            # Async Cursor Iteration
            async for p in db.premium.find({"status.premium": True}):
                uid = p["id"]
                mp = p.get("status", {})
                exp_dt = parse_expire_time(mp.get("expire"))
                
                if not exp_dt: continue
                
                left = (exp_dt - now).total_seconds()
                
                # 1. Handle Expiry
                if left <= 0:
                    await db.update_plan(uid, {"expire": "", "plan": "", "premium": False})
                    try: await bot.send_message(uid, "❌ **Plan Expired!**\nUse /plan to renew.")
                    except: pass
                    continue
                
                # 2. Smart Reminders (24h, 6h, 1h)
                hours = left / 3600
                msg = ""
                flag = ""
                
                if 23.5 <= hours <= 24.5 and not mp.get("reminded_24h"):
                    msg = "⏰ Plan expires in **24 Hours**!"
                    flag = "reminded_24h"
                elif 5.5 <= hours <= 6.5 and not mp.get("reminded_6h"):
                    msg = "⚠️ Plan expires in **6 Hours**!"
                    flag = "reminded_6h"
                elif 0.5 <= hours <= 1.5 and not mp.get("reminded_1h"):
                    msg = "🚨 Plan expires in **1 Hour**!"
                    flag = "reminded_1h"

                if msg:
                    try: await bot.send_message(uid, msg + "\nRenew: /plan")
                    except: pass
                    mp[flag] = True
                    await db.update_plan(uid, mp)

            await asyncio.sleep(1200) # Check every 20 mins
        except Exception as e:
            print(f"Premium Task Error: {e}")
            await asyncio.sleep(60)

# =========================
# 📱 USER COMMANDS
# =========================

@Client.on_message(filters.command("myplan") & filters.private)
async def myplan_cmd(c, m):
    if not IS_PREMIUM: return
    
    mp = await db.get_plan(m.from_user.id)
    if not mp.get("premium"):
        btn = [[InlineKeyboardButton("💎 Buy Premium", callback_data="buy_prem")]]
        return await m.reply("❌ **No Active Plan**\nTap below to buy!", reply_markup=InlineKeyboardMarkup(btn))
    
    exp = parse_expire_time(mp.get("expire"))
    left = str(exp - datetime.now()).split('.')[0] if exp else "Unknown"
    
    await m.reply(
        f"💎 **Premium Status**\n\n"
        f"📦 **Plan:** {mp.get('plan')}\n"
        f"⏳ **Expires:** {exp}\n"
        f"⏲ **Time Left:** {left}",
        quote=True
    )

@Client.on_message(filters.command("plan") & filters.private)
async def plan_cmd(c, m):
    if not IS_PREMIUM: return
    
    btn = [[InlineKeyboardButton("💎 Activate Premium", callback_data="buy_prem")]]
    await m.reply(script.PLAN_TXT.format(PRE_DAY_AMOUNT, RECEIPT_SEND_USERNAME), reply_markup=InlineKeyboardMarkup(btn))

# =========================
# 👨‍💼 ADMIN COMMANDS
# =========================

@Client.on_message(filters.command(["add_prm", "rm_prm"]) & filters.user(ADMINS))
async def manage_premium(c, m):
    if not IS_PREMIUM: return
    
    cmd = m.command
    is_add = cmd[0] == "add_prm"
    
    if len(cmd) < 2:
        return await m.reply(f"Usage: `/{cmd[0]} user_id {'days' if is_add else ''}`")
    
    try:
        uid = int(cmd[1])
        days = int(cmd[2][:-1]) if is_add and len(cmd) > 2 else 0
    except:
        return await m.reply("❌ Invalid Format!")

    if is_add:
        ex = datetime.now() + timedelta(days=days)
        data = {
            "expire": ex.strftime("%Y-%m-%d %H:%M:%S"),
            "plan": f"{days} Days",
            "premium": True,
            "reminded_24h": False, "reminded_6h": False, "reminded_1h": False
        }
        msg_user = f"🎉 **Premium Activated!**\n🗓 **Days:** {days}\n⏳ **Expires:** {data['expire']}"
        msg_admin = f"✅ Added {days} days premium to `{uid}`."
    else:
        data = {"expire": "", "plan": "", "premium": False}
        msg_user = "❌ **Premium Removed by Admin.**"
        msg_admin = f"🗑 Removed premium from `{uid}`."

    await db.update_plan(uid, data)
    await m.reply(msg_admin)
    try: await c.send_message(uid, msg_user)
    except: pass
    
    # Log
    try: await c.send_message(LOG_CHANNEL, f"#PremiumUpdate\nUser: `{uid}`\nAction: {cmd[0]}")
    except: pass

@Client.on_message(filters.command("prm_list") & filters.user(ADMINS))
async def prm_list(c, m):
    if not IS_PREMIUM: return
    
    msg = await m.reply("🔄 Fetching...")
    users = await db.get_premium_users()
    count = 0
    text = "💎 **Premium Users**\n\n"
    
    async for u in users:
        st = u.get("status", {})
        if st.get("premium"):
            count += 1
            text += f"👤 `{u['id']}` | 🗓 {st.get('plan')}\n"
    
    if count == 0: text = "📭 No premium users."
    else: text += f"\n**Total:** {count}"
    
    await msg.edit(text)

# =========================
# 🔘 CALLBACKS
# =========================

@Client.on_callback_query(filters.regex("^buy_prem$"))
async def buy_callback(c, q):
    await q.message.edit(
        "💎 **Select Plan Duration**\n\n"
        "Send the number of days you want to buy (e.g. `30`).\n"
        "Price: ₹1/day\n\n"
        "⏳ Timeout: 60s"
    )
    
    try:
        resp = await c.listen(q.message.chat.id, timeout=60)
        days = int(resp.text)
        amount = days * int(PRE_DAY_AMOUNT)
        
        # QR Code Generation
        uri = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR"
        img = qrcode.make(uri)
        path = f"qr_{q.from_user.id}.png"
        img.save(path)
        
        await q.message.reply_photo(
            path,
            caption=f"💳 **Pay ₹{amount}**\n\nScan & Pay. Then send screenshot here.\n\n⏳ Timeout: 5 mins"
        )
        os.remove(path)
        
        # Receipt Listener
        receipt = await c.listen(q.message.chat.id, filters.photo, timeout=300)
        
        # Forward to Admin
        cap = f"#Payment\n👤: {q.from_user.mention} (`{q.from_user.id}`)\n💰: ₹{amount} ({days} days)\ncmd: `/add_prm {q.from_user.id} {days}d`"
        try:
            await receipt.copy(RECEIPT_SEND_USERNAME, caption=cap) # Use Copy instead of Forward for privacy
            await q.message.reply("✅ **Sent for Verification!**\nAdmin will activate shortly.")
        except Exception as e:
            await q.message.reply(f"❌ Error sending receipt. Contact Admin manually.\nError: {e}")

    except Exception:
        await q.message.reply("⏳ **Timeout or Invalid Input.** Try again.")

