import asyncio
import logging
import os

from telegram import Update, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# =========================
# CONFIG
# =========================

TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = -1003932050774

# =========================
# LOG
# =========================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

current_session = 84  # Khớp với phiên hiện tại của bạn
history = []
is_locked = False

users_data = {}
current_bets = {}
INITIAL_BALANCE = 0


# =========================
# KHÓA / MỞ NHÓM
# =========================

async def lock_chat(app):
    try:
        await app.bot.set_chat_permissions(
            chat_id=CHAT_ID,
            permissions=ChatPermissions(can_send_messages=False)
        )
    except Exception as e:
        logging.error(f"Lỗi khóa nhóm: {e}")

async def unlock_chat(app):
    try:
        await app.bot.set_chat_permissions(
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
    except Exception as e:
        logging.error(f"Lỗi mở nhóm: {e}")


# =========================
# GAME LOOP
# =========================

async def game_loop(app):
    global current_session, is_locked, current_bets

    while True:
        current_session += 1
        is_locked = False
        current_bets.clear()

        trend = (
            " ".join("🔴" if x == "TÀI" else "🟢" for x in history[-10:])
            if history
            else "Chưa có"
        )

        await app.bot.send_message(
            chat_id=CHAT_ID,
            text=(
                f"🎲 *PHIÊN #{current_session}*\n\n"
                f"📈 Lịch sử: {trend}\n"
                f"⏰ Chuẩn bị đặt cược trong 40 giây...\n\n"
                f"👉 Cú pháp đặt cược:\n"
                f"• `/tai [số_tiền]` hoặc `/xiu [số_tiền]`"
            ),
            parse_mode="Markdown"
        )

        await asyncio.sleep(40)

        is_locked = True
        await lock_chat(app)

        await app.bot.send_message(
            chat_id=CHAT_ID,
            text="🔒 Đã khóa sổ! Chuẩn bị tung xúc xắc..."
        )

        await asyncio.sleep(2)

        # Gửi 3 icon xúc xắc động lên nhóm
        dice_msg_1 = await app.bot.send_dice(chat_id=CHAT_ID, emoji="🎲")
        dice_msg_2 = await app.bot.send_dice(chat_id=CHAT_ID, emoji="🎲")
        dice_msg_3 = await app.bot.send_dice(chat_id=CHAT_ID, emoji="🎲")
        
        # BẮT BUỘC ĐỢI 4 GIÂY để animation Telegram chạy xong và cập nhật giá trị dice.value chuẩn xác
        await asyncio.sleep(4)

        # Lấy lại thông tin tin nhắn mới nhất chứa giá trị xúc xắc thật từ server Telegram
        d1 = dice_msg_1.dice.value
        d2 = dice_msg_2.dice.value
        d3 = dice_msg_3.dice.value

        total = d1 + d2 + d3
        result = "TÀI" if total >= 11 else "XỈU"
        result_icon = "🔴" if result == "TÀI" else "🟢"
        history.append(result)

        # Tính toán thắng thua cho người chơi
        result_details = []
        for user_id, bet in current_bets.items():
            choice = bet["choice"]
            amount = bet["amount"]
            name = bet["name"]

            if choice == result:
                win_amount = amount
                users_data[user_id]["balance"] += win_amount
                result_details.append(f"✅ {name} thắng +`{win_amount:,}` (Ví: `{users_data[user_id]['balance']:,}`)")
            else:
                users_data[user_id]["balance"] -= amount
                result_details.append(f"❌ {name} thua -`{amount:,}` (Ví: `{users_data[user_id]['balance']:,}`)")

        bet_summary_text = "\n".join(result_details) if result_details else "(Không có lượt cược nào phiên này)"
        trend_str = " ".join("🔴" if x == "TÀI" else "🟢" for x in history[-6:])

        # Gửi kết quả chuẩn khớp 100% với hình ảnh mẫu của bạn
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text=(
                f"📊 *KẾT QUẢ PHIÊN: #{current_session}*\n"
                f"----------------------------------------\n"
                f"🎲 Xúc xắc: `{d1} - {d2} - {d3}`\n"
                f"🔢 Tổng điểm: *{total}* ({result_icon} *{result}*)\n"
                f"📈 Dây cầu: {trend_str}\n"
                f"----------------------------------------\n"
                f"📝 *Biến động cược:*\n{bet_summary_text}"
            ),
            parse_mode="Markdown"
        )

        is_locked = False
        await unlock_chat(app)
        await asyncio.sleep(2)


