import os
import logging
import sqlite3
import asyncio
import aiohttp
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from dotenv import load_dotenv

load_dotenv()

# ===================== কনফিগারেশন =====================
BOT_TOKEN = "8892555423:AAHcUvQgf2Y8byocmHuc9zgNLE-tD52nNL4"
ADMIN_ID = 1967494059
ADMIN_USERNAME = "RobiEntertainment"
SMS_API_URL = "https://api.paglahost.shop/Custom_SMS/api.php"
SMS_API_KEY = "Shuvo55356"

# ===================== ডিরেক্টরি =====================
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "sender_bot.db")

# ===================== লগিং =====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== ডাটাবেস =====================
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
        logger.info("Sender Bot Database initialized")
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

# ===================== কীবোর্ড =====================
def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [["📨 Send SMS"], ["👤 My Profile", "🎁 Redeem Code"], ["📊 My Stats", "📞 Contact Admin"]],
        resize_keyboard=True
    )

def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        [["💰 Add Credit", "➖ Remove Credit"], ["🚫 Ban User", "✅ Unban User"], ["📣 Broadcast", "🎟️ Create Code"], ["💰 Total Balance", "👥 Users List"], ["🔙 Back"]],
        resize_keyboard=True
    )

def get_back_keyboard():
    return ReplyKeyboardMarkup([["🔙 Back"]], resize_keyboard=True)

# ===================== হ্যান্ডলার =====================
def start(update: Update, context: CallbackContext):
    try:
        user = update.effective_user
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)", (user.id, user.username or user.first_name))
        conn.commit()
        conn.close()
        if user.id == ADMIN_ID:
            update.message.reply_text(f"👑 Admin Panel\nWelcome {user.first_name}!", parse_mode="Markdown", reply_markup=get_admin_keyboard())
        else:
            update.message.reply_text(f"🔥 Welcome {user.first_name}!\n💰 Balance: 10 Credits\n📡 SMS Sender Bot", parse_mode="Markdown", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"start error: {e}")
        update.message.reply_text("❌ Error. Please try again.")

def check_status(func):
    def wrapper(update, context, *args, **kwargs):
        try:
            user_id = update.effective_user.id
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT status FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            conn.close()
            if row and row[0] == "banned":
                update.message.reply_text("🚫 You are banned!", parse_mode="Markdown")
                return
            return func(update, context, *args, **kwargs)
        except Exception as e:
            logger.error(f"check_status error: {e}")
            update.message.reply_text("❌ Error. Please try again.")
    return wrapper

