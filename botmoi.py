import os
import random
import sqlite3
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- CẤU HÌNH CƠ BẢN ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "THẾ_TOKEN_CỦA_BẠN_VÀO_ĐÂY")
PORT = int(os.environ.get("PORT", 10000))
MIN_BET = 1000

# Biến trạng thái trò chơi
current_session = 1
is_betting_open = False
current_bets = {} 
history_cautai = [] 
global_application = None

# --- 1. QUẢN LÝ DATABASE TRỰC TIẾP TRONG 1 FILE ---
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def get_user_balance(user_id, username=""):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT OR REPLACE INTO users (user_id, username, balance) VALUES (?, ?, ?)", (user_id, username, 0))
        conn.commit()
        balance = 0
    else:
        balance = row[0]
    conn.close()
    return balance

def update_balance(user_id, amount):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# --- 2. WEB SERVER GIẢ LẬP CHỐNG NGỦ ĐÔNG RENDER ---
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Tai Xiu Bot Auto Running 24/7!")

def run_web_server():
    server = HTTPServer(('0.0.0.0', PORT), SimpleHandler)
    server.serve_forever()

Thread(target=run_web_server, daemon=True).start()

# --- 3. LỆNH ĐẶT CƯỢC & KIỂM TRA SỐ DƯ (KHÔNG CẦN LỆNH KHỞI ĐỘNG VẪN CHẠY) ---
async def dat_cuoc(update, context):
    global is_betting_open, current_bets
    if not is_betting_open:
        await update.message.reply_text("⏳ Đang trong thời gian chờ kết quả hoặc chuẩn bị phiên mới, chưa thể cược!")
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
    
    balance = get_user_balance(user_id, username)

    if balance < amount:
        await update.message.reply_text(f"❌ Số dư không đủ! Số dư hiện tại: `{balance:,}` điểm.", parse_mode="Markdown")
        return

    update_balance(user_id, -amount)
    current_bets[user_id] = {"choice": command, "amount": amount, "name": username}

    new_balance = get_user_balance(user_id)
    await update.message.reply_text(
        f"✅ Đã cược `{amount:,}` điểm vào **{command.upper()}**.\n"
        f"💰 Số dư còn lại: `{new_balance:,}` điểm",
        parse_mode="Markdown"
    )

async def check_sodu(update, context):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    balance = get_user_balance(user_id, username)
    await update.message.reply_text(f"💰 Số dư tài khoản của bạn: `{balance:,}` điểm", parse_mode="Markdown")

# --- 4. VÒNG LẶP TỰ ĐỘNG HOÀN TOÀN (35S 1 LƯỢT + 10S ĐẾM NGƯỢC) ---
async def game_loop():
    global current_session, is_betting_open, current_bets, history_cautai, global_application
    target_chat_id = os.getenv("CHAT_ID", "NHẬP_CHAT_ID_VÀO_ĐÂY")

    # Đợi 5 giây cho bot ổn định khi vừa khởi động xong
    await asyncio.sleep(5)

    while True:
        # --- GIAI ĐOẠN 1: MỞ CƯỢC (25 GIÂY CHO NGƯỜI CHƠI NHẬP LỆNH) ---
        is_betting_open = True
        current_bets.clear()
        
        cau_string = " ".join(history_cautai) if history_cautai else "Chưa có lịch sử"

        if target_chat_id != "NHẬP_CHAT_ID_VÀO_ĐÂY" and global_application:
            try:
                await global_application.bot.send_message(
                    chat_id=target_chat_id,
                    text=f"🔔 **PHIÊN #{current_session} BẮT ĐẦU!**\n"
                         f"📈 **Dây cầu gần đây:** {cau_string}\n"
                         f"----------------------------------\n"
                         f"⏰ Thời gian đặt cược: **25 giây**\n"
                         f"👉 Cú pháp: `/tai <số>` hoặc `/xiu <số>`",
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Lỗi gửi tin nhắn mở phiên: {e}")

        await asyncio.sleep(25)

        # --- GIAI ĐOẠN 2: ĐẾM NGƯỢC 10 GIÂY & KHÓA CƯỢC ---
        is_betting_open = False
        
        if target_chat_id != "NHẬP_CHAT_ID_VÀO_ĐÂY" and global_application:
            try:
                msg = await global_application.bot.send_message(
                    chat_id=target_chat_id,
                    text="🔒 **ĐÃ KHÓA CƯỢC!** Chuẩn bị tung xúc xắc trong **10 giây**..."
                )
                
                # Đếm ngược thực tế từng giây (từ 10 về 1)
                for i in range(10, 0, -1):
                    await asyncio.sleep(1)
                    # Nếu muốn cập nhật số đếm ngược, có thể bỏ qua hoặc giữ nguyên dòng thông báo tĩnh tùy thích
            except Exception as e:
                print(f"Lỗi đếm ngược: {e}")
        else:
            await asyncio.sleep(10)

        # --- GIAI ĐOẠN 3: TUNG XÚC XẮC & TRẢ THƯỞNG ---
        d1, d2, d3 = random.randint(1, 6), random.randint(1, 6), random.randint(1, 6)
        total = d1 + d2 + d3

        if d1 == d2 == d3:
            winning_choice = "bao"
            result_icon = "🎲"
            result_name = "BÃO (Nhà cái ăn)"
            history_cautai.append("🟦")
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

        if len(history_cautai) > 10:
            history_cautai.pop(0)

        payout_summary = ""
        for uid, data in current_bets.items():
            choice = data["choice"]
            amount = data["amount"]
            name = data["name"]
            
            if winning_choice == "bao":
                payout_summary += f"👤 {name}: Thua `{amount:,}` điểm (Bão)\n"
            elif choice == winning_choice:
                win_amount = amount * 2
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

        if target_chat_id != "NHẬP_CHAT_ID_VÀO_ĐÂY" and global_application:
            try:
                await global_application.bot.send_message(chat_id=target_chat_id, text=result_msg, parse_mode="Markdown")
            except Exception as e:
                print(f"Lỗi gửi kết quả: {e}")

        current_session += 1
        # Thời gian nghỉ ngắn trước khi sang phiên mới (tổng cộng thời gian mỗi vòng lặp trọn vẹn sẽ cực kỳ chuẩn xác)
        await asyncio.sleep(3)

def run_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(game_loop())

# --- 5. HÀM KHỞI CHẠY ---
def main():
    global global_application
    init_db()
    
    global_application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Chỉ cần đăng ký lệnh cược và xem số dư, không cần lệnh bắt đầu game
    global_application.add_handler(CommandHandler("tai", dat_cuoc))
    global_application.add_handler(CommandHandler("xiu", dat_cuoc))
    global_application.add_handler(CommandHandler("sodu", check_sodu))
    
    # Chạy vòng lặp tự động độc lập
    loop = asyncio.new_event_loop()
    t = Thread(target=run_async_loop, args=(loop,), daemon=True)
    t.start()
    
    global_application.run_polling()

if __name__ == "__main__":
    main()
