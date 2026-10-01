import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# Cấu hình log để dễ theo dõi lỗi nếu có
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Hàm xử lý khi người dùng gõ lệnh /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    await update.message.reply_text(f"Xin chào {user_name}! Bot game của bạn đã hoạt động thành công.")

if __name__ == '__main__':
    # THAY ĐOẠN TOKEN DƯỚI ĐÂY BẰNG TOKEN BOT CỦA BẠN (Lấy từ BotFather)
    TOKEN = "8911175761:AAHwll8kdFRp9LmVGhFWctwMTE5-EYuXE00"
    
    # Khởi tạo ứng dụng bot
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Đăng ký lệnh /start cho bot
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)
    
    print("Bot đang chạy...")
    # Bắt đầu chạy bot
    application.run_polling()
