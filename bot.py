import os
import sqlite3
import uuid
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)


# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

DB_FILE = "bot.db"
START_POINTS = 100_000


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
        os.getenv("PORT", "10000")
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

    # Người dùng
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            points INTEGER NOT NULL DEFAULT 100000
        )
    """)

    # Giao dịch điểm ảo
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

    conn.commit()
    conn.close()


# =========================================================
# USER
# =========================================================

def get_user(
    user_id,
    username=""
):

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT points
        FROM users
        WHERE user_id = ?
        """,
        (user_id,)
    )

    row = cur.fetchone()

    if row is None:

        cur.execute(
            """
            INSERT INTO users
            (user_id, username, points)
            VALUES (?, ?, ?)
            """,
            (
                user_id,
                username,
                START_POINTS
            )
        )

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


def change_points(
    user_id,
    amount
):

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT points
        FROM users
        WHERE user_id = ?
        """,
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


# =========================================================
# TRANSACTIONS
# =========================================================

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
# START
# =========================================================

async def start(
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
🤖 BOT ĐIỂM ẢO

Xin chào {user.first_name}!

💰 Điểm hiện tại:
🪙 {points:,}

📌 LỆNH

/balance
→ Xem điểm

/deposit 10000
→ Tạo yêu cầu nạp điểm ảo

/withdraw 5000
→ Tạo yêu cầu rút điểm ảo

/history
→ Xem lịch sử giao dịch

🎲 /dice
→ Tung xúc xắc giải trí

ℹ️ /help
→ Xem hướng dẫn

⚠️ Điểm chỉ là điểm ảo trong bot.
"""
    )


# =========================================================
# HELP
# =========================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        """
📖 HƯỚNG DẪN BOT

💰 ĐIỂM

/balance
→ Xem số dư

/deposit 10000
→ Tạo yêu cầu nạp 10.000 điểm

/withdraw 5000
→ Tạo yêu cầu rút 5.000 điểm

/history
→ Xem 10 giao dịch gần nhất

🎲 XÚC XẮC

/dice
→ Bot tung 3 viên xúc xắc để giải trí

👑 ADMIN

/addpoints USER_ID 10000
→ Cộng điểm

/removepoints USER_ID 5000
→ Trừ điểm

/approve_deposit TX_ID
→ Duyệt nạp

/approve_withdraw TX_ID
→ Duyệt rút

/reject TX_ID
→ Từ chối giao dịch

⚠️ Hệ thống chỉ sử dụng điểm ảo.
"""
    )


# =========================================================
# BALANCE
# =========================================================

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


# =========================================================
# DICE
# =========================================================

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

    d2 = await update.message.reply_dice(
        emoji="🎲"
    )

    d3 = await update.message.reply_dice(
        emoji="🎲"
    )

    a = d1.dice.value
    b = d2.dice.value
    c = d3.dice.value

    total = a + b + c

    await update.message.reply_text(
        f"""
🎲 KẾT QUẢ

🎲 {a}
🎲 {b}
🎲 {c}

🔢 Tổng: {total}

ℹ️ Xúc xắc này chỉ để giải trí,
không sử dụng điểm.
"""
    )


# =========================================================
# DEPOSIT
# =========================================================

async def deposit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if len(context.args) != 1:

        await update.message.reply_text(
            "❌ Cú pháp:\n\n"
            "/deposit 10000"
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

    if amount <= 0:

        await update.message.reply_text(
            "❌ Số điểm phải lớn hơn 0."
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

🆔 Mã giao dịch:
{tx_id}

🪙 Số điểm:
{amount:,}

⏳ Trạng thái:
CHỜ DUYỆT
"""
    )

    if ADMIN_ID:

        try:

            await context.bot.send_message(
                ADMIN_ID,
                f"""
📥 YÊU CẦU NẠP ĐIỂM

👤 {user.first_name}
🆔 User ID: {user.id}

🪙 Số điểm: {amount:,}

🔖 Mã:
{tx_id}

Duyệt:
/approve_deposit {tx_id}

Từ chối:
/reject {tx_id}
"""
            )

        except Exception as e:

            print(
                "Không gửi được thông báo admin:",
                e
            )


# =========================================================
# WITHDRAW
# =========================================================

