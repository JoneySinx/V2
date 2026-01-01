import os
import qrcode
import asyncio
import traceback
import pytz
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

# ─────────────────────────
# 🧠 MEMORY & CONFIG
# ─────────────────────────
VERIFY_CACHE = {}
IST = pytz.timezone("Asia/Kolkata")

# =========================
# 🔧 HELPERS
# =========================
def parse_expire_time(expire):
    if not expire: return None
    if isinstance(expire, datetime): return expire
    if isinstance(expire, str):
        try: return datetime.strptime(expire, "%Y-%m-%d %H:%M:%S")
        except: return None
    return None

def get_ist_str(dt):
    """Convert UTC/Local datetime to Indian Standard Time String"""
    if not dt: return "Unknown"
    try:
        # If dt is naive, assume it's server time (UTC usually on cloud)
        # Adjust as needed. Here just formatting for display.
        return dt.strftime("%d %B %Y, %I:%M %p") 
    except:
        return str(dt)

async def safe_delete(client, chat_id, message_ids):
    try: await client.delete_messages(chat_id, message_ids)
    except: pass

# =========================
# 💎 PREMIUM CHECKER (UTILS)
# =========================
async def is_premium(user_id, bot):
    if not IS_PREMIUM or user_id in ADMINS: return True
    
    mp = await db.get_plan(user_id)
    if mp.get("premium"):
        expire_dt = parse_expire_time(mp.get("expire"))
        
        if expire_dt and expire_dt < datetime.now():
            try:
                btn = [[InlineKeyboardButton("💎 Buy Premium", callback_data="buy_prem")]]
                await bot.send_message(user_id, "❌ **Plan Expired!**\nRenew with /plan", reply_markup=InlineKeyboardMarkup(btn))
            except: pass
            
            await db.update_plan(user_id, {"expire": "", "plan": "", "premium": False})
            return False
        return True
    return False

