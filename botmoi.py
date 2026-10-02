import os
import random
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Nhập các hàm quản lý tiền từ file database.py chung
from database import init_db, get_user_balance, update_balance

BOT_TOKEN = os.getenv("BOT_TOKEN", "TOKEN_CỦA_BẠN")
MIN_BET = 1000

current_session = 1
is_betting_open = False
current_bets = {} 

# Danh sách lưu lịch sử các phiên gần nhất để vẽ dây cầu (lưu tối đa 10 phiên gần nhất)
history_cautai = []

async def dat_cuoc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_betting_open, current_bets
    if not is_betting_open:
        await update.message.reply_text("⏳ Chưa tới thời gian đặt cược! Vui lòng đợi phiên mới.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("⚠️ Cú pháp: `/tai <số_tiền>` hoặc `/xiu <số_tiền>`", parse_mode="Markdown")
        return

    command = update.message.text.split()[0].replace("/", "").lower()
    if command not in ["tai", "xiu"]:
        return

    try:
        amount = int(args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền cược không hợp lệ!")
        return

    if amount < MIN_BET:
        await update.message.reply_text(f"⚠️ Cược tối thiểu {MIN_BET:,} điểm!")
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # Lấy số dư từ database chung
    balance = get_user_balance(user_id, username)

    if balance < amount:
        await update.message.reply_text(f"❌ Số dư không đủ! Số dư hiện tại: `{balance:,}` điểm.", parse_mode="Markdown")
        return

    # Trừ tiền trực tiếp vào database chung
    update_balance(user_id, -amount)
    current_bets[user_id] = {"choice": command, "amount": amount, "name": username}

    new_balance = get_user_balance(user_id)
    await update.message.reply_text(
        f"✅ Đã cược `{amount:,}` điểm vào **{command.upper()}**.\n"
        f"💰 Số dư còn lại: `{new_balance:,}` điểm",
        parse_mode="Markdown"
    )

async def check_sodu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    balance = get_user_balance(user_id, username)
    await update.message.reply_text(f"💰 Số dư tài khoản của bạn: `{balance:,}` điểm", parse_mode="Markdown")

# --- VÒNG LẶP CHẠY LIÊN TỤC MỖI 35 GIÂY ---
async def game_loop(application):
    global current_session, is_betting_open, current_bets, history_cautai
    target_chat_id = os.getenv("CHAT_ID", "NHẬP_CHAT_ID_VÀO_ĐÂY")

    while True:
        # --- GIAI ĐOẠN 1: MỞ CƯỢC (25 giây) ---
        is_betting_open = True
        current_bets.clear()
        
        # Hiển thị dây cầu hiện tại khi mở phiên mới
        cau_string = " ".join(history_cautai) if history_cautai else "Chưa có lịch sử"

        if target_chat_id != "NHẬP_CHAT_ID_VÀO_ĐÂY":
            try:
                await application.bot.send_message(
                    chat_id=target_chat_id,
                    text=f"🔔 **PHIÊN #{current_session} BẮT ĐẦU!**\n"
                         f"📈 **Dây cầu gần đây:** {cau_string}\n"
                         f"----------------------------------\n"
                         f"⏰ Thời gian cược: **25 giây**\n"
                         f"👉 Cú pháp: `/tai <số>` hoặc `/xiu <số>`",
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Lỗi gửi tin nhắn mở phiên: {e}")

        await asyncio.sleep(25) # Chờ 25s nhận cược

        # --- GIAI ĐOẠN 2: ĐÓNG CƯỢC & QUAY THƯỞNG (10 giây) ---
        is_betting_open = False

        await asyncio.sleep(2) # Hiệu ứng chờ lắc
        
        # Tung 3 con xúc xắc ngẫu nhiên (1-6)
        d1, d2, d3 = random.randint(1, 6), random.randint(1, 6), random.randint(1, 6)
        total = d1 + d2 + d3

        if d1 == d2 == d3:
            winning_choice = "bao"
            result_icon = "🎲"
            result_name = "BÃO (Nhà cái ăn)"
            history_cautai.append("🟦") # Ký hiệu bão
        elif total >= 11:
            winning_choice = "tai"
            result_icon = "🔴"
            result_name = "TÀI"
            history_cautai.append("🔴")
        else:
            winning_choice = "xiu"
            result_icon = "🟢"
            result_name = "XỈU"
            history_cautai.append("🟢")

        # Giữ lịch sử cầu tối đa 10 phiên gần nhất cho gọn khung chat
        if len(history_cautai) > 10:
            history_cautai.pop(0)

        # Xử lý trả thưởng cộng tiền vào database chung
        payout_summary = ""
        for uid, data in current_bets.items():
            choice = data["choice"]
            amount = data["amount"]
            name = data["name"]
            
            if winning_choice == "bao":
                payout_summary += f"👤 {name}: Thua `{amount:,}` điểm (Bão)\n"
            elif choice == winning_choice:
                win_amount = amount * 2 # Thưởng gấp đôi
                update_balance(uid, win_amount)
                payout_summary += f"👤 {name}: Thắng `+{win_amount:,}` điểm 🎉\n"
            else:
                payout_summary += f"👤 {name}: Thua `-{amount:,}` điểm ❌\n"

        current_cau_hien_tai = " ".join(history_cautai)
        
        result_msg = (
            f"📊 **KẾT QUẢ PHIÊN: #{current_session}**\n"
            f"----------------------------------\n"
            f"🎲 Xúc xắc: ` {d1} ` - ` {d2} ` - ` {d3} `\n"
            f"🔢 Tổng điểm: **{total}** ({result_icon} {result_name})\n"
            f"📈 **Dây cầu:** {current_cau_hien_tai}\n"
            f"----------------------------------\n"
            f"📝 **Biến động cược:**\n" + (payout_summary if payout_summary else "*(Không có lượt cược nào phiên này)*")
        )

        if target_chat_id != "NHẬP_CHAT_ID_VÀO_ĐÂY":
            try:
                await application.bot.send_message(chat_id=target_chat_id, text=result_msg, parse_mode="Markdown")
            except Exception as e:
                print(f"Lỗi gửi kết quả: {e}")

        current_session += 1
        await asyncio.sleep(8) # Thời gian nghỉ chuyển phiên (Tổng chu kỳ trọn vẹn ~35s)

def main():
    init_db() # Khởi tạo database chung
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Đăng ký các lệnh
    app.add_handler(CommandHandler("tai", dat_cuoc))
    app.add_handler(CommandHandler("xiu", dat_cuoc))
    app.add_handler(CommandHandler("sodu", check_sodu))
    
    # Chạy vòng lặp tự động liên tục
    app.post_init = lambda app: app.create_task(game_loop(app))
    app.run_polling()

if __name__ == "__main__":
    main()
