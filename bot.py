import os
import logging
import sqlite3
import asyncio
import aiohttp
import time
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = "8892555423:AAHcUvQgf2Y8byocmHuc9zgNLE-tD52nNL4"
ADMIN_ID = 1967494059
ADMIN_USERNAME = "RobiEntertainment"
SMS_API_URL = "https://api.paglahost.shop/Custom_SMS/api.php"
SMS_API_KEY = "Shuvo55356"

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "sender_bot.db")

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 10, total_sms INTEGER DEFAULT 0, join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status TEXT DEFAULT 'active')")
        c.execute("CREATE TABLE IF NOT EXISTS redeem_codes (code TEXT PRIMARY KEY, amount INTEGER, usages INTEGER, created_by INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS redeem_history (user_id INTEGER, code TEXT, redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (user_id, code))")
        c.execute("INSERT OR IGNORE INTO redeem_codes (code, amount, usages, created_by) VALUES ('FREE50',50,100,?)", (ADMIN_ID,))
        c.execute("INSERT OR IGNORE INTO redeem_codes (code, amount, usages, created_by) VALUES ('WELCOME10',10,200,?)", (ADMIN_ID,))
        conn.commit()
        conn.close()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"DB init error: {e}")

def get_balance(user_id):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else 0
    except:
        return 0

def update_balance(user_id, amount):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()
        return True
    except:
        return False

def get_profile(user_id):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT username, balance, total_sms, join_date, status FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        conn.close()
        return row
    except:
        return None

def redeem_code(user_id, code):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT 1 FROM redeem_history WHERE user_id=? AND code=?", (user_id, code))
        if c.fetchone():
            conn.close()
            return "already"
        c.execute("SELECT amount, usages FROM redeem_codes WHERE code=?", (code,))
        row = c.fetchone()
        if not row or row[1] <= 0:
            conn.close()
            return "invalid"
        amount = row[0]
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
        c.execute("UPDATE redeem_codes SET usages = usages - 1 WHERE code=?", (code,))
        c.execute("INSERT INTO redeem_history (user_id, code) VALUES (?,?)", (user_id, code))
        conn.commit()
        conn.close()
        return amount
    except:
        return "error"

def get_main_keyboard():
    return ReplyKeyboardMarkup([["📨 Send SMS"], ["👤 My Profile", "🎁 Redeem Code"], ["📊 My Stats", "📞 Contact Admin"]], resize_keyboard=True)

def get_admin_keyboard():
    return ReplyKeyboardMarkup([["💰 Add Credit", "➖ Remove Credit"], ["🚫 Ban User", "✅ Unban User"], ["📣 Broadcast", "🎟️ Create Code"], ["💰 Total Balance", "👥 Users List"], ["🔙 Back"]], resize_keyboard=True)

def get_back_keyboard():
    return ReplyKeyboardMarkup([["🔙 Back"]], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user = update.effective_user
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)", (user.id, user.username or user.first_name))
        conn.commit()
        conn.close()
        if user.id == ADMIN_ID:
            await update.message.reply_text(f"👑 Admin Panel\nWelcome {user.first_name}!", parse_mode="Markdown", reply_markup=get_admin_keyboard())
        else:
            await update.message.reply_text(f"🔥 Welcome {user.first_name}!\n💰 Balance: 10 Credits\n📡 SMS Sender Bot", parse_mode="Markdown", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"start error: {e}")
        await update.message.reply_text("❌ Error. Please try again.")

async def check_status(func):
    async def wrapper(update, context, *args, **kwargs):
        try:
            user_id = update.effective_user.id
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT status FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            conn.close()
            if row and row[0] == "banned":
                await update.message.reply_text("🚫 You are banned!", parse_mode="Markdown")
                return
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            logger.error(f"check_status error: {e}")
            await update.message.reply_text("❌ Error. Please try again.")
    return wrapper

@check_status
async def cmd_sms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        balance = get_balance(user_id)
        if balance < 1:
            await update.message.reply_text(f"❌ Insufficient credits! Contact @{ADMIN_USERNAME}", parse_mode="Markdown", reply_markup=get_main_keyboard())
            return
        await update.message.reply_text("📨 Send SMS\nEnter phone number (11 digits):", parse_mode="Markdown", reply_markup=get_back_keyboard())
        context.user_data['state'] = 'sms_number'
    except Exception as e:
        logger.error(f"cmd_sms error: {e}")
        await update.message.reply_text("❌ Error. Please try again.")

async def sms_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        number = update.message.text.strip()
        if not number.isdigit() or len(number) != 11:
            await update.message.reply_text("❌ Invalid! Enter 11 digits:", reply_markup=get_back_keyboard())
            return
        context.user_data['sms_number'] = number
        context.user_data['state'] = 'sms_message'
        await update.message.reply_text(f"✅ Number: `{number}`\nNow enter your message:", parse_mode="Markdown", reply_markup=get_back_keyboard())
    except Exception as e:
        logger.error(f"sms_number error: {e}")
        await update.message.reply_text("❌ Error. Please try again.")

