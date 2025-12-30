import os
import qrcode
import random
import asyncio
from datetime import datetime, timedelta
from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from hydrogram.errors import ListenerTimeout
from database.users_chats_db import db
from info import (
    IS_PREMIUM, 
    PRE_DAY_AMOUNT, 
    RECEIPT_SEND_USERNAME, 
    UPI_ID, 
    UPI_NAME, 
    ADMINS,
    PICS,
    LOG_CHANNEL
)
from Script import script
from utils import temp

# Global variable for trial status (default OFF)
TRIAL_ENABLED = False


# ─────────────────────────────────────────────
# 🔧 HELPER: Convert expire to datetime
# ─────────────────────────────────────────────
def parse_expire_time(expire):
    """
    Convert expire field to datetime object
    Handles both string and datetime formats
    """
    if not expire:
        return None
    
    if isinstance(expire, datetime):
        return expire
    
    if isinstance(expire, str):
        try:
            from dateutil import parser
            return parser.parse(expire)
        except:
            return None
    
    return None


# ─────────────────────────────────────────────
# 💎 PREMIUM CHECK (Synced with utils.py)
# ─────────────────────────────────────────────
async def is_premium(user_id, bot):
    """Check if user has active premium subscription"""
    if not IS_PREMIUM:
        return True
    if user_id in ADMINS:
        return True

    mp = db.get_plan(user_id)
    if mp.get("premium"):
        expire = mp.get("expire")
        
        # ✅ Convert to datetime if needed
        expire_dt = parse_expire_time(expire)
        
        if expire_dt:
            # Check if expired
            if expire_dt < datetime.now():
                try:
                    await bot.send_message(
                        user_id,
                        f"❌ Your premium {mp.get('plan')} plan has expired.\n\nUse /plan to renew your subscription."
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


# ─────────────────────────────────────────────
# ⏰ PREMIUM EXPIRY CHECKER & REMINDER
# ─────────────────────────────────────────────
async def check_premium_expired(bot):
    """
    Background task that runs every 20 minutes to:
    1. Check expired premium users
    2. Send expiry reminders (24h, 6h, 1h before expiry)
    """
    while True:
        try:
            current_time = datetime.now()
            
            for p in db.get_premium_users():
                user_id = p.get("id")
                mp = p.get("status", {})
                
                if mp.get("premium") and mp.get("expire"):
                    # ✅ Convert to datetime
                    expire_time = parse_expire_time(mp["expire"])
                    
                    if not expire_time:
                        continue
                    
                    time_left = expire_time - current_time
                    
                    # Check if expired
                    if time_left.total_seconds() <= 0:
                        try:
                            await bot.send_message(
                                user_id,
                                f"❌ Your premium {mp.get('plan')} plan has expired.\n\n"
                                f"Expired on: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                                f"Use /plan to renew your subscription."
                            )
                        except Exception as e:
                            print(f"Failed to notify user {user_id}: {e}")

                        mp.update({
                            "expire": "",
                            "plan": "",
                            "premium": False
                        })
                        db.update_plan(user_id, mp)
                        
                        # Log to admin channel
                        try:
                            await bot.send_message(
                                LOG_CHANNEL,
                                f"#PremiumExpired\n\n"
                                f"User ID: {user_id}\n"
                                f"Plan: {mp.get('plan', 'Unknown')}\n"
                                f"Expired: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}"
                            )
                        except:
                            pass
                    
                    # Send reminders
                    else:
                        hours_left = time_left.total_seconds() / 3600
                        
                        # 24 hour reminder
                        if 23.5 <= hours_left <= 24.5 and not mp.get("reminded_24h"):
                            try:
                                await bot.send_message(
                                    user_id,
                                    f"⏰ <b>Premium Expiry Reminder</b>\n\n"
                                    f"Your premium {mp.get('plan')} plan will expire in 24 hours.\n"
                                    f"Expiry time: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                                    f"Use /plan to renew your subscription.",
                                    parse_mode=enums.ParseMode.HTML
                                )
                                mp["reminded_24h"] = True
                                db.update_plan(user_id, mp)
                            except Exception as e:
                                print(f"Failed to send 24h reminder to {user_id}: {e}")
                        
                        # 6 hour reminder
                        elif 5.5 <= hours_left <= 6.5 and not mp.get("reminded_6h"):
                            try:
                                await bot.send_message(
                                    user_id,
                                    f"⚠️ <b>Premium Expiry Alert</b>\n\n"
                                    f"Your premium {mp.get('plan')} plan will expire in 6 hours.\n"
                                    f"Expiry time: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                                    f"Use /plan to renew now!",
                                    parse_mode=enums.ParseMode.HTML
                                )
                                mp["reminded_6h"] = True
                                db.update_plan(user_id, mp)
                            except Exception as e:
                                print(f"Failed to send 6h reminder to {user_id}: {e}")
                        
                        # 1 hour reminder
                        elif 0.5 <= hours_left <= 1.5 and not mp.get("reminded_1h"):
                            try:
                                await bot.send_message(
                                    user_id,
                                    f"🚨 <b>URGENT: Premium Expiring Soon</b>\n\n"
                                    f"Your premium {mp.get('plan')} plan will expire in 1 hour!\n"
                                    f"Expiry time: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                                    f"Renew immediately to avoid service interruption: /plan",
                                    parse_mode=enums.ParseMode.HTML
                                )
                                mp["reminded_1h"] = True
                                db.update_plan(user_id, mp)
                            except Exception as e:
                                print(f"Failed to send 1h reminder to {user_id}: {e}")
            
            # Check every 20 minutes (1200 seconds)
            await asyncio.sleep(1200)
            
        except Exception as e:
            print(f"Error in check_premium_expired: {e}")
            await asyncio.sleep(1200)


# ─────────────────────────────────────────────
# 📱 USER COMMANDS
# ─────────────────────────────────────────────
@Client.on_message(filters.command('myplan') & filters.private)
async def myplan(client: Client, message: Message):
    """Check user's current premium plan"""
    global TRIAL_ENABLED
    
    if not IS_PREMIUM:
        return await message.reply('Premium feature was disabled by admin')
    
    mp = db.get_plan(message.from_user.id)
    
    if not await is_premium(message.from_user.id, client):
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
        
        return await message.reply(
            '❌ You dont have any premium plan.\n\nUse /plan to activate premium subscription.', 
            reply_markup=InlineKeyboardMarkup(btn)
        )
    
    # ✅ Convert expire to datetime
    expire_time = parse_expire_time(mp.get('expire'))
    
    if not expire_time:
        return await message.reply(
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
    
    await message.reply(
        f"✅ <b>Your Premium Status</b>\n\n"
        f"📦 Plan: {mp.get('plan', 'Unknown')}\n"
        f"⏰ Expires: {expire_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⏳ Time Left: {days_left} days {hours_left} hours\n\n"
        f"💡 Use /plan to extend your subscription.",
        parse_mode=enums.ParseMode.HTML
    )


@Client.on_message(filters.command('plan') & filters.private)
async def plan(client: Client, message: Message):
    """Show premium plans and activation options"""
    global TRIAL_ENABLED
    
    if not IS_PREMIUM:
        return await message.reply('Premium feature was disabled by admin')
    
    btn = []
    
    # Only show trial button if enabled
    if TRIAL_ENABLED:
        btn.append([InlineKeyboardButton('🎁 Activate Trial (1 Hour Free)', callback_data='activate_trial')])
    
    btn.append([InlineKeyboardButton('💎 Buy Premium Plan', callback_data='activate_plan')])
    
    await message.reply(
        script.PLAN_TXT.format(PRE_DAY_AMOUNT, RECEIPT_SEND_USERNAME), 
        reply_markup=InlineKeyboardMarkup(btn)
    )


# ─────────────────────────────────────────────
# 👨‍💼 ADMIN COMMANDS
# ─────────────────────────────────────────────
@Client.on_message(filters.command('add_prm') & filters.user(ADMINS))
async def add_premium(bot: Client, message: Message):
    """Admin command to add premium to users"""
    if not IS_PREMIUM:
        return await message.reply('Premium feature was disabled')
    
    try:
        _, user_id, d = message.text.split(' ')
    except:
        return await message.reply(
            '<b>Usage:</b> <code>/add_prm user_id 1d</code>\n\n'
            '<b>Examples:</b>\n'
            '• <code>/add_prm 123456789 7d</code> - 7 days\n'
            '• <code>/add_prm 123456789 30d</code> - 30 days\n'
            '• <code>/add_prm 123456789 365d</code> - 365 days',
            parse_mode=enums.ParseMode.HTML
        )
    
    try:
        days = int(d[:-1])
    except:
        return await message.reply('❌ Not valid days format. Use: 1d, 7d, 30d, 365d, etc...')
    
    try:
        user = await bot.get_users(user_id)
    except Exception as e:
        return await message.reply(f'❌ Error: {e}')
    
    if user.id in ADMINS:
        return await message.reply('ℹ️ ADMINS already have premium access')
    
    if not await is_premium(user.id, bot):
        mp = db.get_plan(user.id)
        ex = datetime.now() + timedelta(days=days)
        mp['expire'] = ex
        mp['plan'] = f'{days} days'
        mp['premium'] = True
        mp['reminded_24h'] = False
        mp['reminded_6h'] = False
        mp['reminded_1h'] = False
        db.update_plan(user.id, mp)
        
        await message.reply(
            f"✅ Successfully granted premium to {user.mention}\n\n"
            f"📦 Plan: {days} days\n"
            f"⏰ Expires: {ex.strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode=enums.ParseMode.HTML
        )
        
        try:
            await bot.send_message(
                user.id, 
                f"🎉 Congratulations! You are now a premium user.\n\n"
                f"📦 Plan: {days} days\n"
                f"⏰ Expires: {ex.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"Enjoy unlimited access!",
                parse_mode=enums.ParseMode.HTML
            )
        except:
            pass
        
        # Log to admin channel
        try:
            await bot.send_message(
                LOG_CHANNEL,
                f"#PremiumGranted\n\n"
                f"User: {user.mention}\n"
                f"User ID: {user.id}\n"
                f"Plan: {days} days\n"
                f"Granted by: {message.from_user.mention}\n"
                f"Expires: {ex.strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode=enums.ParseMode.HTML
            )
        except:
            pass
    else:
        await message.reply(f"ℹ️ {user.mention} is already a premium user")


@Client.on_message(filters.command('rm_prm') & filters.user(ADMINS))
async def remove_premium(bot: Client, message: Message):
    """Admin command to remove premium from users"""
    if not IS_PREMIUM:
        return await message.reply('Premium feature was disabled')
    
    try:
        _, user_id = message.text.split(' ')
    except:
        return await message.reply(
            '<b>Usage:</b> <code>/rm_prm user_id</code>\n\n'
            '<b>Example:</b> <code>/rm_prm 123456789</code>',
            parse_mode=enums.ParseMode.HTML
        )
    
    try:
        user = await bot.get_users(user_id)
    except Exception as e:
        return await message.reply(f'❌ Error: {e}')
    
    if user.id in ADMINS:
        return await message.reply('ℹ️ Cannot remove premium from ADMINS')
    
    if not await is_premium(user.id, bot):
        await message.reply(f"ℹ️ {user.mention} is not a premium user")
    else:
        mp = db.get_plan(user.id)
        old_plan = mp.get('plan', 'Unknown')
        
        mp['expire'] = ''
        mp['plan'] = ''
        mp['premium'] = False
        mp['reminded_24h'] = False
        mp['reminded_6h'] = False
        mp['reminded_1h'] = False
        db.update_plan(user.id, mp)
        
        await message.reply(
            f"✅ Premium removed from {user.mention}\n\n"
            f"Previous plan: {old_plan}",
            parse_mode=enums.ParseMode.HTML
        )
        
        try:
            await bot.send_message(
                user.id, 
                "❌ Your premium subscription has been removed by admin.\n\n"
                "Use /plan to purchase a new subscription."
            )
        except:
            pass
        
        # Log to admin channel
        try:
            await bot.send_message(
                LOG_CHANNEL,
                f"#PremiumRemoved\n\n"
                f"User: {user.mention}\n"
                f"User ID: {user.id}\n"
                f"Previous Plan: {old_plan}\n"
                f"Removed by: {message.from_user.mention}",
                parse_mode=enums.ParseMode.HTML
            )
        except:
            pass


@Client.on_message(filters.command('prm_list') & filters.user(ADMINS))
async def premium_list(bot: Client, message: Message):
    """Admin command to list all premium users"""
    if not IS_PREMIUM:
        return await message.reply('Premium feature was disabled')
    
    tx = await message.reply('🔍 Getting list of premium users...')
    pr = [i for i in db.get_premium_users() if i.get('status', {}).get('premium')]
    
    if not pr:
        return await tx.edit_text('📭 No premium users found in database.')
    
    t = '<b>💎 Premium Users List</b>\n\n'
    
    for idx, p in enumerate(pr, 1):
        try:
            u = await bot.get_users(p['id'])
            mp = p.get('status', {})
            expire = mp.get('expire', '')
            plan = mp.get('plan', 'Unknown')
            
            if expire:
                # ✅ Convert to datetime
                expire_dt = parse_expire_time(expire)
                if expire_dt:
                    time_left = expire_dt - datetime.now()
                    days_left = max(0, time_left.days)
                    t += f"{idx}. {u.mention} (<code>{p['id']}</code>)\n"
                    t += f"   Plan: {plan} | Days left: {days_left}\n\n"
                else:
                    t += f"{idx}. {u.mention} (<code>{p['id']}</code>)\n"
                    t += f"   Plan: {plan}\n\n"
            else:
                t += f"{idx}. {u.mention} (<code>{p['id']}</code>)\n"
                t += f"   Plan: {plan}\n\n"
        except:
            t += f"{idx}. User ID: <code>{p['id']}</code> (Not accessible)\n\n"
    
    t += f"<b>Total Premium Users: {len(pr)}</b>"
    await tx.edit_text(t, parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command('trial_on') & filters.user(ADMINS))
async def trial_on(bot: Client, message: Message):
    """Admin command to enable trial feature"""
    global TRIAL_ENABLED
    if not IS_PREMIUM:
        return await message.reply('Premium feature was disabled')
    
    TRIAL_ENABLED = True
    await message.reply(
        '✅ <b>Trial Feature Enabled!</b>\n\n'
        'Users can now activate 1 hour free trial using /plan command.',
        parse_mode=enums.ParseMode.HTML
    )


@Client.on_message(filters.command('trial_off') & filters.user(ADMINS))
async def trial_off(bot: Client, message: Message):
    """Admin command to disable trial feature"""
    global TRIAL_ENABLED
    if not IS_PREMIUM:
        return await message.reply('Premium feature was disabled')
    
    TRIAL_ENABLED = False
    await message.reply(
        '❌ <b>Trial Feature Disabled!</b>\n\n'
        'Users cannot activate trial anymore.',
        parse_mode=enums.ParseMode.HTML
    )


@Client.on_message(filters.command('trial_status') & filters.user(ADMINS))
async def trial_status(bot: Client, message: Message):
    """Admin command to check trial feature status"""
    if not IS_PREMIUM:
        return await message.reply('Premium feature was disabled')
    
    status = "✅ Enabled" if TRIAL_ENABLED else "❌ Disabled"
    await message.reply(
        f'<b>Trial Feature Status:</b> {status}',
        parse_mode=enums.ParseMode.HTML
    )


# ─────────────────────────────────────────────
# 🔘 CALLBACK HANDLERS
# ─────────────────────────────────────────────
@Client.on_callback_query(filters.regex(r'^activate_trial$'))
async def activate_trial_callback(client: Client, query: CallbackQuery):
    """Callback handler for trial activation"""
    global TRIAL_ENABLED
    
    if not TRIAL_ENABLED:
        return await query.answer(
            '❌ Trial feature is currently disabled by admin!', 
            show_alert=True
        )
    
    mp = db.get_plan(query.from_user.id)
    
    if mp.get('trial'):
        return await query.message.edit(
            '❌ You already used your free trial.\n\n'
            'Use /plan to purchase a premium subscription.'
        )
    
    ex = datetime.now() + timedelta(hours=1)
    mp['expire'] = ex
    mp['trial'] = True
    mp['plan'] = '1 hour trial'
    mp['premium'] = True
    mp['reminded_24h'] = False
    mp['reminded_6h'] = False
    mp['reminded_1h'] = False
    db.update_plan(query.from_user.id, mp)
    
    await query.message.edit(
        f"🎉 <b>Congratulations!</b>\n\n"
        f"Your 1 hour free trial has been activated!\n"
        f"⏰ Expires: {ex.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Enjoy premium features!",
        parse_mode=enums.ParseMode.HTML
    )
    
    # Log to admin channel
    try:
        await client.send_message(
            LOG_CHANNEL,
            f"#TrialActivated\n\n"
            f"User: {query.from_user.mention}\n"
            f"User ID: {query.from_user.id}\n"
            f"Expires: {ex.strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode=enums.ParseMode.HTML
        )
    except:
        pass


@Client.on_callback_query(filters.regex(r'^activate_plan$'))
async def activate_plan_callback(client: Client, query: CallbackQuery):
    """Callback handler for premium plan activation"""
    q = await query.message.edit(
        '💎 <b>Premium Plan Purchase</b>\n\n'
        'How many days do you need premium plan?\n'
        'Send number of days (e.g., 7, 30, 365)\n\n'
        '⏱ Timeout: 5 minutes',
        parse_mode=enums.ParseMode.HTML
    )
    
    try:
        msg = await client.listen(
            chat_id=query.message.chat.id, 
            user_id=query.from_user.id,
            timeout=300
        )
    except ListenerTimeout:
        await q.delete()
        return await query.message.reply('⏰ Timeout! Please try again using /plan')
    
    try:
        d = int(msg.text)
        if d <= 0:
            raise ValueError
    except:
        await q.delete()
        return await query.message.reply(
            '❌ Invalid number!\n\n'
            'Please send a valid number (e.g., 7 for 7 days)\n'
            'Use /plan to try again.'
        )
    
    transaction_note = f'{d} days premium plan for {query.from_user.id}'
    amount = d * PRE_DAY_AMOUNT
    upi_uri = f"upi://pay?pa={UPI_ID}&pn={UPI_NAME}&am={amount}&cu=INR&tn={transaction_note}"
    
    # Generate QR code
    qr = qrcode.make(upi_uri)
    p = f"upi_qr_{query.from_user.id}.png"
    qr.save(p)
    
    await q.delete()
    await query.message.reply_photo(
        p, 
        caption=f"💳 <b>Payment Details</b>\n\n"
                f"📦 Plan: {d} days premium\n"
                f"💰 Amount: ₹{amount}\n\n"
                f"📱 Scan this QR code in any UPI app and pay\n"
                f"📸 After payment, send screenshot here\n\n"
                f"⏱ Timeout: 10 minutes\n"
                f"💬 Support: {RECEIPT_SEND_USERNAME}",
        parse_mode=enums.ParseMode.HTML
    )
    
    os.remove(p)
    
    try:
        msg = await client.listen(
            chat_id=query.message.chat.id, 
            user_id=query.from_user.id, 
            timeout=600
        )
    except ListenerTimeout:
        await q.delete()
        return await query.message.reply(
            f'⏰ <b>Timeout!</b>\n\n'
            f'Please send your payment receipt to: {RECEIPT_SEND_USERNAME}',
            parse_mode=enums.ParseMode.HTML
        )
    
    if msg.photo:
        await q.delete()
        await query.message.reply(
            f'✅ <b>Receipt Received!</b>\n\n'
            f'Your payment receipt has been sent to admin for verification.\n'
            f'You will be notified once approved.\n\n'
            f'💬 Support: {RECEIPT_SEND_USERNAME}',
            parse_mode=enums.ParseMode.HTML
        )
        
        # Forward receipt to admin
        try:
            await client.send_photo(
                RECEIPT_SEND_USERNAME, 
                msg.photo.file_id, 
                caption=f"#PaymentReceipt\n\n"
                        f"From: {query.from_user.mention}\n"
                        f"User ID: <code>{query.from_user.id}</code>\n"
                        f"Plan: {d} days\n"
                        f"Amount: ₹{amount}\n\n"
                        f"Use: <code>/add_prm {query.from_user.id} {d}d</code>",
                parse_mode=enums.ParseMode.HTML
            )
        except:
            pass
    else:
        await q.delete()
        await query.message.reply(
            f"❌ <b>Invalid Receipt!</b>\n\n"
            f"Please send a valid photo of your payment receipt.\n"
            f"Contact: {RECEIPT_SEND_USERNAME}",
            parse_mode=enums.ParseMode.HTML
        )


# ─────────────────────────────────────────────
# 🔧 UTILITY FUNCTIONS
# ─────────────────────────────────────────────
def get_premium_button():
    """Get standard premium button"""
    return InlineKeyboardButton('💎 Buy Premium', url=f"https://t.me/{temp.U_NAME}?start=premium")


def premium_required(func):
    """Decorator to check if user has premium access"""
    async def wrapper(client: Client, message: Message):
        if not await is_premium(message.from_user.id, client):
            btn = [[get_premium_button()]]
            return await message.reply(
                '🔒 <b>Premium Feature</b>\n\n'
                'This feature is only available for premium users!\n\n'
                'Use /plan to activate premium subscription.',
                reply_markup=InlineKeyboardMarkup(btn),
                parse_mode=enums.ParseMode.HTML
            )
        return await func(client, message)
    return wrapper