async def withdraw(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if len(context.args) != 1:

        await update.message.reply_text(
            "❌ Cú pháp:\n\n"
            "/withdraw 5000"
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
❌ KHÔNG ĐỦ ĐIỂM

💰 Số dư: {points:,}
📤 Muốn rút: {amount:,}
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
📤 YÊU CẦU RÚT ĐIỂM

🆔 Mã giao dịch:
{tx_id}

🪙 Số điểm:
{amount:,}

⏳ Trạng thái:
CHỜ DUYỆT
"""
    )

    if ADMIN_ID:

        try:

            await context.bot.send_message(
                ADMIN_ID,
                f"""
📤 YÊU CẦU RÚT ĐIỂM

👤 {user.first_name}
🆔 User ID: {user.id}

🪙 Số điểm: {amount:,}

🔖 Mã:
{tx_id}

Duyệt:
/approve_withdraw {tx_id}

Từ chối:
/reject {tx_id}
"""
            )

        except Exception as e:

            print(
                "Không gửi được thông báo admin:",
                e
            )


# =========================================================
# HISTORY
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

        tx_id = row[0]
        tx_type = row[1]
        amount = row[2]
        status = row[3]
        created = row[4]

        icon = (
            "📥"
            if tx_type == "DEPOSIT"
            else "📤"
        )

        text += (
            f"{icon} {tx_type}\n"
            f"🪙 {amount:,} điểm\n"
            f"🔖 {tx_id}\n"
            f"📌 {status}\n"
            f"🕐 {created}\n\n"
        )

    await update.message.reply_text(text)


# =========================================================
# ADMIN CHECK
# =========================================================

def is_admin(update):

    return (
        ADMIN_ID != 0
        and update.effective_user.id == ADMIN_ID
    )


# =========================================================
# APPROVE DEPOSIT
# =========================================================

async def approve_deposit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    if len(context.args) != 1:

        await update.message.reply_text(
            "/approve_deposit TX_ID"
        )

        return

    tx_id = context.args[0].upper()

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            user_id,
            amount,
            status
        FROM transactions
        WHERE tx_id = ?
        """,
        (tx_id,)
    )

    row = cur.fetchone()

    if not row:

        conn.close()

        await update.message.reply_text(
            "❌ Không tìm thấy giao dịch."
        )

        return

    user_id, amount, status = row

    if status != "PENDING":

        conn.close()

        await update.message.reply_text(
            f"❌ Giao dịch đã là {status}."
        )

        return

    cur.execute(
        """
        SELECT points
        FROM users
        WHERE user_id = ?
        """,
        (user_id,)
    )

    user_row = cur.fetchone()

    if user_row:

        new_balance = (
            user_row[0] + amount
        )

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

    else:

        new_balance = amount

        cur.execute(
            """
            INSERT INTO users
            (user_id, username, points)
            VALUES (?, '', ?)
            """,
            (
                user_id,
                amount
            )
        )

    cur.execute(
        """
        UPDATE transactions
        SET
            status = 'APPROVED',
            balance_after = ?
        WHERE tx_id = ?
        """,
        (
            new_balance,
            tx_id
        )
    )

    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"""
✅ ĐÃ DUYỆT NẠP

🔖 {tx_id}

🪙 +{amount:,} điểm

💰 Số dư mới:
{new_balance:,}
"""
    )


# =========================================================
# APPROVE WITHDRAW
# =========================================================