# =========================
# MENU LỆNH
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    name = user.first_name

    if user_id not in users_data:
        users_data[user_id] = {"name": name, "balance": INITIAL_BALANCE}

    await update.message.reply_text(
        f"👋 Chào {name}!\n\n"
        f"💰 Số dư ví: `{users_data[user_id]['balance']:,}` điểm\n\n"
        f"📋 Menu lệnh:\n"
        f"• `/sd` - Kiểm tra số dư ví\n"
        f"• `/nap` - Hướng dẫn nạp điểm\n"
        f"• `/rut` - Yêu cầu rút điểm\n"
        f"• `/ls` - Xem lịch sử gần đây\n"
        f"• `/tai [số_tiền]` hoặc `/xiu [số_tiền]` - Đặt cược",
        parse_mode="Markdown"
    )

async def check_sd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data:
        users_data[user_id] = {"name": update.effective_user.first_name, "balance": INITIAL_BALANCE}
    
    balance = users_data[user_id]["balance"]
    await update.message.reply_text(f"💰 Số dư ví của bạn: `{balance:,}` điểm", parse_mode="Markdown")

async def menu_nap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💳 Vui lòng liên hệ trực tiếp Admin để nạp điểm.", parse_mode="Markdown")

async def menu_rut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💸 Vui lòng liên hệ Admin để thực hiện lệnh rút điểm.", parse_mode="Markdown")

async def menu_ls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not history:
        await update.message.reply_text("📈 Chưa có lịch sử kết quả phiên nào.")
        return
    trend = " ".join("🔴" if x == "TÀI" else "🟢" for x in history[-20:])
    await update.message.reply_text(f"📈 **Lịch sử các phiên gần nhất:**\n{trend}", parse_mode="Markdown")

async def admin_cong_tien(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ Cú pháp: `/cong [user_id] [số_tiền]`", parse_mode="Markdown")
        return
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ Sai định dạng!")
        return

    if target_id not in users_data:
        users_data[target_id] = {"name": f"User {target_id}", "balance": 0}

    users_data[target_id]["balance"] += amount
    await update.message.reply_text(f"👑 Đã cộng `{amount:,}` điểm cho user `{target_id}`.", parse_mode="Markdown")

async def place_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_locked, current_bets

    if is_locked:
        await update.message.reply_text("⏳ Đang quay thưởng, không thể cược!")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Vui lòng nhập số tiền cược! Ví dụ: `/tai 10000`", parse_mode="Markdown")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền cược không hợp lệ!")
        return

    if amount <= 0:
        await update.message.reply_text("⚠️ Số tiền cược phải lớn hơn 0!")
        return

    user = update.effective_user
    user_id = user.id
    name = user.first_name

    if user_id not in users_data:
        users_data[user_id] = {"name": name, "balance": INITIAL_BALANCE}

    if users_data[user_id]["balance"] < amount:
        await update.message.reply_text(f"❌ Số dư không đủ (`{users_data[user_id]['balance']:,}` điểm).", parse_mode="Markdown")
        return

    command = update.message.text.split()[0].lower()
    choice = "TÀI" if "tai" in command else "XỈU"

    current_bets[user_id] = {"choice": choice, "amount": amount, "name": name}
    await update.message.reply_text(f"✅ {name} đã cược **{amount:,}** điểm vào cửa **{choice}** thành công!", parse_mode="Markdown")

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Chat ID của bạn: {update.effective_user.id}\nGroup ID: {update.effective_chat.id}")


# =========================
# KHỞI ĐỘNG
# =========================

async def post_init(app):
    app.create_task(game_loop(app))

def main():
    if not TOKEN:
        raise RuntimeError("Chưa đặt BOT_TOKEN.")

    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sd", check_sd))
    app.add_handler(CommandHandler("nap", menu_nap))
    app.add_handler(CommandHandler("rut", menu_rut))
    app.add_handler(CommandHandler("ls", menu_ls))
    app.add_handler(CommandHandler("cong", admin_cong_tien))
    app.add_handler(CommandHandler("tai", place_bet))
    app.add_handler(CommandHandler("xiu", place_bet))
    app.add_handler(CommandHandler("id", get_id))

    print("🤖 Bot đang chạy với logic xúc xắc đồng bộ...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
