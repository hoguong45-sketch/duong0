import os
import sqlite3
import uuid
import asyncio
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

DB_FILE = "bot.db"
START_POINTS = 0  # Số dư lúc đầu là 0
MULTIPLIER = 1.97

# Cấu hình giới hạn giao dịch và cược
MIN_BET = 1_000
MIN_DEPOSIT = 30_000


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
            referred_by INTEGER
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

    # Bảng lưu trữ Giftcode do Admin tạo
    cur.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            amount INTEGER,
            max_uses INTEGER,
            used_count INTEGER DEFAULT 0
        )
    """)

    # Bảng ghi nhận ai đã dùng code nào để tránh dùng 2 lần
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_codes (
            user_id INTEGER,
            code TEXT,
            PRIMARY KEY (user_id, code)
        )
    """)

    conn.commit()
    conn.close()


def get_user(user_id, username="", referrer_id=None):

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT points, referred_by FROM users WHERE user_id = ?",
        (user_id,)
    )

    row = cur.fetchone()

    if row is None:

        # Tránh tự giới thiệu chính mình
        ref = referrer_id if referrer_id != user_id else None

        cur.execute(
            """
            INSERT INTO users
            (user_id, username, points, referred_by)
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                username,
                START_POINTS,
                ref
            )
        )

        conn.commit()
        points = START_POINTS

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
# GAME
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

    await update.message.reply_text(
        f"""
🎯 {user.first_name}

Lựa chọn:
{"TÀI" if choice == "T" else "XỈU"}

🪙 Cược: {bet:,} điểm

🎲 Đang tung xúc xắc...
"""
    )

    await asyncio.sleep(0.5)

    dice1 = await update.message.reply_dice(
        emoji="🎲"
    )

    await asyncio.sleep(0.8)

    dice2 = await update.message.reply_dice(
        emoji="🎲"
    )

    await asyncio.sleep(0.8)

    dice3 = await update.message.reply_dice(
        emoji="🎲"
    )

    a = dice1.dice.value
    b = dice2.dice.value
    c = dice3.dice.value

    total = a + b + c

    triple = (
        a == b == c
    )

    if triple:

        result = "BỘ BA"
        win = False

    elif 4 <= total <= 10:

        result = "XỈU"
        win = choice == "X"

    else:

        result = "TÀI"
        win = choice == "T"

    if win:

        reward = int(
            bet * MULTIPLIER
        )

        new_balance = change_points(
            user.id,
            reward
        )

        await update.message.reply_text(
            f"""
🎉 THẮNG!

🎲 {a} + {b} + {c}
🔢 Tổng: {total}

📌 Kết quả: {result}
🎯 Bạn chọn:
{"TÀI" if choice == "T" else "XỈU"}

🪙 Cược: {bet:,}
🏆 Nhận: {reward:,} điểm

💰 Số dư:
{new_balance:,} điểm
"""
        )

    else:

        new_balance = get_user(
            user.id,
            user.username or ""
        )

        await update.message.reply_text(
            f"""
❌ KHÔNG TRÚNG

🎲 {a} + {b} + {c}
🔢 Tổng: {total}

📌 Kết quả: {result}
🎯 Bạn chọn:
{"TÀI" if choice == "T" else "XỈU"}

🪙 Mất: {bet:,} điểm

💰 Số dư:
{new_balance:,} điểm
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

    if choice not in ("T", "X"):
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

T 10000
X 10000
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
        referrer_id
    )

    # Tạo link giới thiệu riêng biệt cho từng user
    ref_link = f"https://t.me/{bot_username}?start={user.id}"

    await update.message.reply_text(
        f"""
🎲 BOT TÀI XỈU & ĐIỂM ẢO

Xin chào {user.first_name}!

💰 Số dư:
{points:,} điểm

🔗 **Link mời bạn bè của bạn:**
`{ref_link}`
(Mỗi người chơi bấm vào link này và tham gia sẽ được hệ thống phân biệt riêng cho bạn).

🎮 Cách chơi (Min cược: {MIN_BET:,} điểm):
T 10000 → Chọn TÀI
X 10000 → Chọn XỈU

📌 LỆNH:
/tk → Xem số dư
/nap 30000 → Nạp điểm
/rut [Số tiền] [Mã NH] [Số TK] [Tên TK] → Rút tiền
/code [Mã_Quà] → Nhập mã nhận thưởng từ Admin
/ls → Lịch sử giao dịch
/dice → Tung xúc xắc giải trí
/help → Xem hướng dẫn
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

🎯 TÀI XỈU (Min cược: {MIN_BET:,} điểm):
T 10000 → Chọn TÀI
X 10000 → Chọn XỈU
⚠️ Bộ ba giống nhau = Thua
🏆 Thắng: Cược × 1.97

💰 GIAO DỊCH & TIỆN ÍCH:
/tk → Xem số dư
/nap [Số điểm] (Tối thiểu {MIN_DEPOSIT:,}) → Nạp điểm
/rut [Số tiền] [Mã NH] [Số TK] [Tên TK] → Rút tiền
/code [Mã] → Nhập giftcode nhận thưởng
/ls → Lịch sử giao dịch
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

    await update.message.reply_text(
        f"""
💰 SỐ DƯ

🪙 {points:,} điểm
"""
    )


async def dice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🎲 Đang tung 3 xúc xắc..."
    )

    d1 = await update.message.reply_dice(
        emoji="🎲"
    )

    await asyncio.sleep(0.8)

    d2 = await update.message.reply_dice(
        emoji="🎲"
    )

    await asyncio.sleep(0.8)

    d3 = await update.message.reply_dice(
        emoji="🎲"
    )

    total = (
        d1.dice.value
        + d2.dice.value
        + d3.dice.value
    )

    await update.message.reply_text(
        f"""
🎲 KẾT QUẢ

{d1.dice.value}
+
{d2.dice.value}
+
{d3.dice.value}

🔢 Tổng: {total}
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

    # Kiểm tra mã có tồn tại không
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

    # Kiểm tra xem user này đã dùng mã này chưa
    cur.execute("SELECT * FROM user_codes WHERE user_id = ? AND code = ?", (user.id, code))
    if cur.fetchone():
        conn.close()
        await update.message.reply_text("❌ Bạn đã sử dụng mã quà tặng này rồi!")
        return

    # Đánh dấu user đã dùng và tăng số lượt dùng code
    cur.execute("INSERT INTO user_codes (user_id, code) VALUES (?, ?)", (user.id, code))
    cur.execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE code = ?", (code,))
    conn.commit()
    conn.close()

    # Cộng điểm cho người dùng
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

    await update.message.reply_text(
        f"""
📥 YÊU CẦU NẠP ĐIỂM

🪙 Số điểm: {amount:,} VNĐ
🆔 Mã giao dịch: `{tx_id}`

🏦 THÔNG TIN CHUYỂN KHOẢN:
• Ngân hàng: **MSB (Maritime Bank)**
• Số tài khoản: **6314072009**
• Chủ tài khoản: (Tên của bạn)
• Nội dung chuyển khoản (BẮT BUỘC): `{tx_id}`

⏳ Trạng thái: CHỜ THANH TOÁN
""",
        parse_mode="Markdown"
    )

    if ADMIN_ID:

        try:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Duyệt Nạp", callback_data=f"app_dep_{tx_id}"),
                    InlineKeyboardButton("❌ Từ chối", callback_data=f"rej_{tx_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                ADMIN_ID,
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

            print(
                "Lỗi gửi Admin:",
                e
            )


async def withdraw(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if len(context.args) < 4:

        await update.message.reply_text(
            """
❌ Cú pháp rút tiền ngân hàng:
/rut [số tiền] [mã ngân hàng] [số TK] [Tên TK không dấu]

💡 Ví dụ:
/rut 100000 VCB 0123456789 Tran Van B
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

    if amount <= 0:

        await update.message.reply_text(
            "❌ Số điểm phải lớn hơn 0."
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

    if ADMIN_ID:

        try:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Duyệt Rút", callback_data=f"app_wit_{tx_id}"),
                    InlineKeyboardButton("❌ Từ chối", callback_data=f"rej_{tx_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await context.bot.send_message(
                ADMIN_ID,
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

            print(
                "Lỗi gửi Admin:",
                e
            )


# =========================================================
# LỊCH SỬ
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
            "📜 Bạn chưa có giao dịch nào."
        )

        return

    text = "📜 LỊCH SỬ GIAO DỊCH\n\n"

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
# ADMIN COMMANDS (TẠO CODE, DUYỆT GIAO DỊCH)
# =========================================================

def is_admin(update):

    return (
        ADMIN_ID != 0
        and
        update.effective_user.id == ADMIN_ID
    )


# Lệnh Admin tạo mã quà tặng: /taocode [MÃ] [SỐ_ĐIỂM] [SỐ_LƯỢT_DÙNG(tùy chọn)]
async def create_promo_code(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if not is_admin(update):
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

    if update.effective_user.id != ADMIN_ID:
        await query.answer("❌ Bạn không có quyền thực hiện thao tác này!", show_alert=True)
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
        await query.edit_message_text(text=query.message.text + "\n\n⚠️️ [ĐÃ XỬ LÝ]")
        return

    user_id, amount, tx_type, status = row

    if action == "app_dep":
        new_balance = change_points(user_id, amount)
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

        await query.answer(f"✅ Đã duyệt nạp mã {tx_id}!", show_alert=True)
        await query.edit_message_text(
            text=f"{query.message.text}\n\n✅ **ĐÃ DUYỆT NẠP THÀNH CÔNG** (+{amount:,} điểm)",
            parse_mode="Markdown"
        )

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
        await query.edit_message_text(
            text=f"{query.message.text}\n\n✅ **ĐÃ DUYỆT RÚT THÀNH CÔNG** (-{amount:,} điểm)",
            parse_mode="Markdown"
        )

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
        await query.edit_message_text(
            text=f"{query.message.text}\n\n❌ **ĐÃ TỪ CHỐI GIAO DỊCH**",
            parse_mode="Markdown"
        )

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


async def approve_deposit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    if len(context.args) != 1:
        await update.message.reply_text("❌ Cú pháp:\n/approve_deposit TX_ID")
        return

    tx_id = context.args[0].upper()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, amount, status FROM transactions WHERE tx_id = ?", (tx_id,))
    row = cur.fetchone()

    if not row or row[2] != "PENDING":
        conn.close()
        await update.message.reply_text("❌ Giao dịch không hợp lệ hoặc đã xử lý.")
        return

    user_id, amount, status = row
    new_balance = change_points(user_id, amount)
    cur.execute("UPDATE transactions SET status = 'APPROVED', balance_after = ? WHERE tx_id = ?", (new_balance, tx_id))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ ĐÃ DUYỆT NẠP\n🔖 {tx_id}\n🪙 +{amount:,} điểm\n💰 Số dư: {new_balance:,}")


async def approve_withdraw(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    if len(context.args) != 1:
        await update.message.reply_text("❌ Cú pháp:\n/approve_withdraw TX_ID")
        return

    tx_id = context.args[0].upper()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, amount, status FROM transactions WHERE tx_id = ?", (tx_id,))
    row = cur.fetchone()

    if not row or row[2] != "PENDING":
        conn.close()
        await update.message.reply_text("❌ Giao dịch không hợp lệ hoặc đã xử lý.")
        return

    user_id, amount, status = row
    current_points = get_user(user_id)
    if amount > current_points:
        conn.close()
        await update.message.reply_text("❌ Người dùng không đủ điểm.")
        return

    new_balance = change_points(user_id, -amount)
    cur.execute("UPDATE transactions SET status = 'APPROVED', balance_after = ? WHERE tx_id = ?", (new_balance, tx_id))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ ĐÃ DUYỆT RÚT\n🔖 {tx_id}\n🪙 -{amount:,} điểm\n💰 Số dư: {new_balance:,}")


async def reject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    if len(context.args) != 1:
        await update.message.reply_text("❌ Cú pháp:\n/reject TX_ID")
        return

    tx_id = context.args[0].upper()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE transactions SET status = 'REJECTED' WHERE tx_id = ? AND status = 'PENDING'", (tx_id,))
    changed = cur.rowcount
    conn.commit()
    conn.close()

    if changed:
        await update.message.reply_text(f"❌ ĐÃ TỪ CHỐI\n🔖 {tx_id}")
    else:
        await update.message.reply_text("❌ Không tìm thấy giao dịch đang chờ.")


async def add_points(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    if len(context.args) != 2:
        await update.message.reply_text("❌ Cú pháp:\n/addpoints USER_ID SO_DIEM")
        return

    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ User ID hoặc số điểm không hợp lệ.")
        return

    new_balance = change_points(user_id, amount)
    await update.message.reply_text(f"✅ CỘNG ĐIỂM\n👤 User ID: {user_id}\n🪙 +{amount:,}\n💰 Số dư mới: {new_balance:,}")


async def remove_points(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    if len(context.args) != 2:
        await update.message.reply_text("❌ Cú pháp:\n/removepoints USER_ID SO_DIEM")
        return

    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ User ID hoặc số điểm không hợp lệ.")
        return

    new_balance = change_points(user_id, -amount)
    if new_balance is None:
        await update.message.reply_text("❌ Người dùng không đủ điểm.")
        return

    await update.message.reply_text(f"✅ TRỪ ĐIỂM\n👤 User ID: {user_id}\n🪙 -{amount:,}\n💰 Số dư mới: {new_balance:,}")


# =========================================================
# MAIN
# =========================================================

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
        .build()
    )

    app.add_handler(CallbackQueryHandler(handle_admin_callback))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("tk", balance))
    app.add_handler(CommandHandler("nap", deposit))
    app.add_handler(CommandHandler("rut", withdraw))
    app.add_handler(CommandHandler("code", use_code))
    app.add_handler(CommandHandler("ls", history))
    app.add_handler(CommandHandler("dice", dice))

    # Lệnh Admin
    app.add_handler(CommandHandler("taocode", create_promo_code))
    app.add_handler(CommandHandler("approve_deposit", approve_deposit))
    app.add_handler(CommandHandler("approve_withdraw", approve_withdraw))
    app.add_handler(CommandHandler("reject", reject))
    app.add_handler(CommandHandler("addpoints", add_points))
    app.add_handler(CommandHandler("removepoints", remove_points))

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
