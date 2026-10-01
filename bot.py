import os
import sqlite3
import asyncio

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")

DB_FILE = "bot.db"
START_POINTS = 100_000
MULTIPLIER = 1.97


# =========================
# DATABASE
# =========================

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            points INTEGER NOT NULL DEFAULT 100000
        )
    """)

    conn.commit()
    conn.close()


def get_user(user_id, username=""):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute(
        "SELECT points FROM users WHERE user_id = ?",
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
            (user_id, username, START_POINTS)
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
            (username, user_id)
        )

        conn.commit()

    conn.close()
    return points


def set_points(user_id, points):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE users
        SET points = ?
        WHERE user_id = ?
        """,
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
        f"""
🎲 BOT XÚC XẮC

Xin chào {user.first_name}!

💰 Số dư: {points:,} điểm

🎮 Cách chơi:

T 10000
→ Chọn TÀI 10.000 điểm

X 10000
→ Chọn XỈU 10.000 điểm

💰 /balance
→ Xem số dư

ℹ️ /help
→ Xem hướng dẫn

🎲 Bot sử dụng xúc xắc thật của Telegram.
🪙 Chỉ sử dụng điểm ảo.
"""
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
        f"💰 Số dư:\n\n🪙 {points:,} điểm"
    )


# =========================
# HELP
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        """
📖 HƯỚNG DẪN

🎯 Cú pháp:

T 10000
→ Chọn TÀI

X 10000
→ Chọn XỈU

Ví dụ:

T 5000
X 20000
T 100000

🎲 Kết quả:

4 → 10 = XỈU
11 → 17 = TÀI

🏆 Nếu dự đoán đúng:
Cược × 1,97 điểm

Ví dụ:
10.000 × 1,97 = 19.700 điểm

⚠️ Bộ ba giống nhau được tính là
kết quả đặc biệt.

🪙 Đây chỉ là điểm ảo,
không có nạp/rút tiền thật.
"""
    )


# =========================
# PLAY
# =========================

async def play_game(update: Update, choice, bet):

    user = update.effective_user

    points = get_user(
        user.id,
        user.username or ""
    )

    if bet <= 0:
        await update.message.reply_text(
            "❌ Số điểm phải lớn hơn 0."
        )
        return

    if bet > points:
        await update.message.reply_text(
            f"""
❌ Không đủ điểm!

💰 Số dư: {points:,}
🎯 Bạn muốn chơi: {bet:,}
"""
        )
        return

    # Trừ cược
    points -= bet
    set_points(user.id, points)

    await update.message.reply_text(
        f"""
🎯 {user.first_name}

Lựa chọn: {choice}
🪙 Cược: {bet:,} điểm

🎲 Đang tung xúc xắc...
"""
    )

    await asyncio.sleep(0.5)

    # Xúc xắc Telegram thật
    dice1 = await update.message.reply_dice(emoji="🎲")

    await asyncio.sleep(0.8)

    dice2 = await update.message.reply_dice(emoji="🎲")

    await asyncio.sleep(0.8)

    dice3 = await update.message.reply_dice(emoji="🎲")

    a = dice1.dice.value
    b = dice2.dice.value
    c = dice3.dice.value

    total = a + b + c

    # Bộ ba
    triple = (a == b == c)

    if triple:
        result = "BỘ BA"
        win = False

    elif 4 <= total <= 10:
        result = "XỈU"
        win = choice == "X"

    else:
        result = "TÀI"
        win = choice == "T"

    # =========================
    # THẮNG
    # =========================

    if win:

        reward = int(bet * MULTIPLIER)

        points += reward

        set_points(user.id, points)

        await update.message.reply_text(
            f"""
🎉 THẮNG!

🎲 {a} + {b} + {c}
🔢 Tổng: {total}

📌 Kết quả: {result}
🎯 Bạn chọn: {"TÀI" if choice == "T" else "XỈU"}

🪙 Cược: {bet:,}
🏆 Nhận: {reward:,} điểm

💰 Số dư:
{points:,} điểm
"""
        )

    # =========================
    # THUA
    # =========================

    else:

        await update.message.reply_text(
            f"""
❌ KHÔNG TRÚNG

🎲 {a} + {b} + {c}
🔢 Tổng: {total}

📌 Kết quả: {result}
🎯 Bạn chọn: {"TÀI" if choice == "T" else "XỈU"}

🪙 Mất: {bet:,} điểm

💰 Số dư:
{points:,} điểm
"""
        )


# =========================
# NHẬN T 10000 / X 10000
# =========================

async def text_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    parts = text.split()

    if len(parts) != 2:
        return

    choice = parts[0].upper()

    if choice not in ("T", "X"):
        return

    try:
        bet = int(parts[1].replace(",", "").replace(".", ""))
    except ValueError:
        await update.message.reply_text(
            "❌ Số điểm không hợp lệ.\n\n"
            "Ví dụ:\n"
            "T 10000\n"
            "X 10000"
        )
        return

    await play_game(
        update,
        choice,
        bet
    )


# =========================
# MAIN
# =========================

def main():

    if not TOKEN:
        raise RuntimeError(
            "Chưa thiết lập BOT_TOKEN"
        )

    init_db()

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("balance", balance)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    # Nhận:
    # T 10000
    # X 10000
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_bet
        )
    )

    print("🤖 BOT ĐANG CHẠY...")

    app.run_polling()


if __name__ == "__main__":
    main()