# =========================
# ⏰ ADVANCED REMINDER SYSTEM
# =========================
async def check_premium_expired(bot):
    while True:
        try:
            now = datetime.now()
            async for p in db.premium.find({"status.premium": True}):
                uid = p["id"]
                mp = p.get("status", {})
                exp_dt = parse_expire_time(mp.get("expire"))
                
                if not exp_dt: continue
                
                left_seconds = (exp_dt - now).total_seconds()
                left_minutes = left_seconds / 60
                
                msg = ""
                flag = ""
                
                # 1. EXPIRY HANDLER
                if left_seconds <= 0:
                    if mp.get("last_reminder_id"):
                        await safe_delete(bot, uid, [mp.get("last_reminder_id")])

                    btn = [[InlineKeyboardButton("💎 Buy Premium", callback_data="buy_prem")]]
                    try: 
                        await bot.send_message(
                            uid, 
                            "❌ **Your Premium Plan has Expired!**\n\n"
                            "Renew now to continue using our services.",
                            reply_markup=InlineKeyboardMarkup(btn)
                        )
                    except: pass
                    
                    await db.update_plan(uid, {
                        "expire": "", "plan": "", "premium": False, 
                        "reminded_12h": False, "reminded_6h": False, 
                        "reminded_3h": False, "reminded_1h": False, 
                        "reminded_30m": False, "reminded_10m": False,
                        "last_reminder_id": 0
                    })
                    continue

                # 2. INTERVAL CHECKER
                if 715 <= left_minutes <= 725 and not mp.get("reminded_12h"):
                    msg = f"⏰ **Premium Reminder**\n\nYour plan expires in **12 Hours**.\n🗓 {get_ist_str(exp_dt)}"
                    flag = "reminded_12h"
                
                elif 355 <= left_minutes <= 365 and not mp.get("reminded_6h"):
                    msg = f"⚠️ **Premium Alert**\n\nYour plan expires in **6 Hours**.\n🗓 {get_ist_str(exp_dt)}"
                    flag = "reminded_6h"
                
                elif 175 <= left_minutes <= 185 and not mp.get("reminded_3h"):
                    msg = f"⚠️ **Urgent Alert**\n\nYour plan expires in **3 Hours**.\n🗓 {get_ist_str(exp_dt)}"
                    flag = "reminded_3h"

                elif 55 <= left_minutes <= 65 and not mp.get("reminded_1h"):
                    msg = f"🚨 **Critical Alert**\n\nYour plan expires in **1 Hour**.\n🗓 {get_ist_str(exp_dt)}"
                    flag = "reminded_1h"

                elif 25 <= left_minutes <= 35 and not mp.get("reminded_30m"):
                    msg = f"⏳ **Final Warning**\n\nYour plan expires in **30 Minutes**.\nRenew immediately!"
                    flag = "reminded_30m"
                
                elif 5 <= left_minutes <= 15 and not mp.get("reminded_10m"):
                    msg = f"🔥 **Expiring Soon**\n\nYour plan expires in **10 Minutes**.\nService will stop soon."
                    flag = "reminded_10m"

                if msg:
                    if mp.get("last_reminder_id"):
                        await safe_delete(bot, uid, [mp.get("last_reminder_id")])
                    
                    btn = [[InlineKeyboardButton("💎 Renew Now", callback_data="buy_prem")]]
                    try:
                        sent_msg = await bot.send_message(uid, msg, reply_markup=InlineKeyboardMarkup(btn))
                        mp[flag] = True
                        mp["last_reminder_id"] = sent_msg.id
                        await db.update_plan(uid, mp)
                    except Exception:
                        pass

            await asyncio.sleep(60)
        except Exception as e:
            print(f"Premium Loop Error: {e}")
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
    ist_exp = get_ist_str(exp) if exp else "Unknown"
    left = str(exp - datetime.now()).split('.')[0] if exp else "Unknown"
    
    await m.reply(
        f"💎 **Premium Status**\n\n"
        f"📦 **Plan:** {mp.get('plan')}\n"
        f"🗓 **Expires:** {ist_exp} (IST)\n"
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
            "reminded_12h": False, "reminded_6h": False, "reminded_3h": False,
            "reminded_1h": False, "reminded_30m": False, "reminded_10m": False,
            "last_reminder_id": 0
        }
        msg_user = (
            f"🎉 **Premium Activated!**\n\n"
            f"🗓 **Duration:** {days} Days\n"
            f"📅 **Expires:** {get_ist_str(ex)} (IST)\n\n"
            f"Enjoy high speed & exclusive features! ❤️"
        )
        msg_admin = f"✅ Added {days} days premium to `{uid}`."
    else:
        data = {"expire": "", "plan": "", "premium": False}
        msg_user = "❌ **Premium Removed by Admin.**"
        msg_admin = f"🗑 Removed premium from `{uid}`."

    await db.update_plan(uid, data)
    await m.reply(msg_admin)
    try: await c.send_message(uid, msg_user)
    except: pass
    
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
# 🔘 CALLBACKS (FIXED FOR BUTTON ISSUE)
# =========================

