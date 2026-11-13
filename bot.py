import os
import telebot
from telebot.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, send_from_directory
from threading import Thread

# --- 1. CẤU HÌNH BOT ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

# --- 2. CẤU HÌNH WEB SERVER (ĐỂ CHỨA GIAO DIỆN) ---
app = Flask(__name__, static_folder='.')

@app.route('/')
def serve_index():
    # Trả về file index.html nằm cùng thư mục
    return send_from_directory('.', 'index.html')

def run_web():
    # Render sẽ cấp một cổng (PORT) tự động, nếu không có thì dùng 8080
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# --- 3. XỬ LÝ LỆNH /start (TỰ ĐỘNG BẬT APP) ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Lấy link Render của chính bạn (ví dụ: https://ten-app.onrender.com)
    # BẠN CẦN THAY LINK NÀY BẰNG LINK WEB SERVICE CỦA BẠN TRÊN RENDER
    web_app_url = "https://TEN-WEB-SERVICE-CUA-BAN.onrender.com"
    
    markup = InlineKeyboardMarkup()
    # Tạo nút mở app
    web_app_btn = InlineKeyboardButton(
        text="🚀 Bấm để mở Bank Ảo", 
        web_app=WebAppInfo(url=web_app_url)
    )
    markup.add(web_app_btn)

    bot.send_message(
        message.chat.id, 
        "Nhấn nút bên dưới để mở giao diện Bank Ảo (Toàn màn hình):", 
        reply_markup=markup
    )

# --- 4. CHẠY SONG SONG CẢ BOT VÀ WEB ---
if __name__ == "__main__":
    # Chạy Web Server ở một luồng riêng
    t = Thread(target=run_web)
    t.start()
    
    # Chạy Bot ở luồng chính
    print("Bot và Web đang chạy...")
    bot.infinity_polling()
