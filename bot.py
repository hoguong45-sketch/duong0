import os
import sqlite3
import uuid
import random
import asyncio
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

cskh_env = os.getenv("CSKH_IDS", "")
CSKH_IDS = [int(x.strip()) for x in cskh_env.split(",") if x.strip().isdigit()]

DB_FILE = "bot.db"
START_POINTS = 0  
MULTIPLIER = 1.97

MIN_BET = 5_000         
MIN_DEPOSIT = 10_000    
MIN_WITHDRAW = 30_000   

NEWBIE_BONUS = 5_000
NEWBIE_WAGERING_ROUNDS = 10  
REF_BONUS = 1_000            

# Danh sách tài khoản ngân hàng nạp (Random liên tục ngẫu nhiên)
DEPOSIT_BANKS = [
    {
        "bank_name": "MSB (Maritime Bank)",
        "account_number": "6314072009",
        "account_holder": "Chính chủ"
    },
    {
        "bank_name": "MB (Military Bank)",
        "account_number": "0776876883",
        "account_holder": "Chính chủ"
    }
]

# Biến toàn cục quản lý trạng thái Phiên tự động
current_session_id = 1000
session_state = "CLOSED"  # "OPENED" (Đang nhận cược), "CLOSING" (Đang quay thưởng)
session_bets = {}         # Lưu cược phiên hiện tại: {user_id: {"choice": "T"/"X", "amount": 10000, "name": "..."}}
session_lock = asyncio.Lock()


# =========================================================
# RENDER WEB SERVER
# =========================================================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )
        self.end_headers()

        self.wfile.write(
            b"Telegram bot is running!"
        )

    def log_message(self, format, *args):
        return


