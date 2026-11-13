import os
import telebot
from telebot.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

# Lấy token từ biến môi trường trên Render
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    print("LỖI: Chưa cài đặt biến môi trường BOT_TOKEN trên Render!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    # ĐÃ CẬP NHẬT LINK GITHUB PAGES CỦA BẠN VÀO ĐÂY
    web_app_url = "https://hoguong45-sketch.github.io/duong0/"
    
    markup = InlineKeyboardMarkup()
    web_app_btn = InlineKeyboardButton(
        text="🚀 Mở Bank Ảo", 
        web_app=WebAppInfo(url=web_app_url)
    )
    markup.add(web_app_btn)

    bot.send_message(
        message.chat.id, 
        "Chào mừng bạn! Bấm nút bên dưới để mở giao diện Mini App.", 
        reply_markup=markup
    )

if __name__ == "__main__":
    print("Bot đang chạy...")
    bot.infinity_polling()