async def sms_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        number = context.user_data.get('sms_number')
        msg = update.message.text
        if not number:
            await update.message.reply_text("❌ Error! Start again.", reply_markup=get_main_keyboard())
            context.user_data.clear()
            return
        await update.message.reply_text(f"⏳ Sending SMS to `{number}`...", parse_mode="Markdown")
        success = False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(SMS_API_URL, params={"key": SMS_API_KEY, "number": number, "msg": msg}, timeout=30) as resp:
                    text = await resp.text()
                    success = "success" in text.lower()
        except Exception as e:
            logger.error(f"SMS send error: {e}")
        if success:
            update_balance(user_id, -1)
            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE users SET total_sms = total_sms + 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            await update.message.reply_text(f"✅ SMS sent to `{number}`!", parse_mode="Markdown", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text("❌ Failed to send SMS! Please try again.", reply_markup=get_main_keyboard())
        context.user_data.clear()
    except Exception as e:
        logger.error(f"sms_message error: {e}")
        await update.message.reply_text("❌ Error sending SMS. Please try again.")

@check_status
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        row = get_profile(user_id)
        if row:
            await update.message.reply_text(f"👤 Profile\nID: {user_id}\nBalance: {row[1]}\nSMS Sent: {row[2]}\nStatus: {row[4]}", parse_mode="Markdown", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text("❌ Profile not found. Please /start again.", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"profile error: {e}")
        await update.message.reply_text("❌ Error loading profile. Please try again.")

@check_status
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        row = get_profile(user_id)
        if row:
            await update.message.reply_text(f"📊 My Stats\nBalance: {row[1]}\nSMS Sent: {row[2]}", parse_mode="Markdown", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text("❌ Stats not found.", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"stats error: {e}")
        await update.message.reply_text("❌ Error loading stats. Please try again.")

@check_status
async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("🎟 Enter redeem code:", parse_mode="Markdown", reply_markup=get_back_keyboard())
        context.user_data['state'] = 'redeem_code'
    except Exception as e:
        logger.error(f"redeem error: {e}")
        await update.message.reply_text("❌ Error. Please try again.")

async def redeem_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        code = update.message.text.strip().upper()
        result = redeem_code(user_id, code)
        if result == "already":
            await update.message.reply_text("❌ Already used!", reply_markup=get_main_keyboard())
        elif result == "invalid":
            await update.message.reply_text("❌ Invalid/expired!", reply_markup=get_main_keyboard())
        elif result == "error":
            await update.message.reply_text("❌ Error processing code. Please try again.", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text(f"🎉 +{result} credits!", reply_markup=get_main_keyboard())
        context.user_data.clear()
    except Exception as e:
        logger.error(f"redeem_process error: {e}")
        await update.message.reply_text("❌ Error. Please try again.")

async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(f"📞 Admin: @{ADMIN_USERNAME}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Message", url=f"https://t.me/{ADMIN_USERNAME}")]]))
    except Exception as e:
        logger.error(f"contact error: {e}")
        await update.message.reply_text("❌ Error. Please try again.")

