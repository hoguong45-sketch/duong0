import os
import sqlite3
import uuid
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

# Lấy danh sách ID CSKH từ biến môi trường (ví dụ: CSKH_IDS="123456789,987654321")
cskh_env = os.getenv("CSKH_IDS", "")
CSKH_IDS = [int(x.strip()) for x in cskh_env.split(",") if x.strip().isdigit()]

DB_FILE = "bot.db"
START_POINTS = 0  
MULTIPLIER = 1.97

# Cấu hình mức cược và giao dịch
MIN_BET = 5_000         
MIN_DEPOSIT = 10_000    # Min nạp 10k
MIN_WITHDRAW = 30_000   # Min rút 30k

# Cấu hình Tân thủ & Giới thiệu
NEWBIE_BONUS = 5_000
NEWBIE_WAGERING_ROUNDS = 10  # x10 vòng cược cho code tân thủ
REF_BONUS = 1_000            # Mời mỗi bạn bè được 1,000 điểm


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

    port = int(
        os.environ.get("PORT", 10000)
    )

    server = HTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    print(
        f"🌐 Render server running on port {port}"
    )

    server.serve_forever()


# =========================================================
# DATABASE
# =========================================================

def get_db():
    return sqlite3.connect(
        DB_FILE,
        timeout=10
    )


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

    # Bảng lưu danh sách CSKH được thêm động trong DB
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
    if user_id == ADMIN_ID:
        return True
    if user_id in CSKH_IDS:
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
            (
                user_id,
                username,
                initial_points,
                ref,
                wagering_req
            )
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
        cur.execute(
            """
            UPDATE users
            SET username = ?
            WHERE user_id = ?
            """,
            (
                username,
                user_id
            )
        )
        conn.commit()

    conn.close()
    return points


def change_points(user_id, amount):

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT points FROM users WHERE user_id = ?",
        (user_id,)
    )

    row = cur.fetchone()

    if row is None:

        if amount < 0:
            conn.close()
            return None

        new_balance = amount

        cur.execute(
            """
            INSERT INTO users
            (user_id, username, points)
            VALUES (?, '', ?)
            """,
            (
                user_id,
                new_balance
            )
        )

    else:

        new_balance = row[0] + amount

        if new_balance < 0:
            conn.close()
            return None

        cur.execute(
            """
            UPDATE users
            SET points = ?
            WHERE user_id = ?
            """,
            (
                new_balance,
                user_id
            )
        )

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
        (
            user_id,
            tx_id,
            game_type,
            choice,
            bet_amount,
            result_dice,
            total_score,
            status,
            reward_amount,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )
    conn.commit()
    conn.close()


def create_transaction(
    user_id,
    tx_type,
    amount
):

    tx_id = uuid.uuid4().hex[:8].upper()

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO transactions
        (
            tx_id,
            user_id,
            type,
            amount,
            status,
            balance_after,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tx_id,
            user_id,
            tx_type,
            amount,
            "PENDING",
            0,
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )
    )

    conn.commit()
    conn.close()

    return tx_id


# =========================================================
# GAME (TÀI XỈU & CHẴN LẺ)
# =========================================================