# 1. BUY PREMIUM HANDLER (Handles both 'buy_prem' and 'activate_plan')
@Client.on_callback_query(filters.regex(r"^(buy_prem|activate_plan)$"))
async def buy_callback(c, q):
    prompt_msg = await q.message.edit(
        "💎 **Select Plan Duration**\n\n"
        "Send the number of days you want to buy (e.g. `30`).\n"
        f"Price: ₹{PRE_DAY_AMOUNT}/day\n\n"
        "⏳ Timeout: 60s"
    )
    
    try:
        resp = await c.listen(q.message.chat.id, timeout=60)
        await safe_delete(c, q.message.chat.id, [prompt_msg.id, resp.id])

        try:
            days = int(resp.text)
        except ValueError:
            return await q.message.reply("❌ Invalid Number! Please send numeric days (e.g., 30).")

        amount = days * int(PRE_DAY_AMOUNT)
        
        uri = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR"
        img = qrcode.make(uri)
        path = f"qr_{q.from_user.id}.png"
        img.save(path)
        
        qr_msg = await q.message.reply_photo(
            path,
            caption=f"💳 **Pay ₹{amount}**\n\nScan & Pay. Then send screenshot here.\n\n⏳ Timeout: 5 mins"
        )
        
        try: os.remove(path)
        except: pass
        
        receipt = await c.listen(q.message.chat.id, timeout=300)
        
        if not receipt.photo:
            return await q.message.reply("❌ **Invalid!** Please send a photo/screenshot.")
        
        # DELETE QR CODE
        await safe_delete(c, q.message.chat.id, [qr_msg.id])

        status_msg = await q.message.reply("✅ **Sent for Verification!**\nAdmin will activate shortly.")
        
        # SAVE MESSAGE ID TO DELETE LATER
        VERIFY_CACHE[q.from_user.id] = status_msg.id
        
        cap = f"#Payment\n👤: {q.from_user.mention} (`{q.from_user.id}`)\n💰: ₹{amount} ({days} days)"
        btn = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"pay_confirm_{q.from_user.id}_{days}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"pay_reject_{q.from_user.id}")
            ]
        ]
        
        try:
            await receipt.copy(RECEIPT_SEND_USERNAME, caption=cap, reply_markup=InlineKeyboardMarkup(btn))
        except Exception as e:
            await q.message.reply(f"❌ Error sending receipt to Admin.\nContact manually: {RECEIPT_SEND_USERNAME}")

    except asyncio.TimeoutError:
        await q.message.reply("⏳ **Timeout!** Process cancelled.")
    except Exception as e:
        traceback.print_exc()
        await q.message.reply(f"❌ **Error Occurred:** `{str(e)}`")


@Client.on_callback_query(filters.regex(r"^pay_(confirm|reject)_"))
async def payment_action_callback(c, q):
    if q.from_user.id not in ADMINS:
        return await q.answer("❌ Only Admins!", show_alert=True)

    data = q.data.split("_")
    action = data[1]
    user_id = int(data[2])

    if action == "confirm":
        days = int(data[3])
        
        ex = datetime.now() + timedelta(days=days)
        plan_data = {
            "expire": ex.strftime("%Y-%m-%d %H:%M:%S"),
            "plan": f"{days} Days",
            "premium": True,
            "reminded_12h": False, "reminded_6h": False, "reminded_3h": False,
            "reminded_1h": False, "reminded_30m": False, "reminded_10m": False,
            "last_reminder_id": 0
        }
        await db.update_plan(user_id, plan_data)
        
        new_caption = q.message.caption + f"\n\n✅ **Approved by** {q.from_user.mention}"
        await q.message.edit_caption(caption=new_caption, reply_markup=None)
        
        # DELETE "Sent for Verification" Message
        if user_id in VERIFY_CACHE:
            await safe_delete(c, user_id, [VERIFY_CACHE[user_id]])
            del VERIFY_CACHE[user_id]
        
        try:
            await c.send_message(
                user_id, 
                f"🎉 **Congratulations!**\n\n"
                f"✅ Your premium of **{days} Days** is Active.\n"
                f"📅 **Expires:** {get_ist_str(ex)} (IST)\n\n"
                f"Enjoy our service! ❤️"
            )
        except Exception:
            pass
            
    elif action == "reject":
        new_caption = q.message.caption + f"\n\n❌ **Rejected by** {q.from_user.mention}"
        await q.message.edit_caption(caption=new_caption, reply_markup=None)
        
        if user_id in VERIFY_CACHE:
            await safe_delete(c, user_id, [VERIFY_CACHE[user_id]])
            del VERIFY_CACHE[user_id]
        
        try:
            await c.send_message(
                user_id,
                "❌ **Payment Rejected!**\n\n"
                "Your payment was rejected by admin.\n"
                "Please contact admin manually."
            )
        except Exception:
            pass