def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"🌐 Render server running on port {port}")
    server.serve_forever()


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return sqlite3.connect(DB_FILE, timeout=10)


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            points INTEGER NOT NULL DEFAULT 0,
            referred_by INTEGER,
            wagering_required INTEGER NOT NULL DEFAULT 0,
            wagering_completed INTEGER NOT NULL DEFAULT 0,
            received_newbie BOOLEAN NOT NULL DEFAULT 0,
            ref_count INTEGER NOT NULL DEFAULT 0,
            total_deposited INTEGER NOT NULL DEFAULT 0,
            has_deposited_30k BOOLEAN NOT NULL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cskh_list (
            user_id INTEGER PRIMARY KEY
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_id TEXT UNIQUE,
            user_id INTEGER,
            type TEXT,
            amount INTEGER,
            status TEXT,
            balance_after INTEGER,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bet_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tx_id TEXT,
            game_type TEXT,
            choice TEXT,
            bet_amount INTEGER,
            result_dice TEXT,
            total_score INTEGER,
            status TEXT,
            reward_amount INTEGER,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS session_history (
            session_id INTEGER PRIMARY KEY,
            dice_result TEXT,
            total_score INTEGER,
            result_type TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            amount INTEGER,
            max_uses INTEGER,
            used_count INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_codes (
            user_id INTEGER,
            code TEXT,
            PRIMARY KEY (user_id, code)
        )
    """)

    conn.commit()
    conn.close()


def is_cskh(user_id):
    if user_id == ADMIN_ID or user_id in CSKH_IDS:
        return True
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM cskh_list WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row is not None


def get_user(user_id, username="", referrer_id=None, context=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT points, referred_by, wagering_required, wagering_completed, received_newbie, ref_count, total_deposited, has_deposited_30k FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = cur.fetchone()

    if row is None:
        ref = referrer_id if referrer_id != user_id else None
        initial_points = START_POINTS + NEWBIE_BONUS
        wagering_req = NEWBIE_BONUS * NEWBIE_WAGERING_ROUNDS

        cur.execute(
            """
            INSERT INTO users
            (user_id, username, points, referred_by, wagering_required, wagering_completed, received_newbie, ref_count, total_deposited, has_deposited_30k)
            VALUES (?, ?, ?, ?, ?, 0, 1, 0, 0, 0)
            """,
            (user_id, username, initial_points, ref, wagering_req)
        )

        if ref:
            cur.execute("SELECT user_id, ref_count FROM users WHERE user_id = ?", (ref,))
            ref_user = cur.fetchone()
            if ref_user:
                cur.execute("UPDATE users SET points = points + ?, ref_count = ref_count + 1 WHERE user_id = ?", (REF_BONUS, ref))
                if context:
                    try:
                        asyncio.create_task(
                            context.bot.send_message(
                                ref,
                                f"🎉 **CÓ BẠN MỚI THAM GIA!**\n\n👤 Thành viên: `{username or user_id}` đã tham gia qua link của bạn.\n🪙 Hệ thống cộng thưởng: **+{REF_BONUS:,} điểm** vào tài khoản!",
                                parse_mode="Markdown"
                            )
                        )
                    except Exception:
                        pass
        conn.commit()
        points = initial_points
    else:
        points = row[0]
        cur.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        conn.commit()

    conn.close()
    return points


def change_points(user_id, amount):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row is None:
        if amount < 0:
            conn.close()
            return None
        new_balance = amount
        cur.execute("INSERT INTO users (user_id, username, points) VALUES (?, '', ?)", (user_id, new_balance))
    else:
        new_balance = row[0] + amount
        if new_balance < 0:
            conn.close()
            return None
        cur.execute("UPDATE users SET points = ? WHERE user_id = ?", (new_balance, user_id))
    conn.commit()
    conn.close()
    return new_balance


def update_wagering(user_id, bet_amount):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET wagering_completed = wagering_completed + ? WHERE user_id = ?", (bet_amount, user_id))
    conn.commit()
    conn.close()


def check_wagering_status(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT wagering_required, wagering_completed, total_deposited, has_deposited_30k FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return False, 0, 0, 0, False
    req, comp, total_dep, has_30k = row
    return True, req, comp, total_dep, has_30k


def log_bet_history(user_id, tx_id, game_type, choice, bet_amount, result_dice, total_score, status, reward_amount):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO bet_history 
        (user_id, tx_id, game_type, choice, bet_amount, result_dice, total_score, status, reward_amount, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, tx_id, game_type, choice, bet_amount, result_dice, total_score, status, reward_amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()


def create_transaction(user_id, tx_type, amount):
    tx_id = uuid.uuid4().hex[:8].upper()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO transactions (tx_id, user_id, type, amount, status, balance_after, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (tx_id, user_id, tx_type, amount, "PENDING", 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()
    return tx_id


# =========================================================
# HỆ THỐNG PHIÊN TỰ ĐỘNG CHẠY LIÊN TỤC (BẮM START LÀ CHẠY LUÔN)
# =========================================================

async def get_recent_bridge_history():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT result_type, total_score FROM session_history ORDER BY session_id DESC LIMIT 10")
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        return "Chưa có dữ liệu"
    
    bridge_str = ""
    for r in reversed(rows):
        res_type, score = r
        if res_type == "TÀI":
            bridge_str += f"🔵({score}) "
        else:
            bridge_str += f"🔴({score}) "
    return bridge_str


async def auto_session_loop(application: Application):
    global current_session_id, session_state
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT MAX(session_id) FROM session_history")
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        current_session_id = row[0] + 1
    else:
        current_session_id = 1001

    while True:
        try:
            async with session_lock:
                session_state = "OPENED"
                session_bets.clear()

            print(f"--- BẮT ĐẦU PHIÊN #{current_session_id} (Đang mở cược 40s) ---")
            
            # Chờ 40 giây nhận cược
            await asyncio.sleep(40)

            # Thông báo đếm ngược 10 giây cuối
            async with session_lock:
                session_state = "CLOSING"

            print(f"--- ĐẾM NGƯỢC 10S CUỐI PHIÊN #{current_session_id} ---")
            await asyncio.sleep(10)

            # Quay thưởng và tổng kết
            a = random.randint(1, 6)
            b = random.randint(1, 6)
            c = random.randint(1, 6)
            total = a + b + c
            triple = (a == b == c)

            if triple:
                res_type = "XỈU" if total <= 10 else "TÀI"
            else:
                res_type = "TÀI" if total >= 11 else "XỈU"

            dice_str = f"{a} + {b} + {c}"

            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO session_history (session_id, dice_result, total_score, result_type, created_at) VALUES (?, ?, ?, ?, ?)",
                (current_session_id, dice_str, total, res_type, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            conn.close()

            async with session_lock:
                for uid, data in session_bets.items():
                    choice = data["choice"]
                    bet_amt = data["amount"]
                    
                    win = False
                    if not triple:
                        if choice == "T" and total >= 11: win = True
                        elif choice == "X" and total <= 10: win = True
                        elif choice == "C" and total % 2 == 0: win = True
                        elif choice == "L" and total % 2 != 0: win = True

                    tx_id = uuid.uuid4().hex[:6].upper()
                    if win:
                        reward = int(bet_amt * MULTIPLIER)
                        change_points(uid, reward)
                        log_bet_history(uid, tx_id, f"Phiên #{current_session_id}", choice, bet_amt, dice_str, total, "THẮNG", reward)
                    else:
                        log_bet_history(uid, tx_id, f"Phiên #{current_session_id}", choice, bet_amt, dice_str, total, "THUA", 0)

            print(f"Hoàn tất phiên #{current_session_id} | Kết quả: {dice_str} = {total} ({res_type})")
            current_session_id += 1

        except Exception as e:
            print(f"Lỗi trong vòng lặp phiên tự động: {e}")
            await asyncio.sleep(5)


# =========================================================
# ĐẶT CƯỢC TRONG PHIÊN TỰ ĐỘNG
# =========================================================

async def text_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    parts = text.split()

    if len(parts) != 2:
        return

    choice = parts[0].upper()
    if choice not in ("T", "X", "C", "L"):
        return

    try:
        bet = int(parts[1].replace(",", "").replace(".", ""))
    except ValueError:
        return

    user = update.effective_user
    points = get_user(user.id, user.username or "")

    if bet < MIN_BET:
        await update.message.reply_text(f"❌ Mức cược tối thiểu là {MIN_BET:,} điểm!")
        return

    if bet > points:
        await update.message.reply_text(f"❌ Không đủ điểm! Số dư hiện tại: {points:,} điểm")
        return

    global session_state
    async with session_lock:
        if session_state != "OPENED":
            await update.message.reply_text("⏳ Đang quay thưởng phiên hiện tại, vui lòng đợi phiên tiếp theo mở trong giây lát!")
            return

        change_points(user.id, -bet)
        update_wagering(user.id, bet)

        session_bets[user.id] = {
            "choice": choice,
            "amount": bet,
            "name": user.first_name
        }

    choice_name = {"T": "TÀI", "X": "XỈU", "C": "CHẴN", "L": "LẺ"}.get(choice, choice)
    await update.message.reply_text(
        f"✅ **ĐẶT CƯỢC THÀNH CÔNG!**\n\n"
        f"🔖 Phiên: `#{current_session_id}`\n"
        f"🎯 Lựa chọn: **{choice_name}**\n"
        f"🪙 Tiền cược: `{bet:,} điểm`\n"
        f"💰 Số dư còn lại: `{get_user(user.id):,} điểm`",
        parse_mode="Markdown"
    )


# =========================================================
# USER COMMANDS & REFERRAL SYSTEM
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username

    referrer_id = None
    if context.args:
        try:
            referrer_id = int(context.args[0])
        except ValueError:
            pass

    points = get_user(user.id, user.username or "", referrer_id, context)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT ref_count, wagering_required, wagering_completed, total_deposited, has_deposited_30k FROM users WHERE user_id = ?", (user.id,))
    row = cur.fetchone()
    conn.close()
    
    ref_count = row[0] if row else 0
    w_req = row[1] if row else 0
    w_comp = row[2] if row else 0
    total_dep = row[3] if row else 0
    has_30k = row[4] if row else 0

    ref_link = f"https://t.me/{bot_username}?start={user.id}"
    bridge_display = await get_recent_bridge_history()

    await update.message.reply_text(
        f"""
🎲 BOT TÀI XỈU PHIÊN CHẠY LIÊN TỤC

Xin chào {user.first_name}!
🎁 **Đã nhận quà Tân thủ:** +{NEWBIE_BONUS:,} điểm.

💰 Số dư: {points:,} điểm
👥 Bạn bè đã mời: {ref_count} người (Nhận +{REF_BONUS:,} điểm/bạn)
📈 Tiến độ vòng cược: {w_comp:,} / {w_req:,} điểm
📊 **Cầu Tài Xỉu gần nhất:**\n{bridge_display}

🔗 **Link mời bạn bè:**
`{ref_link}`

🎮 **Cách chơi tự động:**
Bot tự động chạy phiên liên tục 24/7 (50s/phiên). Cược trực tiếp qua chat:
• `T [Số điểm]` → Cược TÀI
• `X [Số điểm]` → Cược XỈU
• `C [Số điểm]` → Cược CHẴN
• `L [Số điểm]` → Cược LẺ

📌 LỆNH:
/tk → Xem số dư & thông tin tài khoản
/se → Lấy link giới thiệu
/nap 10000 → Nạp điểm (Hệ thống random STK ngẫu nhiên liên tục)
/rut [Số tiền] [Ngân hàng] [STK] [Tên] → Rút tiền
/code [Mã] → Nhập giftcode
/ls → Lịch sử nạp rút
/lichsucuoc → Lịch sử cược trò chơi
/help → Hướng dẫn
""",
        parse_mode="Markdown"
    )


async def get_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username
    ref_link = f"https://t.me/{bot_username}?start={user.id}"
    await update.message.reply_text(f"🔗 **LINK MỜI BẠN BÈ:**\n`{ref_link}`", parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"""
📖 HƯỚNG DẪN CHI TIẾT

🎯 **HỆ THỐNG PHIÊN TỰ ĐỘNG:**
• Phiên diễn ra liên tục 24/7 ngay khi bot khởi động (50s/phiên).
• Cú pháp cược: `T [tiền]`, `X [tiền]`, `C [tiền]`, `L [tiền]`.
• Thắng nhận hệ số ×1.97.

💰 **GIAO DỊCH:**
• /nap [số tiền] (Min nạp 10k, hệ thống tự động đổi ngẫu nhiên STK MSB hoặc MB)
• /rut [số tiền] [NH] [STK] [Tên] (Min rút 30k, yêu cầu nạp lần đầu 30k & cược x1)
• /tk xem số dư tài khoản.
"""
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    points = get_user(user.id, user.username or "")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT ref_count, wagering_required, wagering_completed, total_deposited, has_deposited_30k FROM users WHERE user_id = ?", (user.id,))
    row = cur.fetchone()
    conn.close()

    ref_count = row[0] if row else 0
    w_req = row[1] if row else 0
    w_comp = row[2] if row else 0
    total_dep = row[3] if row else 0
    has_30k = row[4] if row else 0

    await update.message.reply_text(
        f"""
💰 THÔNG TIN TÀI KHOẢN

🪙 Số dư: {points:,} điểm
👥 Bạn bè đã mời: {ref_count} người
📈 Vòng cược: {w_comp:,} / {w_req:,} điểm
📥 Tổng nạp: {total_dep:,}đ (Đã nạp 30k đầu: {"✅" if has_30k else "❌"})
"""
    )


async def bet_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT tx_id, game_type, bet_amount, result_dice, total_score, status, reward_amount, created_at FROM bet_history WHERE user_id = ? ORDER BY id DESC LIMIT 10",
        (user.id,)
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📜 Bạn chưa có lịch sử cược nào.")
        return

    text = "📜 **LỊCH SỬ CƯỢC GẦN NHẤT**\n\n"
    for r in rows:
        tx_id, g_type, bet_amt, dice_res, total, status, reward, time_str = r
        icon = "✅" if status == "THẮNG" else "❌"
        text += f"{icon} **{g_type}** ({status})\n🪙 Cược: {bet_amt:,}đ | Nhận: +{reward:,}đ\n🎲 Xúc xắc: {dice_res} = {total}\n🕐 {time_str}\n\n"

    await update.message.reply_text(text, parse_mode="Markdown")


# =========================================================
# NẠP & RÚT (RANDOM STK NGẪU NHIÊN LIÊN TỤC)
# =========================================================

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) != 1:
        await update.message.reply_text("❌ Cú pháp: /nap [số điểm]\nVí dụ: /nap 30000")
        return

    try:
        amount = int(context.args[0].replace(",", "").replace(".", ""))
    except ValueError:
        await update.message.reply_text("❌ Số điểm không hợp lệ.")
        return

    if amount < MIN_DEPOSIT:
        await update.message.reply_text(f"❌ Nạp tối thiểu {MIN_DEPOSIT:,} điểm!")
        return

    tx_id = create_transaction(user.id, "DEPOSIT", amount)

    # Lựa chọn ngẫu nhiên liên tục STK ngân hàng nạp
    selected_bank = random.choice(DEPOSIT_BANKS)

    await update.message.reply_text(
        f"""
📥 YÊU CẦU NẠP ĐIỂM

🪙 Số điểm: {amount:,} VNĐ
🆔 Mã giao dịch: `{tx_id}`

🏦 THÔNG TIN CHUYỂN KHOẢN (Random ngẫu nhiên):
• Ngân hàng: **{selected_bank['bank_name']}**
• Số tài khoản: `{selected_bank['account_number']}`
• Chủ tài khoản: {selected_bank['account_holder']}
• Nội dung chuyển khoản (BẮT BUỘC): `{tx_id}`

⏳ Trạng thái: CHỜ THANH TOÁN
""",
        parse_mode="Markdown"
    )

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM cskh_list")
    cskh_rows = cur.fetchall()
    conn.close()
    
    notify_targets = set(CSKH_IDS)
    if ADMIN_ID: notify_targets.add(ADMIN_ID)
    for r in cskh_rows: notify_targets.add(r[0])

    for target_id in notify_targets:
        try:
            keyboard = [[InlineKeyboardButton("✅ Duyệt Nạp", callback_data=f"app_dep_{tx_id}"), InlineKeyboardButton("❌ Từ chối", callback_data=f"rej_{tx_id}")]]
            await context.bot.send_message(target_id, f"📥 NẠP MỚI ({selected_bank['bank_name']})\n👤 {user.first_name} (ID: {user.id})\n🪙 {amount:,}\n🔖 `{tx_id}`", reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            pass


async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if len(context.args) < 4:
        await update.message.reply_text("❌ Cú pháp: /rut [số tiền] [mã NH] [số TK] [Tên TK]\nVí dụ: /rut 30000 MB 0365092606 Nguyen Van A")
        return

    try:
        amount = int(context.args[0].replace(",", "").replace(".", ""))
    except ValueError:
        await update.message.reply_text("❌ Số tiền không hợp lệ.")
        return

    bank_code = context.args[1].upper()
    bank_account = context.args[2]
    bank_owner = " ".join(context.args[3:])

    if amount < MIN_WITHDRAW:
        await update.message.reply_text(f"❌ Rút tối thiểu {MIN_WITHDRAW:,} điểm.")
        return

    ok, req, comp, total_dep, has_30k = check_wagering_status(user.id)
    if not has_30k:
        await update.message.reply_text("❌ Bạn cần nạp lần đầu tối thiểu 30,000đ mới được phép rút tiền.")
        return

    if comp < total_dep:
        await update.message.reply_text(f"❌ Bạn cần cược tối thiểu bằng tổng tiền nạp ({total_dep:,}đ) mới được rút.")
        return

    points = get_user(user.id)
    if amount > points:
        await update.message.reply_text(f"❌ Số dư không đủ! (Có: {points:,})")
        return

    tx_id = create_transaction(user.id, "WITHDRAW", amount)

    await update.message.reply_text(
        f"""
📤 YÊU CẦU RÚT TIỀN

🆔 Mã GD: `{tx_id}`
🪙 Số điểm rút: {amount:,}
🏦 NH: {bank_code} - STK: `{bank_account}` - Tên: **{bank_owner}**
⏳ Trạng thái: CHỜ DUYỆT
""",
        parse_mode="Markdown"
    )

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM cskh_list")
    cskh_rows = cur.fetchall()
    conn.close()
    
    notify_targets = set(CSKH_IDS)
    if ADMIN_ID: notify_targets.add(ADMIN_ID)
    for r in cskh_rows: notify_targets.add(r[0])

    for target_id in notify_targets:
        try:
            keyboard = [[InlineKeyboardButton("✅ Duyệt Rút", callback_data=f"app_wit_{tx_id}"), InlineKeyboardButton("❌ Từ chối", callback_data=f"rej_{tx_id}")]]
            await context.bot.send_message(target_id, f"📤 RÚT MỚI\n👤 {user.first_name} (ID: {user.id})\n🪙 {amount:,}\n🏦 {bank_code} - {bank_account}\n🔖 `{tx_id}`", reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception:
            pass


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT tx_id, type, amount, status, created_at FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT 10", (user.id,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📜 Bạn chưa có giao dịch nào.")
        return

    text = "📜 **LỊCH SỬ NẠP RÚT**\n\n"
    for row in rows:
        icon = "📥" if row[1] == "DEPOSIT" else "📤"
        type_name = "NẠP" if row[1] == "DEPOSIT" else "RÚT"
        text += f"{icon} {type_name} | {row[2]:,}đ\n🔖 `{row[0]}` | {row[3]}\n🕐 {row[4]}\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")


# =========================================================
# ADMIN & CSKH COMMANDS
# =========================================================

async def create_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Lệnh này chỉ dành cho Admin!")
        return

    if len(context.args) < 2:
        await update.message.reply_text("❌ Cú pháp: /taocode [MÃ] [SỐ_ĐIỂM] [LƯỢT]")
        return

    code = context.args[0].upper().strip()
    try:
        amount = int(context.args[1].replace(",", ""))
        max_uses = int(context.args[2]) if len(context.args) > 2 else 0
    except ValueError:
        await update.message.reply_text("❌ Lỗi tham số.")
        return

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO promo_codes (code, amount, max_uses, used_count) VALUES (?, ?, ?, 0)", (code, amount, max_uses))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Tạo mã `{code}` thành công (+{amount:,}đ)!", parse_mode="Markdown")
    except sqlite3.IntegrityError:
        conn.close()
        await update.message.reply_text("❌ Mã này đã tồn tại.")


async def use_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("❌ Cú pháp: /code [Mã]")
        return

    code = context.args[0].upper().strip()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT amount, max_uses, used_count FROM promo_codes WHERE code = ?", (code,))
    row = cur.fetchone()

    if not row:
        conn.close()
        await update.message.reply_text("❌ Mã không tồn tại.")
        return

    amount, max_uses, used_count = row
    if max_uses > 0 and used_count >= max_uses:
        conn.close()
        await update.message.reply_text("❌ Mã đã hết lượt sử dụng.")
        return

    cur.execute("SELECT * FROM user_codes WHERE user_id = ? AND code = ?", (user.id, code))
    if cur.fetchone():
        conn.close()
        await update.message.reply_text("❌ Bạn đã dùng mã này rồi.")
        return

    cur.execute("INSERT INTO user_codes (user_id, code) VALUES (?, ?)", (user.id, code))
    cur.execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE code = ?", (code,))
    conn.commit()
    conn.close()

    new_balance = change_points(user.id, amount)
    await update.message.reply_text(f"🎉 Nhận mã thành công +{amount:,}đ!\n💰 Số dư: {new_balance:,}đ")


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    if not is_cskh(update.effective_user.id):
        await query.answer("❌ Bạn không có quyền duyệt!", show_alert=True)
        return

    data = query.data
    parts = data.split("_")
    action = parts[0] + "_" + parts[1] if parts[0] == "app" else parts[0]
    tx_id = parts[-1]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, amount, type, status FROM transactions WHERE tx_id = ?", (tx_id,))
    row = cur.fetchone()

    if not row or row[3] != "PENDING":
        conn.close()
        await query.answer("❌ Giao dịch đã được xử lý hoặc không tồn tại!", show_alert=True)
        return

    user_id, amount, tx_type, status = row

    if action == "app_dep":
        new_balance = change_points(user_id, amount)
        cur.execute("SELECT total_deposited FROM users WHERE user_id = ?", (user_id,))
        u_row = cur.fetchone()
        new_total = (u_row[0] if u_row else 0) + amount

        cur.execute("UPDATE transactions SET status = 'APPROVED', balance_after = ? WHERE tx_id = ?", (new_balance, tx_id))
        cur.execute("UPDATE users SET total_deposited = ?, has_deposited_30k = CASE WHEN ? >= 30000 THEN 1 ELSE has_deposited_30k END WHERE user_id = ?", (new_total, new_total, user_id))
        conn.commit()
        conn.close()

        await query.answer("✅ Đã duyệt nạp!", show_alert=True)
        try:
            await query.edit_message_text(text=f"{query.message.text}\n\n✅ ĐÃ DUYỆT NẠP (+{amount:,}đ)")
            await context.bot.send_message(user_id, f"🎉 Nạp thành công +{amount:,}đ!\n💰 Số dư: {new_balance:,}đ")
        except Exception:
            pass

    elif action == "app_wit":
        cur_pts = get_user(user_id)
        if amount > cur_pts:
            conn.close()
            await query.answer("❌ User không đủ điểm trừ!", show_alert=True)
            return

        new_balance = change_points(user_id, -amount)
        cur.execute("UPDATE transactions SET status = 'APPROVED', balance_after = ? WHERE tx_id = ?", (new_balance, tx_id))
        conn.commit()
        conn.close()

        await query.answer("✅ Đã duyệt rút!", show_alert=True)
        try:
            await query.edit_message_text(text=f"{query.message.text}\n\n✅ ĐÃ DUYỆT RÚT (-{amount:,}đ)")
            await context.bot.send_message(user_id, f"✅ Yêu cầu rút {amount:,}đ đã được duyệt thành công!")
        except Exception:
            pass

    elif action == "rej":
        cur.execute("UPDATE transactions SET status = 'REJECTED' WHERE tx_id = ?", (tx_id,))
        conn.commit()
        conn.close()
        await query.answer("❌ Đã từ chối giao dịch!", show_alert=True)
        try:
            await query.edit_message_text(text=f"{query.message.text}\n\n❌ ĐÃ TỪ CHỐI")
            await context.bot.send_message(user_id, f"❌ Giao dịch mã `{tx_id}` đã bị từ chối.")
        except Exception:
            pass


# =========================================================
# MAIN (KHỞI ĐỘNG HỆ THỐNG VÀ CHẠY NGAY PHIÊN TỰ ĐỘNG)
# =========================================================

async def post_init(application: Application):
    commands = [
        ("start", "Khởi động bot và chạy phiên"),
        ("tk", "Xem số dư"),
        ("se", "Lấy link giới thiệu"),
        ("nap", "Nạp điểm (Random STK)"),
        ("rut", "Rút tiền ngân hàng"),
        ("code", "Nhập mã quà tặng"),
        ("lichsucuoc", "Lịch sử cược game"),
        ("ls", "Lịch sử nạp rút"),
        ("help", "Hướng dẫn")
    ]
    await application.bot.set_my_commands(commands)
    
    # Kích hoạt vòng lặp chạy phiên tự động chạy luôn ngay khi bot khởi động
    asyncio.create_task(auto_session_loop(application))


def main():
    if not TOKEN:
        raise RuntimeError("❌ Chưa thiết lập BOT_TOKEN")

    init_db()

    threading.Thread(target=run_web_server, daemon=True).start()

    app = Application.builder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CallbackQueryHandler(handle_admin_callback))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("se", get_referral_link))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("tk", balance))
    app.add_handler(CommandHandler("nap", deposit))
    app.add_handler(CommandHandler("rut", withdraw))
    app.add_handler(CommandHandler("code", use_code))
    app.add_handler(CommandHandler("ls", history))
    app.add_handler(CommandHandler("lichsucuoc", bet_history))
    app.add_handler(CommandHandler("taocode", create_promo_code))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_bet))

    print("🤖 BOT TÀI XỈU PHIÊN TỰ ĐỘNG ĐANG CHẠY...")
    app.run_polling()


if __name__ == "__main__":
    main()