@check_status
def cmd_sms(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        balance = get_balance(user_id)
        if balance < 1:
            update.message.reply_text(f"❌ Insufficient credits! Contact @{ADMIN_USERNAME}", parse_mode="Markdown", reply_markup=get_main_keyboard())
            return
        update.message.reply_text("📨 Send SMS\nEnter phone number (11 digits):", parse_mode="Markdown", reply_markup=get_back_keyboard())
        context.user_data['state'] = 'sms_number'
    except Exception as e:
        logger.error(f"cmd_sms error: {e}")
        update.message.reply_text("❌ Error. Please try again.")

def sms_number(update: Update, context: CallbackContext):
    try:
        number = update.message.text.strip()
        if not number.isdigit() or len(number) != 11:
            update.message.reply_text("❌ Invalid! Enter 11 digits:", reply_markup=get_back_keyboard())
            return
        context.user_data['sms_number'] = number
        context.user_data['state'] = 'sms_message'
        update.message.reply_text(f"✅ Number: `{number}`\nNow enter your message:", parse_mode="Markdown", reply_markup=get_back_keyboard())
    except Exception as e:
        logger.error(f"sms_number error: {e}")
        update.message.reply_text("❌ Error. Please try again.")

def sms_message(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        number = context.user_data.get('sms_number')
        msg = update.message.text
        if not number:
            update.message.reply_text("❌ Error! Start again.", reply_markup=get_main_keyboard())
            context.user_data.clear()
            return
        update.message.reply_text(f"⏳ Sending SMS to `{number}`...", parse_mode="Markdown")
        success = False
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            async def send():
                async with aiohttp.ClientSession() as session:
                    async with session.get(SMS_API_URL, params={"key": SMS_API_KEY, "number": number, "msg": msg}, timeout=30) as resp:
                        text = await resp.text()
                        return "success" in text.lower()
            success = loop.run_until_complete(send())
            loop.close()
        except Exception as e:
            logger.error(f"SMS send error: {e}")
        if success:
            update_balance(user_id, -1)
            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE users SET total_sms = total_sms + 1 WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            update.message.reply_text(f"✅ SMS sent to `{number}`!", parse_mode="Markdown", reply_markup=get_main_keyboard())
        else:
            update.message.reply_text("❌ Failed to send SMS! Please try again.", reply_markup=get_main_keyboard())
        context.user_data.clear()
    except Exception as e:
        logger.error(f"sms_message error: {e}")
        update.message.reply_text("❌ Error sending SMS. Please try again.")

@check_status
def profile(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        row = get_profile(user_id)
        if row:
            update.message.reply_text(f"👤 Profile\nID: {user_id}\nBalance: {row[1]}\nSMS Sent: {row[2]}\nStatus: {row[4]}", parse_mode="Markdown", reply_markup=get_main_keyboard())
        else:
            update.message.reply_text("❌ Profile not found. Please /start again.", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"profile error: {e}")
        update.message.reply_text("❌ Error loading profile. Please try again.")

@check_status
def stats(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        row = get_profile(user_id)
        if row:
            update.message.reply_text(f"📊 My Stats\nBalance: {row[1]}\nSMS Sent: {row[2]}", parse_mode="Markdown", reply_markup=get_main_keyboard())
        else:
            update.message.reply_text("❌ Stats not found.", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"stats error: {e}")
        update.message.reply_text("❌ Error loading stats. Please try again.")

@check_status
def redeem(update: Update, context: CallbackContext):
    try:
        update.message.reply_text("🎟 Enter redeem code:", parse_mode="Markdown", reply_markup=get_back_keyboard())
        context.user_data['state'] = 'redeem_code'
    except Exception as e:
        logger.error(f"redeem error: {e}")
        update.message.reply_text("❌ Error. Please try again.")

def redeem_process(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        code = update.message.text.strip().upper()
        result = redeem_code(user_id, code)
        if result == "already":
            update.message.reply_text("❌ Already used!", reply_markup=get_main_keyboard())
        elif result == "invalid":
            update.message.reply_text("❌ Invalid/expired!", reply_markup=get_main_keyboard())
        elif result == "error":
            update.message.reply_text("❌ Error processing code. Please try again.", reply_markup=get_main_keyboard())
        else:
            update.message.reply_text(f"🎉 +{result} credits!", reply_markup=get_main_keyboard())
        context.user_data.clear()
    except Exception as e:
        logger.error(f"redeem_process error: {e}")
        update.message.reply_text("❌ Error. Please try again.")

def contact(update: Update, context: CallbackContext):
    try:
        update.message.reply_text(f"📞 Admin: @{ADMIN_USERNAME}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Message", url=f"https://t.me/{ADMIN_USERNAME}")]]))
    except Exception as e:
        logger.error(f"contact error: {e}")
        update.message.reply_text("❌ Error. Please try again.")

# ===================== অ্যাডমিন হ্যান্ডলার =====================
def admin_add_credit(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    update.message.reply_text("💰 Add Credit\nFormat: ID AMOUNT", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'add_credit'

def admin_remove_credit(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    update.message.reply_text("➖ Remove Credit\nFormat: ID AMOUNT", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'remove_credit'

def admin_ban_user(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    update.message.reply_text("🚫 Ban User\nEnter user ID:", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'ban_user'

def admin_unban_user(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    update.message.reply_text("✅ Unban User\nEnter user ID:", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'unban_user'

def admin_broadcast(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    update.message.reply_text("📣 Broadcast\nSend your message:", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'broadcast'

def admin_create_code(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    update.message.reply_text("🎟️ Create Code\nFormat: CODE AMOUNT USAGES", parse_mode="Markdown", reply_markup=get_back_keyboard())
    context.user_data['admin_state'] = 'create_code'

def admin_total_balance(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT SUM(balance), COUNT(*) FROM users")
    total, users = c.fetchone()
    conn.close()
    update.message.reply_text(f"💰 Total Balance\nUsers: {users}\nTotal Credits: {total or 0}", parse_mode="Markdown", reply_markup=get_admin_keyboard())

def admin_users_list(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id, username, balance, status FROM users ORDER BY user_id DESC LIMIT 20")
    users = c.fetchall()
    conn.close()
    if not users:
        update.message.reply_text("No users", reply_markup=get_admin_keyboard())
        return
    text = "👥 Recent Users\n"
    for u in users:
        text += f"ID: {u[0]}  💰{u[2]}  {u[3]}\n"
    update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

def admin_state_handler(update: Update, context: CallbackContext):
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
                context.bot.send_message(target, f"🎉 +{amount} credits added!")
            except: pass
            update.message.reply_text(f"✅ Added {amount} to {target}", reply_markup=get_admin_keyboard())
        except:
            update.message.reply_text("❌ Invalid! Use: ID AMOUNT", parse_mode="Markdown")
        context.user_data['admin_state'] = None
    elif state == 'remove_credit':
        try:
            target, amount = map(int, msg.split())
            c.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, target))
            conn.commit()
            try:
                context.bot.send_message(target, f"⚠️ -{amount} credits removed!")
            except: pass
            update.message.reply_text(f"✅ Removed {amount} from {target}", reply_markup=get_admin_keyboard())
        except:
            update.message.reply_text("❌ Invalid! Use: ID AMOUNT", parse_mode="Markdown")
        context.user_data['admin_state'] = None
    elif state == 'ban_user':
        try:
            target = int(msg.strip())
            c.execute("UPDATE users SET status = 'banned' WHERE user_id = ?", (target,))
            conn.commit()
            try:
                context.bot.send_message(target, "🚫 You are banned!")
            except: pass
            update.message.reply_text(f"🚫 User {target} banned", reply_markup=get_admin_keyboard())
        except:
            update.message.reply_text("❌ Invalid ID!")
        context.user_data['admin_state'] = None
    elif state == 'unban_user':
        try:
            target = int(msg.strip())
            c.execute("UPDATE users SET status = 'active' WHERE user_id = ?", (target,))
            conn.commit()
            try:
                context.bot.send_message(target, "✅ You are unbanned!")
            except: pass
            update.message.reply_text(f"✅ User {target} unbanned", reply_markup=get_admin_keyboard())
        except:
            update.message.reply_text("❌ Invalid ID!")
        context.user_data['admin_state'] = None
    elif state == 'broadcast':
        c.execute("SELECT user_id FROM users WHERE status='active'")
        users = c.fetchall()
        update.message.reply_text(f"⏳ Broadcasting to {len(users)} users...")
        success = 0
        for u in users:
            try:
                context.bot.send_message(u[0], f"📢 Broadcast\n\n{msg}", parse_mode='Markdown')
                success += 1
                import time
                time.sleep(0.05)
            except: pass
        update.message.reply_text(f"✅ Broadcast sent to {success} users!", reply_markup=get_admin_keyboard())
        context.user_data['admin_state'] = None
    elif state == 'create_code':
        try:
            parts = msg.split()
            code, amount, usages = parts[0].upper(), int(parts[1]), int(parts[2])
            c.execute("INSERT INTO redeem_codes (code, amount, usages, created_by) VALUES (?,?,?,?)", (code, amount, usages, user_id))
            conn.commit()
            update.message.reply_text(f"✅ Code created!\n{code}\n{amount} credits\n{usages} uses", reply_markup=get_admin_keyboard())
        except:
            update.message.reply_text("❌ Invalid! Use: CODE AMOUNT USAGES", parse_mode="Markdown")
        context.user_data['admin_state'] = None
    conn.close()

# ===================== মেসেজ হ্যান্ডলার =====================
def handle_message(update: Update, context: CallbackContext):
    try:
        user_id = update.effective_user.id
        msg = update.message.text
        logger.info(f"📩 {user_id}: {msg}")
        if user_id == ADMIN_ID:
            if msg == "💰 Add Credit": admin_add_credit(update, context); return
            if msg == "➖ Remove Credit": admin_remove_credit(update, context); return
            if msg == "🚫 Ban User": admin_ban_user(update, context); return
            if msg == "✅ Unban User": admin_unban_user(update, context); return
            if msg == "📣 Broadcast": admin_broadcast(update, context); return
            if msg == "🎟️ Create Code": admin_create_code(update, context); return
            if msg == "💰 Total Balance": admin_total_balance(update, context); return
            if msg == "👥 Users List": admin_users_list(update, context); return
            if msg == "🔙 Back":
                update.message.reply_text("Main Menu", reply_markup=get_main_keyboard())
                context.user_data.clear(); return
            if context.user_data.get('admin_state'):
                admin_state_handler(update, context); return
        if msg == "🔙 Back":
            update.message.reply_text("Main Menu", reply_markup=get_main_keyboard())
            context.user_data.clear(); return
        if msg == "📨 Send SMS": cmd_sms(update, context); return
        if msg == "👤 My Profile": profile(update, context); return
        if msg == "🎁 Redeem Code": redeem(update, context); return
        if msg == "📊 My Stats": stats(update, context); return
        if msg == "📞 Contact Admin": contact(update, context); return
        state = context.user_data.get('state')
        if state == 'sms_number': sms_number(update, context); return
        elif state == 'sms_message': sms_message(update, context); return
        elif state == 'redeem_code': redeem_process(update, context); return
        update.message.reply_text("❌ Use buttons!", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"handle_message error: {e}")
        update.message.reply_text("❌ Something went wrong. Please try again.")

# ===================== মেইন =====================
def main():
    try:
        print("=" * 60)
        print("📨 SMS SENDER BOT (Standalone)")
        print("=" * 60)
        init_db()
        updater = Updater(BOT_TOKEN, use_context=True)
        dp = updater.dispatcher
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
        updater.start_polling()
        print("✅ Sender Bot is RUNNING!")
        print("=" * 60)
        updater.idle()
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
