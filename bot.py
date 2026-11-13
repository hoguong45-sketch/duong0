import os
import telebot
from telebot.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

# Sử dụng token trực tiếp hoặc lấy từ biến môi trường của Render
BOT_TOKEN = "8911175761:AAEV3V4LaDW_AO_Lfou4e2vIs6E61yZ-jzg"

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Đường dẫn Web App / Mini App của bạn
    web_app_url = "https://hoguong45-sketch.github.io/duong0/"
    
    markup = InlineKeyboardMarkup()
    web_app_btn = InlineKeyboardButton(
        text="🚀 Mở Bank Ảo", 
        web_app=WebAppInfo(url=web_app_url)
    )
    markup.add(web_app_btn)

    bot.send_message(
        message.chat.id, 
        "Chào mừng bạn đến với Ngân hàng số! Bấm nút bên dưới để mở giao diện Mini App.", 
        reply_markup=markup
    )

if __name__ == "__main__":
    print("Bot đang chạy...")
    bot.infinity_polling()