# ===================== অ্যাডমিন হ্যান্ডলার =====================
async def admin_add_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("💰 Add Credit\nFormat: ID AMOUNT", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'add_credit'

async def admin_remove_credit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("➖ Remove Credit\nFormat: ID AMOUNT", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'remove_credit'

async def admin_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🚫 Ban User\nEnter user ID:", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'ban_user'

async def admin_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("✅ Unban User\nEnter user ID:", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'unban_user'

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("📣 Broadcast\nSend your message:", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'broadcast'

async def admin_create_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🎟️ Create Code\nFormat: CODE AMOUNT USAGES", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'create_code'

async def admin_total_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT SUM(balance), COUNT(*) FROM users")
    total, users = c.fetchone()
    conn.close()
    await update.message.reply_text(f"💰 Total Balance\nUsers: {users}\nTotal Credits: {total or 0}", parse_mode="Markdown", reply_markup=get_admin_keyboard())

async def admin_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id, username, balance, status FROM users ORDER BY user_id DESC LIMIT 20")
    users = c.fetchall()
    conn.close()
    if not users:
        await update.message.reply_text("No users", reply_markup=get_admin_keyboard())
        return
    text = "👥 Recent Users\n"
    for u in users:
        text += f"ID: {u[0]}  💰{u[2]}  {u[3]}\n"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

async def admin_state_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = update.message.text
    state = context.user_data.get('admin_state')
    conn = get_db()
    c = conn.cursor()
    if state == 'add_credit':
        try:
            target, amount = map(int, msg.split())
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target))
            conn.commit()
            try:
                await context.bot.send_message(target, f"🎉 +{amount} credits added!")
            except: pass
            await update.message.reply_text(f"✅ Added {amount} to {target}", reply_markup=get_admin_keyboard())
        except:
            await update.message.reply_text("❌ Invalid! Use: ID AMOUNT", parse_mode="Markdown")
        context.user_data['admin_state'] = None
    elif state == 'remove_credit':
        try:
            target, amount = map(int, msg.split())
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, target))
            conn.commit()
            try:
                await context.bot.send_message(target, f"⚠️ -{amount} credits removed!")
            except: pass
            await update.message.reply_text(f"✅ Removed {amount} from {target}", reply_markup=get_admin_keyboard())
        except:
            await update.message.reply_text("❌ Invalid! Use: ID AMOUNT", parse_mode="Markdown")
        context.user_data['admin_state'] = None
    elif state == 'ban_user':
        try:
            target = int(msg.strip())
            c.execute("UPDATE users SET status = 'banned' WHERE user_id = ?", (target,))
            conn.commit()
            try:
                await context.bot.send_message(target, "🚫 You are banned!")
            except: pass
            await update.message.reply_text(f"🚫 User {target} banned", reply_markup=get_admin_keyboard())
        except:
            await update.message.reply_text("❌ Invalid ID!")
        context.user_data['admin_state'] = None
    elif state == 'unban_user':
        try:
            target = int(msg.strip())
            c.execute("UPDATE users SET status = 'active' WHERE user_id = ?", (target,))
            conn.commit()
            try:
                await context.bot.send_message(target, "✅ You are unbanned!")
            except: pass
            await update.message.reply_text(f"✅ User {target} unbanned", reply_markup=get_admin_keyboard())
        except:
            await update.message.reply_text("❌ Invalid ID!")
        context.user_data['admin_state'] = None
    elif state == 'broadcast':
        c.execute("SELECT user_id FROM users WHERE status='active'")
        users = c.fetchall()
        await update.message.reply_text(f"⏳ Broadcasting to {len(users)} users...")
        success = 0
        for u in users:
            try:
                await context.bot.send_message(u[0], f"📢 Broadcast\n\n{msg}", parse_mode='Markdown')
                success += 1
                await asyncio.sleep(0.05)
            except: pass
        await update.message.reply_text(f"✅ Broadcast sent to {success} users!", reply_markup=get_admin_keyboard())
        context.user_data['admin_state'] = None
    elif state == 'create_code':
        try:
            parts = msg.split()
            code, amount, usages = parts[0].upper(), int(parts[1]), int(parts[2])
            c.execute("INSERT INTO redeem_codes (code, amount, usages, created_by) VALUES (?,?,?,?)", (code, amount, usages, user_id))
            conn.commit()
            await update.message.reply_text(f"✅ Code created!\n{code}\n{amount} credits\n{usages} uses", reply_markup=get_admin_keyboard())
        except:
            await update.message.reply_text("❌ Invalid! Use: CODE AMOUNT USAGES", parse_mode="Markdown")
        context.user_data['admin_state'] = None
    conn.close()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        msg = update.message.text
        logger.info(f"📩 {user_id}: {msg}")
        if user_id == ADMIN_ID:
            if msg == "💰 Add Credit": await admin_add_credit(update, context); return
            if msg == "➖ Remove Credit": await admin_remove_credit(update, context); return
            if msg == "🚫 Ban User": await admin_ban_user(update, context); return
            if msg == "✅ Unban User": await admin_unban_user(update, context); return
            if msg == "📣 Broadcast": await admin_broadcast(update, context); return
            if msg == "🎟️ Create Code": await admin_create_code(update, context); return
            if msg == "💰 Total Balance": await admin_total_balance(update, context); return
            if msg == "👥 Users List": await admin_users_list(update, context); return
            if msg == "🔙 Back":
                await update.message.reply_text("Main Menu", reply_markup=get_main_keyboard())
                context.user_data.clear(); return
            if context.user_data.get('admin_state'):
                await admin_state_handler(update, context); return
        if msg == "🔙 Back":
            await update.message.reply_text("Main Menu", reply_markup=get_main_keyboard())
            context.user_data.clear(); return
        if msg == "📨 Send SMS": await cmd_sms(update, context); return
        if msg == "👤 My Profile": await profile(update, context); return
        if msg == "🎁 Redeem Code": await redeem(update, context); return
        if msg == "📊 My Stats": await stats(update, context); return
        if msg == "📞 Contact Admin": await contact(update, context); return
        state = context.user_data.get('state')
        if state == 'sms_number': await sms_number(update, context); return
        elif state == 'sms_message': await sms_message(update, context); return
        elif state == 'redeem_code': await redeem_process(update, context); return
        await update.message.reply_text("❌ Use buttons!", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"handle_message error: {e}")
        await update.message.reply_text("❌ Something went wrong. Please try again.")

async def main():
    try:
        print("=" * 60)
        print("📨 SMS SENDER BOT (Python 3.13 Compatible)")
        print("=" * 60)
        init_db()
        app = Application.builder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        print("✅ Bot is RUNNING!")
        print("=" * 60)
        await app.run_polling()
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    try:
        import asyncio
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped!")
