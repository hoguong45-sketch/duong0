import os
import telebot
from telebot.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8911175761:AAEV3V4LaDW_AO_Lfou4e2vIs6E61yZ-jzg"
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    web_app_url = "https://hoguong45-sketch.github.io/duong0/"
    
    markup = InlineKeyboardMarkup()
    web_app_btn = InlineKeyboardButton(
        text="🚀 Mở BankTongocduong", 
        web_app=WebAppInfo(url=web_app_url)
    )
    markup.add(web_app_btn)

    bot.send_message(
        message.chat.id, 
        "Chào mừng bạn đến với **BankTongocduong**!\n\nBấm nút bên dưới để mở giao diện quản lý tài khoản và chọn Đăng nhập hoặc Đăng ký.", 
        reply_markup=markup,
        parse_mode="Markdown"
    )

if __name__ == "__main__":
    print("Bot đang chạy...")
    bot.infinity_polling()
