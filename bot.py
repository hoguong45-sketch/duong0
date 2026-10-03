import os
import json
import logging
import random
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# 1. WEB SERVER DUY TRÌ 24/7 (RENDER)
# =========================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "🤖 Bot Tổng Hợp (Tài Xỉu + Ví Nạp/Rút) đang hoạt động 24/7!"

def run_web():
    port = int(os.getenv("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)


# =========================
# 2. CẤU HÌNH BOT
# =========================
TOKEN = os.getenv("BOT_TOKEN")  # Token của bot
ADMIN_ID = 8013947246         # ID Telegram của bạn để nhận thông báo nạp/rút

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Lưu trữ dữ liệu người dùng: {user_id: {"name": "...", "custom_id": "...", "balance": 0, "step": "..."}}
users_data = {}
gift_codes = {"VIP2026": 50000, "TET2026": 100000}
history_phien = []  # Lưu lịch sử các phiên Tài Xỉu gần đây

BANK_LIST = [
    {"name": "MSB", "stk": "6314072009", "chủ tài khoản": "TÔ NGỌC DƯƠNG"},
    {"name": "MBBank", "stk": "0776876883", "chủ tài khoản": "TÔ NGỌC DƯƠNG"}
]


# =========================
# XỬ LÝ ĐĂNG KÝ TÊN KHI /START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if user_id not in users_data or users_data[user_id].get("step") != "active":
        users_data[user_id] = {
            "step": "waiting_name",
            "custom_id": f"CUBE{random.randint(1000,9999)}",
            "balance": 0
        }
        await update.message.reply_text(
            f"👋 Chào mừng bạn đến với hệ thống!\n"
            f"🆔 ID định danh của bạn: `{users_data[user_id]['custom_id']}`\n\n"
            f"⚠️ **BẮT BUỘC:** Vui lòng nhập **Họ và Tên chính xác trùng với Tên Chủ Tài Khoản Ngân Hàng** của bạn để dùng khi rút tiền:",
            parse_mode="Markdown"
        )
        return

    u = users_data[user_id]
    await send_main_menu(update, u)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not update.message or not update.message.text:
        return
    
    text = update.message.text.strip()

    # Xử lý đoạn chờ nhập tên chính chủ
    if user_id in users_data and users_data[user_id].get("step") == "waiting_name":
        users_data[user_id]["name"] = text
        users_data[user_id]["step"] = "active"
        
        await update.message.reply_text(
            f"✅ Đăng ký tên thành công!\n"
            f"📌 Tên chủ thẻ: **{text}**\n"
            f"🆔 ID của bạn: `{users_data[user_id]['custom_id']}`\n\n"
            f"Bây giờ bạn có thể sử dụng đầy đủ các lệnh:\n"
            f"• `/sd` - Kiểm tra số dư\n"
            f"• `/nap` - Nạp tiền\n"
            f"• `/rut [số_tiền] [STK - Ngân hàng]` - Rút tiền\n"
            f"• `/code [mã]` - Nhập mã quà tặng\n"
            f"• `/tai [số_tiền]` hoặc `/xiu [số_tiền]` - Đặt cược",
            parse_mode="Markdown"
        )
        return

async def send_main_menu(update, u):
    await update.message.reply_text(
        f"👤 Tài khoản: **{u['name']}**\n"
        f"🆔 ID: `{u['custom_id']}`\n"
        f"💰 Số dư ví: `{u['balance']:,}` điểm\n\n"
        f"📋 Menu lệnh hệ thống:\n"
        f"• `/sd` - Kiểm tra số dư ví\n"
        f"• `/nap` - Hướng dẫn nạp điểm\n"
        f"• `/rut [số_tiền] [STK - Ngân hàng]` - Yêu cầu rút tiền\n"
        f"• `/code [mã]` - Nhập mã quà tặng\n"
        f"• `/ls` - Xem lịch sử phiên\n"
        f"• `/tai [số_tiền]` / `/xiu [số_tiền]` - Đặt cược Tài/Xỉu",
        parse_mode="Markdown"
    )


# =========================
# QUẢN LÝ VÍ & GIAO DỊCH (NẠP, RÚT, SỐ DƯ, CODE)
# =========================
async def check_sd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` và hoàn tất đăng ký tên ngân hàng trước!")
        return
    
    u = users_data[user_id]
    await update.message.reply_text(
        f"👤 Tên chủ thẻ: **{u['name']}**\n"
        f"🆔 ID: `{u['custom_id']}`\n"
        f"💰 Số dư ví của bạn: `{u['balance']:,}` điểm",
        parse_mode="Markdown"
    )

async def menu_nap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` để đăng ký tên trước khi nạp!")
        return

    u = users_data[user_id]
    bank = random.choice(BANK_LIST)

    nap_text = (
        f"💳 **HƯỚNG DẪN NẠP ĐIỂM**\n\n"
        f"👤 Tên chủ thẻ: *{u['name']}*\n"
        f"🆔 ID định danh: `{u['custom_id']}`\n"
        f"🏦 Ngân hàng: *{bank['name']}*\n"
        f"📌 Số tài khoản: `{bank['stk']}`\n"
        f"👤 Chủ STK: *{bank['chủ tài khoản']}*\n"
        f"💰 Nội dung chuyển khoản bắt buộc:\n`NAP {u['name']} {u['custom_id']}`\n\n"
        f"⚠️ Chuyển khoản xong hãy bấm nút bên dưới để báo Admin duyệt!"
    )
    
    keyboard = [[InlineKeyboardButton("✅ Đã Chuyển Khoản, Báo Admin Duyệt", callback_data=f"nap_done_{user_id}")]]
    await update.message.reply_text(nap_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def menu_rut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` trước!")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Sai cú pháp! Dùng: `/rut [số_tiền] [STK - Tên Ngân Hàng]`", parse_mode="Markdown")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền rút không hợp lệ!")
        return

    bank_info = " ".join(context.args[1:])
    u = users_data[user_id]

    if u["balance"] < amount:
        await update.message.reply_text("❌ Số dư ví của bạn không đủ để thực hiện lệnh rút này!")
        return

    keyboard = [
        [
            InlineKeyboardButton("✅ Duyệt Rút", callback_data=f"rut_yes_{user_id}_{amount}"),
            InlineKeyboardButton("❌ Từ chối", callback_data=f"rut_no_{user_id}")
        ]
    ]

    # Gửi thông báo về cho Admin
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"🔔 **YÊU CẦU RÚT TIỀN MỚI**\n\n"
            f"👤 Khách: **{u['name']}**\n"
            f"🆔 ID: `{u['custom_id']}`\n"
            f"💰 Số tiền rút: `{amount:,}` điểm\n"
            f"🏦 Nhận tiền tại STK: `{bank_info}`"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await update.message.reply_text("⏳ Yêu cầu rút tiền đã được gửi tới hệ thống Admin, vui lòng chờ xử lý!")

async def nhap_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` đăng ký tên trước khi nhập code!")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Vui lòng nhập mã code! Ví dụ: `/code VIP2026`", parse_mode="Markdown")
        return

    code = context.args[0].strip()
    if code in gift_codes:
        reward = gift_codes[code]
        users_data[user_id]["balance"] += reward
        del gift_codes[code]
        await update.message.reply_text(f"🎉 Nhận mã thành công! Đã cộng thêm `{reward:,}` điểm vào ví.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Mã code không tồn tại hoặc đã được sử dụng!")


# =========================
# TÍNH NĂNG GAME TÀI XỈU
# =========================
async def dat_cuoc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` để đăng ký tài khoản trước khi chơi!")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Vui lòng nhập số tiền cược! Ví dụ: `/tai 10000` hoặc `/xiu 20000`")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền cược không hợp lệ!")
        return

    u = users_data[user_id]
    if u["balance"] < amount:
        await update.message.reply_text("❌ Số dư ví của bạn không đủ để đặt cược số tiền này!")
        return

    command = update.message.text.split()[0].lower()
    choice = "TÀI" if "tai" in command else "XỈU"

    # Trừ tiền cược tạm thời
    u["balance"] -= amount
    await update.message.reply_text(
        f"🎲 Đã đặt cược thành công **{amount:,}** điểm vào cửa **{choice}**!\n"
        f"💰 Số dư ví hiện tại: `{u['balance']:,}` điểm",
        parse_mode="Markdown"
    )

async def xem_lich_su(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not history_phien:
        await update.message.reply_text("📜 Chưa có lịch sử phiên cược nào gần đây.")
        return
    text = "📜 **Lịch sử các phiên gần đây:**\n" + "\n".join(history_phien[-10:])
    await update.message.reply_text(text, parse_mode="Markdown")


# =========================
# XỬ LÝ NÚT BẤM (CALLBACK)
# =========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("nap_done_"):
        target_id = int(data.split("_")[2])
        u = users_data.get(target_id, {})
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"🔔 **CÓ YÊU CẦU NẠP TIỀN**\n\n"
                f"👤 Tên: **{u.get('name')}**\n"
                f"🆔 ID: `{u.get('custom_id')}`\n"
                f"📝 Nội dung cần check: `NAP {u.get('name')} {u.get('custom_id')}`\n"
                f"👉 Kiểm tra ngân hàng và cộng điểm cho khách!"
            ),
            parse_mode="Markdown"
        )
        await query.edit_message_text(text="✅ Đã gửi yêu cầu nạp cho Admin, vui lòng đợi hệ thống duyệt!")

    elif data.startswith("rut_yes_"):
        parts = data.split("_")
        target_id = int(parts[2])
        amount = int(parts[3])
        await query.edit_message_text(text="✅ Đã duyệt rút tiền thành công!")
        try:
            await context.bot.send_message(chat_id=target_id, text=f"🎉 Yêu cầu rút `{amount:,}` điểm đã được thanh toán thành công!")
        except:
            pass

    elif data.startswith("rut_no_"):
        target_id = int(parts[2] if 'parts' in locals() else data.split("_")[2])
        await query.edit_message_text(text="❌ Đã từ chối lệnh rút.")
        try:
            await context.bot.send_message(chat_id=target_id, text="❌ Yêu cầu rút điểm của bạn đã bị từ chối.")
        except:
            pass


# =========================
# KHỞI CHẠY BOT
# =========================
def main():
    if not TOKEN:
        raise RuntimeError("Chưa cấu hình BOT_TOKEN.")

    # Chạy Web Server ngầm cho Render
    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    # Các lệnh hệ thống & ví
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sd", check_sd))
    app.add_handler(CommandHandler("tk", check_sd))
    app.add_handler(CommandHandler("nap", menu_nap))
    app.add_handler(CommandHandler("rut", menu_rut))
    app.add_handler(CommandHandler("code", nhap_code))
    
    # Các lệnh game
    app.add_handler(CommandHandler("tai", dat_cuoc))
    app.add_handler(CommandHandler("xiu", dat_cuoc))
    app.add_handler(CommandHandler("ls", xem_lich_su))

    # Xử lý tin nhắn text thường (nhập tên đăng ký)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Xử lý nút bấm xác nhận
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot tổng hợp đang chạy ổn định...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