async def play_game(
    update: Update,
    choice,
    bet
):

    user = update.effective_user

    points = get_user(
        user.id,
        user.username or ""
    )

    if bet < MIN_BET:

        await update.message.reply_text(
            f"""
❌ Mức cược tối thiểu là {MIN_BET:,} điểm!
"""
        )

        return

    if bet > points:

        await update.message.reply_text(
            f"""
❌ Không đủ điểm! Vui lòng nạp thêm để chơi.

💰 Số dư: {points:,}
🎯 Bạn muốn chơi: {bet:,}
"""
        )

        return

    change_points(
        user.id,
        -bet
    )
    
    update_wagering(user.id, bet)

    tx_id = uuid.uuid4().hex[:6].upper()
    
    if choice == "T":
        choice_name = "TÀI"
        cửa_dat_display = "t2"
    elif choice == "X":
        choice_name = "XỈU"
        cửa_dat_display = "x1"
    elif choice == "C":
        choice_name = "CHẴN"
        cửa_dat_display = "c"
    else:  # 'L'
        choice_name = "LẺ"
        cửa_dat_display = "l"

    noi_dung_display = cửa_dat_display

    await update.message.reply_text(
        f"""
🎯 {user.first_name}

Lựa chọn: {choice_name}
🪙 Cược: {bet:,} điểm

🎲 Đang tung xúc xắc...
"""
    )

    await asyncio.sleep(0.5)

    dice1 = await update.message.reply_dice(emoji="🎲")
    await asyncio.sleep(0.8)
    dice2 = await update.message.reply_dice(emoji="🎲")
    await asyncio.sleep(0.8)
    dice3 = await update.message.reply_dice(emoji="🎲")

    a = dice1.dice.value
    b = dice2.dice.value
    c = dice3.dice.value

    total = a + b + c
    triple = (a == b == c)

    if choice in ("T", "X"):
        if triple:
            win = False
        elif 4 <= total <= 10:
            win = (choice == "X")
        else:
            win = (choice == "T")
    else:  # Chẵn / Lẻ
        win = (total % 2 == 0) if choice == "C" else (total % 2 != 0)
        if triple:
            win = False

    result_dice_str = f"{a} + {b} + {c}"

    if win:
        reward = int(bet * MULTIPLIER)
        new_balance = change_points(user.id, reward)
        status_text = "Thắng cuộc"
        reward_display = f"+{reward:,}đ"
        
        log_bet_history(user.id, tx_id, choice_name, cửa_dat_display, bet, result_dice_str, total, "THẮNG", reward)

        await update.message.reply_text(
            f"""
┌─────────────────────────
├─ Trò chơi: Xúc xắc ({choice_name})
├─ Kết quả: {result_dice_str} = {total}
├─ Cửa đặt : {cửa_dat_display}
├─ Mã giao dịch: {tx_id}
├─ Tiền cược: {bet:,}đ
├─ Nội dung: {noi_dung_display}
└─────────────────────────
├─ Kết quả: {status_text} - {reward_display}

Số dư: {new_balance:,}đ
"""
        )

    else:
        new_balance = get_user(user.id, user.username or "")
        status_text = "Thua cuộc"
        reward_display = "0đ"
        
        log_bet_history(user.id, tx_id, choice_name, cửa_dat_display, bet, result_dice_str, total, "THUA", 0)

        await update.message.reply_text(
            f"""
┌─────────────────────────
├─ Trò chơi: Xúc xắc ({choice_name})
├─ Kết quả: {result_dice_str} = {total}
├─ Cửa đặt : {cửa_dat_display}
├─ Mã giao dịch: {tx_id}
├─ Tiền cược: {bet:,}đ
├─ Nội dung: {noi_dung_display}
└─────────────────────────
├─ Kết quả: {status_text} - {reward_display}

Số dư: {new_balance:,}đ
"""
        )


