import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    await update.message.reply_text(f"Xin chào {user_name}! Bot Chẵn Lẻ / Tài Xỉu của bạn đã hoạt động thành công 24/7 trên Render!")

if __name__ == '__main__':
    TOKEN = "8911175761:AAHwll8kdFRp9LmVGhFWctwMTE5-EYuXEO0"
    
    application = ApplicationBuilder().token(TOKEN).build()
    
    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)
    
    print("Bot đang chạy...")
    application.run_polling()