async def approve_withdraw(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    if len(context.args) != 1:

        await update.message.reply_text(
            "/approve_withdraw TX_ID"
        )

        return

    tx_id = context.args[0].upper()

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            user_id,
            amount,
            status
        FROM transactions
        WHERE tx_id = ?
        """,
        (tx_id,)
    )

    row = cur.fetchone()

    if not row:

        conn.close()

        await update.message.reply_text(
            "❌ Không tìm thấy giao dịch."
        )

        return

    user_id, amount, status = row

    if status != "PENDING":

        conn.close()

        await update.message.reply_text(
            f"❌ Giao dịch đã là {status}."
        )

        return

    cur.execute(
        """
        SELECT points
        FROM users
        WHERE user_id = ?
        """,
        (user_id,)
    )

    user_row = cur.fetchone()

    if not user_row:

        conn.close()

        await update.message.reply_text(
            "❌ Người dùng không tồn tại."
        )

        return

    current_points = user_row[0]

    if amount > current_points:

        conn.close()

        await update.message.reply_text(
            "❌ Người dùng không đủ điểm."
        )

        return

    new_balance = (
        current_points - amount
    )

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

    cur.execute(
        """
        UPDATE transactions
        SET
            status = 'APPROVED',
            balance_after = ?
        WHERE tx_id = ?
        """,
        (
            new_balance,
            tx_id
        )
    )

    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"""
✅ ĐÃ DUYỆT RÚT

🔖 {tx_id}

🪙 -{amount:,} điểm

💰 Số dư mới:
{new_balance:,}
"""
    )


# =========================================================
# REJECT
# =========================================================

async def reject(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    if len(context.args) != 1:

        await update.message.reply_text(
            "/reject TX_ID"
        )

        return

    tx_id = context.args[0].upper()

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE transactions
        SET status = 'REJECTED'
        WHERE tx_id = ?
        AND status = 'PENDING'
        """,
        (tx_id,)
    )

    changed = cur.rowcount

    conn.commit()
    conn.close()

    if changed:

        await update.message.reply_text(
            f"❌ Đã từ chối {tx_id}"
        )

    else:

        await update.message.reply_text(
            "❌ Không tìm thấy giao dịch đang chờ."
        )


# =========================================================
# ADMIN ADD POINTS
# =========================================================

async def add_points(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    if len(context.args) != 2:

        await update.message.reply_text(
            "/addpoints USER_ID SO_DIEM"
        )

        return

    try:

        user_id = int(
            context.args[0]
        )

        amount = int(
            context.args[1]
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Sai định dạng."
        )

        return

    if amount <= 0:

        await update.message.reply_text(
            "❌ Số điểm phải lớn hơn 0."
        )

        return

    new_balance = change_points(
        user_id,
        amount
    )

    await update.message.reply_text(
        f"""
✅ CỘNG ĐIỂM

👤 {user_id}

🪙 +{amount:,}

💰 Số dư:
{new_balance:,}
"""
    )


# =========================================================
# ADMIN REMOVE POINTS
# =========================================================

async def remove_points(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update):
        return

    if len(context.args) != 2:

        await update.message.reply_text(
            "/removepoints USER_ID SO_DIEM"
        )

        return

    try:

        user_id = int(
            context.args[0]
        )

        amount = int(
            context.args[1]
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Sai định dạng."
        )

        return

    if amount <= 0:

        await update.message.reply_text(
            "❌ Số điểm phải lớn hơn 0."
        )

        return

    new_balance = change_points(
        user_id,
        -amount
    )

    if new_balance is None:

        await update.message.reply_text(
            "❌ Người dùng không đủ điểm."
        )

        return

    await update.message.reply_text(
        f"""
✅ TRỪ ĐIỂM

👤 {user_id}

🪙 -{amount:,}

💰 Số dư:
{new_balance:,}
"""
    )


# =========================================================
# MAIN
# =========================================================

def main():

    if not TOKEN:

        raise RuntimeError(
            "❌ Chưa thiết lập BOT_TOKEN"
        )

    init_db()

    # Server cho Render
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

    # Người dùng
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    app.add_handler(
        CommandHandler(
            "balance",
            balance
        )
    )

    app.add_handler(
        CommandHandler(
            "deposit",
            deposit
        )
    )

    app.add_handler(
        CommandHandler(
            "withdraw",
            withdraw
        )
    )

    app.add_handler(
        CommandHandler(
            "history",
            history
        )
    )

    app.add_handler(
        CommandHandler(
            "dice",
            dice
        )
    )

    # Admin
    app.add_handler(
        CommandHandler(
            "approve_deposit",
            approve_deposit
        )
    )

    app.add_handler(
        CommandHandler(
            "approve_withdraw",
            approve_withdraw
        )
    )

    app.add_handler(
        CommandHandler(
            "reject",
            reject
        )
    )

    app.add_handler(
        CommandHandler(
            "addpoints",
            add_points
        )
    )

    app.add_handler(
        CommandHandler(
            "removepoints",
            remove_points
        )
    )

    print("🤖 BOT ĐANG CHẠY...")

    app.run_polling()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
