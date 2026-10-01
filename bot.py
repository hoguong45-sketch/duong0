import os
import sqlite3
import random
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

TOKEN = os.getenv("BOT_TOKEN")

DB = "bot.db"

# =========================
# DATABASE
# =========================

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            points INTEGER DEFAULT 1000
        )
    """)

    conn.commit()
    conn.close()


def get_user(user_id, username=""):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute(
        "SELECT points FROM users WHERE user_id = ?",
        (user_id,)
    )

    row = cur.fetchone()

    if row is None:
        cur.execute(
            "INSERT INTO users (user_id, username, points) VALUES (?, ?, ?)",
            (user_id, username, 1000)
        )
        conn.commit()
        points = 1000
    else:
        points = row[0]

    conn.close()
    return points


def set_points(user_id, points):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET points = ? WHERE user_id = ?",
        (points, user_id)
    )

    conn.commit()
    conn.close()


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    points = get_user(
        user.id,
        user.username or ""
    )

    await update.message.reply_text(
        f"""🎲 CHÀO MỪNG {user.first_name}!

🎮 Bot xúc xắc điểm ảo

💰 Điểm hiện tại: {points:,}

Các lệnh:

/balance - Xem điểm
/roll - Tung 3 xúc xắc
/daily - Nhận điểm hằng ngày
/help - Xem hướng dẫn

⚠️ Điểm chỉ dùng trong bot, không có giá trị tiền thật."""
    )


# =========================
# BALANCE
# =========================

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    points = get_user(
        user.id,
        user.username or ""
    )

    await update.message.reply_text(
        f"💰 Số điểm của bạn: {points:,}"
    )


# =========================
# ROLL DICE
# =========================

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    points = get_user(
        user.id,
        user.username or ""
    )

    if points < 10:
        await update.message.reply_text(
            "❌ Bạn cần ít nhất 10 điểm để chơi."
        )
        return

    # Trừ 10 điểm để chơi
    points -= 10

    dice = [
        random.randint(1, 6),
        random.randint(1, 6),
        random.randint(1, 6)
    ]

    total = sum(dice)

    # Thưởng theo kết quả
    if dice[0] == dice[1] == dice[2]:
        reward = 100
        result = "🎉 TAM HOA!"

    elif total >= 14:
        reward = 30
        result = "🔥 KẾT QUẢ CAO!"

    elif total <= 5:
        reward = 5
        result = "📉 KẾT QUẢ THẤP"

    else:
        reward = 15
        result = "👍 KẾT QUẢ THƯỜNG"

    points += reward

    set_points(user.id, points)

    await update.message.reply_text(
        f"""🎲 KẾT QUẢ XÚC XẮC

🎲 {dice[0]}   🎲 {dice[1]}   🎲 {dice[2]}

🔢 Tổng: {total}

{result}

➕ Nhận: {reward} điểm
💰 Số dư: {points:,} điểm"""
    )


# =========================
# DAILY
# =========================

async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    points = get_user(
        user.id,
        user.username or ""
    )

    reward = 500
    points += reward

    set_points(user.id, points)

    await update.message.reply_text(
        f"""🎁 THƯỞNG HẰNG NGÀY

Bạn nhận được:
🪙 +{reward} điểm

💰 Số dư:
{points:,} điểm"""
    )


# =========================
# HELP
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        """📖 HƯỚNG DẪN

/start
→ Tạo tài khoản

/balance
→ Xem số điểm

/roll
→ Tung 3 xúc xắc

/daily
→ Nhận 500 điểm

/help
→ Xem hướng dẫn

🎲 Mỗi lần /roll sử dụng 10 điểm ảo.

⚠️ Đây chỉ là trò chơi điểm ảo, không hỗ trợ tiền thật."""
    )


# =========================
# MAIN
# =========================

def main():
    if not TOKEN:
        raise RuntimeError(
            "Chưa đặt biến môi trường BOT_TOKEN"
        )

    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("balance", balance)
    )

    app.add_handler(
        CommandHandler("roll", roll)
    )

    app.add_handler(
        CommandHandler("daily", daily)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    print("🤖 Bot đang chạy...")

    app.run_polling()


if __name__ == "__main__":
    main()
