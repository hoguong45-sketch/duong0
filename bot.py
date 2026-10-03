import asyncio
import random
import logging
import os
from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)
# =========================================================
# CONFIG
# =========================================================
TOKEN = os.getenv("BOT_TOKEN")
# Thay bằng Chat ID nhóm của bạn
CHAT_ID = int(os.getenv("CHAT_ID", "0"))
# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
# =========================================================
# GAME DATA
# =========================================================
current_session = 0
game_history = []
bets = {}
is_locked = False
# =========================================================
# KHÓA CHAT
# =========================================================
async def lock_chat(application):
    try:
        await application.bot.set_chat_permissions(
            chat_id=CHAT_ID,
            permissions=ChatPermissions(
                can_send_messages=False
            )
        )
        logging.info("Đã khóa chat.")
    except Exception as e:
        logging.error(f"Lỗi khóa chat: {e}")
# =========================================================
# MỞ CHAT
# =========================================================
async def unlock_chat(application):
    try:
        await application.bot.set_chat_permissions(
            chat_id=CHAT_ID,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True
            )
        )
        logging.info("Đã mở chat.")
    except Exception as e:
        logging.error(f"Lỗi mở chat: {e}")
# =========================================================
# GAME
# =========================================================
async def start_game(application):
    global current_session
    global game_history
    global bets
    global is_locked
    while True:
        # =========================
        # PHIÊN MỚI
        # =========================
        current_session += 1
        bets = {}
        is_locked = False
        if game_history:
            recent_trend = " ".join(
                "🔴" if x == "TÀI" else "🟢"
                for x in game_history[-5:]
            )
        else:
            recent_trend = "Chưa có"
        start_text = (
            f"🔔 *PHIÊN #{current_session} BẮT ĐẦU!*\n\n"
            f"📈 Dây cầu: {recent_trend}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏰ Thời gian đặt cược: *40 giây*\n\n"
            f"🔴 `/tai số`\n"
            f"🟢 `/xiu số`"
        )
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=start_text,
            parse_mode="Markdown"
        )
        # =========================
        # MỞ CƯỢC 40 GIÂY
        # =========================
        await asyncio.sleep(40)
        # =========================
        # KHÓA CƯỢC
        # =========================
        is_locked = True
        await lock_chat(application)
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=(
                "🔒 *ĐÃ KHÓA CƯỢC!*\n\n"
                "🎲 Chuẩn bị tung xúc xắc trong *10 giây*..."
            ),
            parse_mode="Markdown"
        )
        await asyncio.sleep(10)
        # =========================
        # TUNG XÚC XẮC
        # =========================
        d1 = random.randint(1, 6)
        d2 = random.randint(1, 6)
        d3 = random.randint(1, 6)
        total = d1 + d2 + d3
        result = "TÀI" if total >= 11 else "XỈU"
        game_history.append(result)
        # =========================
        # HIỆU ỨNG
        # =========================
        dice_msg = await application.bot.send_message(
            chat_id=CHAT_ID,
            text="🎲 Đang lắc xúc xắc..."
        )
        await asyncio.sleep(1)
        # =========================
        # DÂY CẦU
        # =========================
        trend = " ".join(
            "🔴" if x == "TÀI" else "🟢"
            for x in game_history[-10:]
        )
        result_icon = "🔴" if result == "TÀI" else "🟢"
        # =========================
        # KẾT QUẢ
        # =========================
        result_text = (
            f"📊 *KẾT QUẢ PHIÊN #{current_session}*\n\n"
            f"🎲 Xúc xắc: `{d1} - {d2} - {d3}`\n"
            f"🔢 Tổng điểm: *{total}*\n"
            f"🏆 Kết quả: {result_icon} *{result}*\n"
            f"📈 Dây cầu: {trend}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
        # =========================
        # HIỂN THỊ CƯỢC
        # =========================
        if bets:
            result_text += "📝 *CƯỢC PHIÊN NÀY:*\n"
            for data in bets.values():
                win = data["choice"].upper() == result
                status = "🟢 THẮNG" if win else "🔴 THUA"
                result_text += (
                    f"• @{data['name']} — "
                    f"{data['choice'].upper()} "
                    f"{data['amount']:,} → {status}\n"
                )
        else:
            result_text += "📝 Không có lượt cược nào."
        # =========================
        # HIỆN KẾT QUẢ
        # =========================
        await application.bot.edit_message_text(
            chat_id=CHAT_ID,
            message_id=dice_msg.message_id,
            text=result_text,
            parse_mode="Markdown"
        )
        # =========================
        # MỞ CHAT
        # =========================
        is_locked = False
        await unlock_chat(application)
        # =========================
        # NGHỈ 2 GIÂY
        # =========================
        await asyncio.sleep(2)
# =========================================================
# ĐẶT CƯỢC
# =========================================================
async def place_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_locked
    global bets
    if is_locked:
        await update.message.reply_text(
            "🔒 Đã khóa cược!\n"
            "Chờ phiên tiếp theo."
        )
        return
    if not update.message:
        return
    command = update.message.text.split()
    if len(command) < 2:
        await update.message.reply_text(
            "⚠️ Sai cú pháp!\n\n"
            "/tai 10000\n"
            "/xiu 10000"
        )
        return
    try:
        amount = int(command[1])
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "⚠️ Số tiền cược không hợp lệ!"
        )
        return
    user = update.effective_user
    name = user.username or user.first_name or str(user.id)
    if command[0].lower().startswith("/tai"):
        choice = "tai"
    else:
        choice = "xiu"
    bets[user.id] = {
        "name": name,
        "choice": choice,
        "amount": amount
    }
    await update.message.reply_text(
        f"✅ @{name}\n"
        f"Đã đặt *{amount:,}* vào *{choice.upper()}*!",
        parse_mode="Markdown"
    )