async def text_bet(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if not update.message.text:
        return

    text = update.message.text.strip()
    parts = text.split()

    if len(parts) != 2:
        return

    choice = parts[0].upper()

    if choice not in ("T", "X", "C", "L"):
        return

    try:

        bet = int(
            parts[1]
            .replace(",", "")
            .replace(".", "")
        )

    except ValueError:

        await update.message.reply_text(
            """
❌ Số điểm không hợp lệ.

Ví dụ:
T 5000 (Tài)
X 5000 (Xỉu)
C 5000 (Chẵn)
L 5000 (Lẻ)
"""
        )

        return

    await play_game(
        update,
        choice,
        bet
    )


# =========================================================
# USER COMMANDS & REFERRAL SYSTEM
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username

    referrer_id = None
    if context.args:
        try:
            referrer_id = int(context.args[0])
        except ValueError:
            pass

    points = get_user(
        user.id,
        user.username or "",
        referrer_id,
        context
    )

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

    await update.message.reply_text(
        f"""
🎲 BOT TÀI XỈU & CHẴN LẺ

Xin chào {user.first_name}!
🎁 **Đã nhận quà Tân thủ:** +{NEWBIE_BONUS:,} điểm (Yêu cầu hoàn thành x{NEWBIE_WAGERING_ROUNDS} vòng cược tương đương {w_req:,} điểm).

💰 Số dư: {points:,} điểm
👥 Số bạn bè đã mời: {ref_count} người (Mỗi lượt mời thành công nhận +{REF_BONUS:,} điểm)
📈 Tiến độ vòng cược: {w_comp:,} / {w_req:,} điểm
📥 Đã nạp 30k lần đầu: {"✅ Đã nạp" if has_30k else "❌ Chưa nạp (Yêu cầu nạp 30k lần đầu & cược x1 để mở khóa rút)"}

🔗 **Link mời bạn bè của bạn:**
`{ref_link}`

🎮 Cách chơi (Min cược: {MIN_BET:,} điểm):
• T 5000 → Chọn TÀI
• X 5000 → Chọn XỈU
• C 5000 → Chọn CHẴN
• L 5000 → Chọn LẺ

📌 LỆNH:
/tk → Xem số dư & thông tin tài khoản
/se → Lấy link mời bạn bè
/nap 10000 → Nạp điểm (Min nạp: {MIN_DEPOSIT:,})
/rut [Số tiền] [Mã NH] [Số TK] [Tên TK] → Rút tiền (Min rút: {MIN_WITHDRAW:,})
/code [Mã_Quà] → Nhập mã nhận thưởng
/ls → Lịch sử nạp rút
/lichsucuoc → Xem lịch sử đặt cược game
/dice → Tung xúc xắc giải trí
/help → Xem hướng dẫn
""",
        parse_mode="Markdown"
    )


async def get_referral_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username
    ref_link = f"https://t.me/{bot_username}?start={user.id}"

    await update.message.reply_text(
        f"""
🔗 **LINK MỜI BẠN BÈ CỦA BẠN:**
`{ref_link}`

💡 *Mỗi người bạn tham gia qua link này và cược, bạn sẽ nhận được ngay **+{REF_BONUS:,} điểm**!*
""",
        parse_mode="Markdown"
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        f"""
📖 HƯỚNG DẪN

🎯 TRÒ CHƠI (Min cược: {MIN_BET:,} điểm):
• T 5000 → Chọn TÀI
• X 5000 → Chọn XỈU
• C 5000 → Chọn CHẴN
• L 5000 → Chọn LẺ
⚠️ Bộ ba giống nhau = Thua
🏆 Thắng: Cược × 1.97

💰 GIAO DỊCH & TIỆN ÍCH:
/tk → Xem số dư & tiến độ tài khoản
/se → Lấy link giới thiệu bạn bè
/nap [Số điểm] (Tối thiểu {MIN_DEPOSIT:,}) → Nạp điểm
/rut [Số tiền] [Mã NH] [Số TK] [Tên TK] (Min rút: {MIN_WITHDRAW:,}, yêu cầu nạp lần đầu 30k & cược x1) → Rút tiền
/code [Mã] → Nhập giftcode nhận thưởng
/ls → Lịch sử giao dịch nạp rút
/lichsucuoc → Lịch sử đặt cược trò chơi
🎲 /dice → Tung xúc xắc giải trí
"""
    )


async def balance(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    points = get_user(
        user.id,
        user.username or ""
    )

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
📈 Vòng cược đã hoàn thành: {w_comp:,} / {w_req:,} điểm
📥 Tổng tiền đã nạp: {total_dep:,}đ
✅ Nạp 30k lần đầu: {"Đã hoàn thành" if has_30k else "Chưa hoàn thành"}
"""
    )


async def bet_history(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT tx_id, game_type, bet_amount, result_dice, total_score, status, reward_amount, created_at
        FROM bet_history
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 10
        """,
        (user.id,)
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📜 Bạn chưa có lịch sử đặt cược trò chơi nào.")
        return

    text = "📜 **LỊCH SỬ ĐẶT CƯỢC (10 VÁN GẦN NHẤT)**\n\n"
    for r in rows:
        tx_id, g_type, bet_amt, dice_res, total, status, reward, time_str = r
        icon = "✅" if status == "THẮNG" else "❌"
        text += (
            f"{icon} **{g_type}** ({status})\n"
            f"🔖 Mã GD: `{tx_id}`\n"
            f"🪙 Cược: {bet_amt:,}đ | Nhận: +{reward:,}đ\n"
            f"🎲 Xúc xắc: {dice_res} = {total}\n"
            f"🕐 {time_str}\n\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")


async def dice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🎲 Đang tung 3 xúc xắc..."
    )

    d1 = await update.message.reply_dice(emoji="🎲")
    await asyncio.sleep(0.8)
    d2 = await update.message.reply_dice(emoji="🎲")
    await asyncio.sleep(0.8)
    d3 = await update.message.reply_dice(emoji="🎲")

    total = (
        d1.dice.value
        + d2.dice.value
        + d3.dice.value
    )

    await update.message.reply_text(
        f"""
🎲 KẾT QUẢ

{d1.dice.value} + {d2.dice.value} + {d3.dice.value}
🔢 Tổng: {total} ({"Chẵn" if total % 2 == 0 else "Lẻ"})
"""
    )


# =========================================================
# NHẬP CODE (CHO NGƯỜI DÙNG)
# =========================================================

async def use_code(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user

    if not context.args:
        await update.message.reply_text("❌ Cú pháp:\n/code [Mã_Giftcode]")
        return

    code = context.args[0].upper().strip()

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT amount, max_uses, used_count FROM promo_codes WHERE code = ?", (code,))
    row = cur.fetchone()

    if not row:
        conn.close()
        await update.message.reply_text("❌ Mã quà tặng không tồn tại hoặc đã hết hạn!")
        return

    amount, max_uses, used_count = row

    if max_uses > 0 and used_count >= max_uses:
        conn.close()
        await update.message.reply_text("❌ Mã quà tặng này đã hết lượt sử dụng!")
        return

    cur.execute("SELECT * FROM user_codes WHERE user_id = ? AND code = ?", (user.id, code))
    if cur.fetchone():
        conn.close()
        await update.message.reply_text("❌ Bạn đã sử dụng mã quà tặng này rồi!")
        return

    cur.execute("INSERT INTO user_codes (user_id, code) VALUES (?, ?)", (user.id, code))
    cur.execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE code = ?", (code,))
    conn.commit()
    conn.close()

    new_balance = change_points(user.id, amount)

    await update.message.reply_text(
        f"""
🎉 NHẬP MÃ QUÀ TẶNG THÀNH CÔNG!

🎁 Mã: `{code}`
🪙 Nhận được: +{amount:,} điểm
💰 Số dư hiện tại: {new_balance:,} điểm
""",
        parse_mode="Markdown"
    )


# =========================================================
# NẠP & RÚT
# =========================================================

async def deposit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if len(context.args) != 1:

        await update.message.reply_text(
            f"""
❌ Cú pháp:
/nap [số điểm cần nạp]
(Nạp tối thiểu: {MIN_DEPOSIT:,})

Ví dụ:
/nap 30000
"""
        )

        return

    try:

        amount = int(
            context.args[0]
            .replace(",", "")
            .replace(".", "")
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Số điểm không hợp lệ."
        )

        return

    if amount < MIN_DEPOSIT:

        await update.message.reply_text(
            f"""
❌ Số tiền nạp tối thiểu phải từ {MIN_DEPOSIT:,} điểm trở lên!
"""
        )

        return

    tx_id = create_transaction(
        user.id,
        "DEPOSIT",
        amount
    )

    # Đã cập nhật STK nạp sang MB Bank 0365092606 theo yêu cầu
    await update.message.reply_text(
        f"""
📥 YÊU CẦU NẠP ĐIỂM

🪙 Số điểm: {amount:,} VNĐ
🆔 Mã giao dịch: `{tx_id}`

🏦 THÔNG TIN CHUYỂN KHOẢN:
• Ngân hàng: **MB (Military Bank)**
• Số tài khoản: **0365092606**
• Chủ tài khoản: (Tên của bạn)
• Nội dung chuyển khoản (BẮT BUỘC): `{tx_id}`

⏳ Trạng thái: CHỜ THANH TOÁN
""",
        parse_mode="Markdown"
    )

    # Gửi thông báo đến toàn bộ Admin và CSKH
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM cskh_list")
    cskh_rows = cur.fetchall()
    conn.close()
    
    notify_targets = set(CSKH_IDS)
    if ADMIN_ID:
        notify_targets.add(ADMIN_ID)
    for r in cskh_rows:
        notify_targets.add(r[0])

    for target_id in notify_targets:
        try:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Duyệt Nạp", callback_data=f"app_dep_{tx_id}"),
                    InlineKeyboardButton("❌ Từ chối", callback_data=f"rej_{tx_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                target_id,
                f"""
📥 YÊU CẦU NẠP ĐIỂM MỚI

👤 {user.first_name}
🆔 User ID: {user.id}
🪙 Số điểm: {amount:,}
🔖 Mã giao dịch: {tx_id}
""",
                reply_markup=reply_markup
            )
        except Exception as e:
            print(f"Lỗi gửi thông báo cho CSKH/Admin {target_id}:", e)


async def withdraw(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if len(context.args) < 4:

        await update.message.reply_text(
            f"""
❌ Cú pháp rút tiền ngân hàng:
/rut [số tiền] [mã ngân hàng] [số TK] [Tên TK không dấu]
(Min rút: {MIN_WITHDRAW:,}, yêu cầu nạp lần đầu 30k & cược x1)

💡 Ví dụ:
/rut 30000 VCB 0123456789 Tran Van B
"""
        )

        return

    try:

        amount = int(
            context.args[0]
            .replace(",", "")
            .replace(".", "")
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Số điểm/số tiền rút không hợp lệ."
        )

        return

    bank_code = context.args[1].upper()
    bank_account = context.args[2]
    bank_owner = " ".join(context.args[3:])

    if amount < MIN_WITHDRAW:
        await update.message.reply_text(f"❌ Số tiền rút tối thiểu phải từ {MIN_WITHDRAW:,} điểm trở lên.")
        return

    ok, req, comp, total_dep, has_30k = check_wagering_status(user.id)
    
    if not has_30k:
        await update.message.reply_text(
            f"""
❌ Bạn chưa đủ điều kiện rút tiền!
⚠️ Yêu cầu: Bạn phải nạp lần đầu tối thiểu 30,000đ thì mới được phép rút tiền.
"""
        )
        return

    if comp < total_dep:
        await update.message.reply_text(
            f"""
❌ Bạn chưa hoàn thành đủ vòng cược (x1) để rút tiền!
📥 Tổng tiền đã nạp: {total_dep:,}đ
📈 Tổng cược đã thực hiện: {comp:,}đ
⚠️ Bạn cần phải cược tối thiểu bằng tổng số tiền đã nạp ({total_dep:,}đ) mới được rút.
"""
        )
        return

    points = get_user(
        user.id,
        user.username or ""
    )

    if amount > points:

        await update.message.reply_text(
            f"""
❌ Không đủ điểm để rút!

💰 Số dư hiện tại: {points:,}
📤 Số tiền muốn rút: {amount:,}
"""
        )

        return

    tx_id = create_transaction(
        user.id,
        "WITHDRAW",
        amount
    )

    await update.message.reply_text(
        f"""
📤 GHI NHẬN YÊU CẦU RÚT TIỀN

🆔 Mã giao dịch: `{tx_id}`
🪙 Số điểm rút: {amount:,}

🏦 THÔNG TIN NHẬN CỦA BẠN:
• Ngân hàng: **{bank_code}**
• Số TK: `{bank_account}`
• Chủ TK: **{bank_owner}**

⏳ Trạng thái: CHỜ DUYỆT
""",
        parse_mode="Markdown"
    )

    # Gửi thông báo đến toàn bộ Admin và CSKH
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM cskh_list")
    cskh_rows = cur.fetchall()
    conn.close()
    
    notify_targets = set(CSKH_IDS)
    if ADMIN_ID:
        notify_targets.add(ADMIN_ID)
    for r in cskh_rows:
        notify_targets.add(r[0])

    for target_id in notify_targets:
        try:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Duyệt Rút", callback_data=f"app_wit_{tx_id}"),
                    InlineKeyboardButton("❌ Từ chối", callback_data=f"rej_{tx_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                target_id,
                f"""
📤 YÊU CẦU RÚT TIỀN MỚI

👤 {user.first_name} (ID: {user.id})
🪙 Số điểm: {amount:,}
🏦 NH: {bank_code} - STK: {bank_account} - Tên: {bank_owner}
🔖 Mã giao dịch: {tx_id}
""",
                reply_markup=reply_markup
            )
        except Exception as e:
            print(f"Lỗi gửi thông báo cho CSKH/Admin {target_id}:", e)


# =========================================================
# LỊCH SỬ GIAO DỊCH NẠP RÚT
# =========================================================

async def history(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            tx_id,
            type,
            amount,
            status,
            created_at
        FROM transactions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 10
        """,
        (user.id,)
    )

    rows = cur.fetchall()
    conn.close()

    if not rows:

        await update.message.reply_text(
            "📜 Bạn chưa có giao dịch nạp rút nào."
        )

        return

    text = "📜 LỊCH SỬ GIAO DỊCH NẠP RÚT\n\n"

    for row in rows:

        icon = (
            "📥"
            if row[1] == "DEPOSIT"
            else "📤"
        )

        type_name = (
            "NẠP"
            if row[1] == "DEPOSIT"
            else "RÚT"
        )

        text += (
            f"{icon} {type_name}\n"
            f"🪙 {row[2]:,} điểm\n"
            f"🔖 {row[0]}\n"
            f"📌 {row[3]}\n"
            f"🕐 {row[4]}\n\n"
        )

    await update.message.reply_text(text)


# =========================================================
# ADMIN & CSKH COMMANDS
# =========================================================

def is_admin(update):
    return (
        ADMIN_ID != 0
        and
        update.effective_user.id == ADMIN_ID
    )


async def add_cskh(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not is_admin(update):
        await update.message.reply_text("❌ Bạn không có quyền sử dụng lệnh này!")
        return

    if not context.args:
        await update.message.reply_text("❌ Cú pháp:\n/addcskh [USER_ID]")
        return

    try:
        cskh_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID không hợp lệ.")
        return

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT OR IGNORE INTO cskh_list (user_id) VALUES (?)", (cskh_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Đã thêm User ID `{cskh_id}` vào danh sách CSKH thành công!", parse_mode="Markdown")
    except Exception as e:
        conn.close()
        await update.message.reply_text(f"❌ Lỗi: {e}")


async def remove_cskh(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not is_admin(update):
        await update.message.reply_text("❌ Bạn không có quyền sử dụng lệnh này!")
        return

    if not context.args:
        await update.message.reply_text("❌ Cú pháp:\n/removecskh [USER_ID]")
        return

    try:
        cskh_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ User ID không hợp lệ.")
        return

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM cskh_list WHERE user_id = ?", (cskh_id,))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Đã xóa User ID `{cskh_id}` khỏi danh sách CSKH.", parse_mode="Markdown")


async def create_promo_code(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not is_admin(update):
        await update.message.reply_text("❌ Bạn không có quyền sử dụng lệnh này (Chỉ Admin mới có quyền tạo code)!")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            """
❌ Cú pháp tạo mã cho Admin:
/taocode [MÃ_CODE] [SỐ_ĐIỂM] [SỐ_LƯỢT (mặc định 0 = không giới hạn)]

Ví dụ:
/taocode KM10K 10000 50
"""
        )
        return

    code = context.args[0].upper().strip()
    try:
        amount = int(context.args[1].replace(",", "").replace(".", ""))
        max_uses = int(context.args[2]) if len(context.args) > 2 else 0
    except ValueError:
        await update.message.reply_text("❌ Số điểm hoặc số lượt không hợp lệ.")
        return

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO promo_codes (code, amount, max_uses, used_count)
            VALUES (?, ?, ?, 0)
            """,
            (code, amount, max_uses)
        )
        conn.commit()
        conn.close()

        await update.message.reply_text(
            f"""
✅ TẠO MÃ QUÀ TẶNG THÀNH CÔNG!

🎁 Mã: `{code}`
🪙 Giá trị: +{amount:,} điểm
👥 Giới hạn lượt dùng: {"Không giới hạn" if max_uses == 0 else f"{max_uses} người"}
""",
            parse_mode="Markdown"
        )
    except sqlite3.IntegrityError:
        conn.close()
        await update.message.reply_text("❌ Mã quà tặng này đã tồn tại! Vui lòng chọn tên mã khác.")


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    user_id_callback = update.effective_user.id

    if not is_cskh(user_id_callback):
        await query.answer("❌ Bạn không có quyền thực hiện thao tác duyệt giao dịch này!", show_alert=True)
        return

    data = query.data
    parts = data.split("_")
    action = parts[0] + "_" + parts[1] if parts[0] == "app" else parts[0]
    tx_id = parts[-1]

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT user_id, amount, type, status
        FROM transactions
        WHERE tx_id = ?
        """,
        (tx_id,)
    )
    row = cur.fetchone()

    if not row or row[3] != "PENDING":
        conn.close()
        await query.answer("❌ Giao dịch không tồn tại hoặc đã được xử lý!", show_alert=True)
        try:
            await query.edit_message_text(text=query.message.text + "\n\n⚠ [ĐÃ XỬ LÝ]")
        except Exception:
            pass
        return

    user_id, amount, tx_type, status = row

    if action == "app_dep":
        new_balance = change_points(user_id, amount)
        
        cur.execute("SELECT total_deposited FROM users WHERE user_id = ?", (user_id,))
        u_row = cur.fetchone()
        current_total = u_row[0] if u_row else 0
        new_total = current_total + amount
        
        has_30k_update = 1 if new_total >= 30_000 else 0

        cur.execute(
            """
            UPDATE transactions
            SET status = 'APPROVED', balance_after = ?
            WHERE tx_id = ?
            """,
            (new_balance, tx_id)
        )
        cur.execute(
            """
            UPDATE users
            SET total_deposited = total_deposited + ?,
                has_deposited_30k = CASE WHEN (total_deposited + ?) >= 30000 THEN 1 ELSE has_deposited_30k END
            WHERE user_id = ?
            """,
            (amount, amount, user_id)
        )
        conn.commit()
        conn.close()

        await query.answer(f"✅ Đã duyệt nạp mã {tx_id}!", show_alert=True)
        try:
            await query.edit_message_text(
                text=f"{query.message.text}\n\n✅ **ĐÃ DUYỆT NẠP THÀNH CÔNG** (+{amount:,} điểm) bởi CSKH/Admin",
                parse_mode="Markdown"
            )
        except Exception:
            pass

        try:
            await context.bot.send_message(
                user_id,
                f"""
🎉 YÊU CẦU NẠP ĐIỂM ĐÃ ĐƯỢC DUYỆT!

🔖 Mã giao dịch: `{tx_id}`
🪙 Cộng tiền: +{amount:,} điểm
💰 Số dư hiện tại: {new_balance:,} điểm
""",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif action == "app_wit":
        current_points = get_user(user_id)
        if amount > current_points:
            conn.close()
            await query.answer("❌ Người dùng không đủ điểm để trừ!", show_alert=True)
            return

        new_balance = change_points(user_id, -amount)
        cur.execute(
            """
            UPDATE transactions
            SET status = 'APPROVED', balance_after = ?
            WHERE tx_id = ?
            """,
            (new_balance, tx_id)
        )
        conn.commit()
        conn.close()

        await query.answer(f"✅ Đã duyệt rút mã {tx_id}!", show_alert=True)
        try:
            await query.edit_message_text(
                text=f"{query.message.text}\n\n✅ **ĐÃ DUYỆT RÚT THÀNH CÔNG** (-{amount:,} điểm) bởi CSKH/Admin",
                parse_mode="Markdown"
            )
        except Exception:
            pass

        try:
            await context.bot.send_message(
                user_id,
                f"""
✅ YÊU CẦU RÚT TIỀN ĐÃ ĐƯỢC DUYỆT!

🔖 Mã giao dịch: `{tx_id}`
🪙 Trừ điểm: -{amount:,} điểm
💰 Số dư hiện tại: {new_balance:,} điểm
""",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif action == "rej":
        cur.execute(
            """
            UPDATE transactions
            SET status = 'REJECTED'
            WHERE tx_id = ? AND status = 'PENDING'
            """,
            (tx_id,)
        )
        conn.commit()
        conn.close()

        await query.answer(f"❌ Đã từ chối giao dịch {tx_id}!", show_alert=True)
        try:
            await query.edit_message_text(
                text=f"{query.message.text}\n\n❌ **ĐÃ TỪ CHỐI GIAO DỊCH** bởi CSKH/Admin",
                parse_mode="Markdown"
            )
        except Exception:
            pass

        try:
            await context.bot.send_message(
                user_id,
                f"""
❌ YÊU CẦU GIAO DỊCH ĐÃ BỊ TỪ CHỐI

🔖 Mã giao dịch: `{tx_id}`
""",
                parse_mode="Markdown"
            )
        except Exception:
            pass


# =========================================================
# MAIN
# =========================================================

async def post_init(application: Application):
    """Thiết lập menu lệnh (hiển thị khi gõ /)"""
    commands = [
        ("start", "Bắt đầu / Lấy link mời bạn bè"),
        ("tk", "Xem số dư tài khoản"),
        ("se", "Lấy link giới thiệu bạn bè"),
        ("nap", "Nạp điểm vào tài khoản"),
        ("rut", "Rút tiền về ngân hàng"),
        ("code", "Nhập mã quà tặng"),
        ("lichsucuoc", "Xem lịch sử cược trò chơi"),
        ("ls", "Xem lịch sử giao dịch nạp rút"),
        ("dice", "Tung xúc xắc giải trí"),
        ("help", "Xem hướng dẫn chi tiết")
    ]
    await application.bot.set_my_commands(commands)


def main():

    if not TOKEN:
        raise RuntimeError("❌ Chưa thiết lập BOT_TOKEN")

    init_db()

    threading.Thread(
        target=run_web_server,
        daemon=True
    ).start()

    app = (
        Application
        .builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

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
    app.add_handler(CommandHandler("dice", dice))

    # Lệnh quản lý cho Admin & CSKH
    app.add_handler(CommandHandler("taocode", create_promo_code))
    app.add_handler(CommandHandler("addcskh", add_cskh))
    app.add_handler(CommandHandler("removecskh", remove_cskh))

    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            text_bet
        )
    )

    print("🤖 BOT ĐANG CHẠY...")
    app.run_polling()


if __name__ == "__main__":
    main()
