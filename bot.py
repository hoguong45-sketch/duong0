import asyncio
import random
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Bật logging để theo dõi trạng thái
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Cấu hình Token bot của bạn
TOKEN = "8911175761:AAHwll8kdFRp9LmVGhFWctwMTE5-EYuXEO0" 
CHAT_ID = "@your_channel_or_group_username"  # Thay bằng username nhóm của bạn (VD: -100xxxxxxxxxx)

# Trạng thái game
current_session = 0
game_history = []  # Lưu lịch sử ('TÀI' hoặc 'XỈU')
bets = {}  # Lưu cược của người chơi
is_locked = False

async def start_game(application):
    global current_session, game_history, bets, is_locked
    
    while True:
        current_session += 1
        bets = {}
        is_locked = False
        
        # 1. BẮT ĐẦU PHIÊN MỚI (Mở cược 40 giây)
        recent_trend = " ".join(["🔴" if h == "TÀI" else "🟢" for h in game_history[-5:]]) if game_history else "Chưa có"
        
        start_text = (
            f"🔔 **PHIÊN #{current_session} BẮT ĐẦU!**\n"
            f"📈 **Dây cầu gần đây:** {recent_trend}\n"
            f"----------------------------------------\n"
            f"⏰ **Thời gian đặt cược:** 40 giây\n"
            f"👉 **Cú pháp:** `/tai <số>` hoặc `/xiu <số>`"
        )
        
        await application.bot.send_message(chat_id=CHAT_ID, text=start_text, parse_mode="Markdown")
        
        # Chờ 40 giây cho người chơi đặt cược
        await asyncio.sleep(40)
        
        # 2. KHÓA CƯỢC (10 giây cuối trước khi tung)
        is_locked = True
        
        # Tự động khóa chat thành viên trong nhóm
        try:
            await application.bot.set_chat_permissions(
                chat_id=CHAT_ID,
                permissions={
                    "can_send_messages": False,
                    "can_send_media_messages": False,
                    "can_send_polls": False,
                    "can_send_other_messages": False
                }
            )
        except Exception as e:
            logging.error(f"Không thể khóa chat (Hãy cấp quyền Admin cho bot): {e}")

        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=f"🔒 **ĐÃ KHÓA CƯỢC!** Chuẩn bị tung xúc xắc trong **10 giây**...",
            parse_mode="Markdown"
        )
        
        # Chờ 10 giây cuối
        await asyncio.sleep(10)
        
        # 3. TUNG XÚC XẮC & TRẢ KẾT QUẢ
        d1, d2, d3 = random.randint(1, 6), random.randint(1, 6), random.randint(1, 6)
        total = d1 + d2 + d3
        result = "TÀI" if total >= 11 else "XỈU"
        game_history.append(result)
        
        # Hiệu ứng chờ lắc xúc xắc
        dice_msg = await application.bot.send_message(chat_id=CHAT_ID, text="🎲 Đang lắc xúc xắc...")
        await asyncio.sleep(1)
        
        trend_full = " ".join(["🔴" if h == "TÀI" else "🟢" for h in game_history[-10:]])
        result_icon = "🔴" if result == "TÀI" else "🟢"
        
        result_text = (
            f"📊 **KẾT QUẢ PHIÊN: #{current_session}**\n"
            f"----------------------------------------\n"
            f"🎲 **Xúc xắc:** {d1} - {d2} - {d3}\n"
            f"🔢 **Tổng điểm:** {total} ({result_icon} {result})\n"
            f"📈 **Dây cầu:** {trend_full}\n"
            f"----------------------------------------\n"
            f"📝 **Biến động cược:**\n"
        )
        
        if bets:
            bet_details = []
            for uid, data in bets.items():
                win = data['choice'] == result.lower()
                status = "🟢 THẮNG" if win else "🔴 THUA"
                bet_details.append(f"- @{data['name']}: Đặt {data['choice'].upper()} ({data['amount']}) -> {status}")
            result_text += "\n".join(bet_details)
        else:
            result_text += "(Không có lượt cược nào phiên này)"
            
        await application.bot.edit_message_text(
            chat_id=CHAT_ID,
            message_id=dice_msg.message_id,
            text=result_text,
            parse_mode="Markdown"
        )
        
        # Mở lại quyền chat cho thành viên
        try:
            await application.bot.set_chat_permissions(
                chat_id=CHAT_ID,
                permissions={
                    "can_send_messages": True,
                    "can_send_media_messages": True,
                    "can_send_polls": True,
                    "can_send_other_messages": True
                }
            )
        except Exception as e:
            logging.error(f"Không thể mở khóa chat: {e}")
            
        await asyncio.sleep(2)

async def place_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_locked, bets
    if is_locked:
        await update.message.reply_text("🔒 Đã khóa cược, không thể đặt cược lúc này!")
        return
        
    command = update.message.text.split()
    cmd_name = command[0].lower() # /tai hoặc /xiu
    
    if len(command) < 2:
        await update.message.reply_text("⚠️ Sai cú pháp! Vui lòng dùng: `/tai <số>` hoặc `/xiu <số>`", parse_mode="Markdown")
        return
        
    try:
        amount = int(command[1])
        if amount <= 0:
            raise ValueError()
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền cược không hợp lệ!")
        return
        
    user = update.effective_user
    choice = "tai" if "tai" in cmd_name else "xiu"
    
    bets[user.id] = {
        "name": user.username or user.first_name,
        "choice": choice,
        "amount": amount
    }
    
    await update.message.reply_text(f"✅ @{user.username or user.first_name} đã đặt **{amount}** vào **{choice.upper()}** thành công!", parse_mode="Markdown")

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Đăng ký lệnh cược
    app.add_handler(CommandHandler("tai", place_bet))
    app.add_handler(CommandHandler("xiu", place_bet))
    
    # Khởi chạy luồng game 24/7 ngầm
    async def post_init(application):
        asyncio.create_task(start_game(application))
        
    app.post_init = post_init
    
    print("🤖 Bot Tài Xỉu @Chanleduongcube_bot đang chạy 24/7...")
    app.run_polling()

if __name__ == "__main__":
    main()