# =========================================================
# LẤY CHAT ID
# =========================================================
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 Chat ID:\n`{update.effective_chat.id}`",
        parse_mode="Markdown"
    )
# =========================================================
# START
# =========================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎲 *BOT TÀI XỈU*\n\n"
        "🔴 `/tai số`\n"
        "🟢 `/xiu số`\n\n"
        "Ví dụ:\n"
        "`/tai 10000`\n"
        "`/xiu 20000`",
        parse_mode="Markdown"
    )
# =========================================================
# KHỞI ĐỘNG GAME
# =========================================================
async def post_init(application):
    application.create_task(
        start_game(application)
    )
# =========================================================
# MAIN
# =========================================================
def main():
    if not TOKEN:
        raise RuntimeError(
            "Chưa cấu hình BOT_TOKEN trên Render!"
        )
    if CHAT_ID == 0:
        raise RuntimeError(
            "Chưa cấu hình CHAT_ID trên Render!"
        )
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )
    app.add_handler(
        CommandHandler("start", start_command)
    )
    app.add_handler(
        CommandHandler("tai", place_bet)
    )
    app.add_handler(
        CommandHandler("xiu", place_bet)
    )
    app.add_handler(
        CommandHandler("id", get_id)
    )
    print("🤖 Bot Tài Xỉu đang chạy...")
    app.run_polling(
        drop_pending_updates=True
    )
if __name__ == "__main__":
    main()

Trên Render bạn chỉ cần tạo 2 biến

BOT_TOKEN = token mới của bạn
CHAT_ID = -100xxxxxxxxxx

Không đặt token trực tiếp trong code.

Bot cần được cấp quyền quản trị nhóm, đặc biệt quyền hạn chế thành viên, thì chức năng khóa/mở chat mới hoạt động.

Nếu bạn muốn lấy CHAT_ID, thêm bot vào nhóm → gửi:

/id

Bot sẽ trả về ID nhóm.
