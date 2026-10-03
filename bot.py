import os
import json
import logging
import random
import asyncio
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
    return "🤖 Bot Tổng Hợp (Tài Xỉu Group + Ví Cá Nhân + Ẩn Danh Admin) đang hoạt động 24/7!"

def run_web():
    port = int(os.getenv("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)


# =========================
# 2. CẤU HÌNH BOT
# =========================
TOKEN = os.getenv("BOT_TOKEN")  # Token của bot
ADMIN_ID = 8013947246         # ID Telegram của Admin

# 👇 ĐÃ GÁN CỨNG CHÍNH XÁC ID NHÓM TELEGRAM CỦA BẠN VÀO ĐÂY
GROUP_CHAT_ID = -1003932050774 

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Lưu trữ dữ liệu người dùng & game
users_data = {}
gift_codes = {"VIP2026": 50000, "TET2026": 100000}
history_phien = []
phien_id = 1

# DANH SÁCH NGÂN HÀNG (ĐÃ ẨN DANH TÊN THẬT CỦA ADMIN)
BANK_LIST = [
    {"name": "MSB", "stk": "6314072009", "chủ tài khoản": "HỆ THỐNG TỰ ĐỘNG (ANONYMOUS)"},
    {"name": "MBBank", "stk": "0776876883", "chủ tài khoản": "HỆ THỐNG TỰ ĐỘNG (ANONYMOUS)"}
]


# =========================
# 3. XỬ LÝ LỆNH START & MENU
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    chat_id = update.message.chat_id

    # Nếu gọi trong Nhóm (Group / Supergroup)
    if update.message.chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            f"🎲 **HỆ THỐNG TÀI XỈU VIP ĐANG HOẠT ĐỘNG TRONG NHÓM**\n"
            f"📌 Group ID hiện tại: `{chat_id}`\n\n"
            f"📋 **Các lệnh chơi tại nhóm:**\n"
            f"• `/tai [số_tiền]` - Đặt cửa Tài\n"
            f"• `/xiu [số_tiền]` - Đặt cửa Xỉu\n"
            f"• `/sd` hoặc `/tk` - Kiểm tra số dư ví\n"
            f"• `/ls` - Xem lịch sử phiên\n\n"
            f"💡 *Chưa có tài khoản? Hãy inbox riêng cho Bot gõ `/start` để đăng ký!*",
            parse_mode="Markdown"
        )
        return

    # Nếu chat riêng (Inbox) với Bot
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        users_data[user_id] = {
            "step": "waiting_name",
            "custom_id": f"CUBE{random.randint(1000,9999)}",
            "balance": 0
        }
        await update.message.reply_text(
            f"👋 Chào mừng bạn đến với hệ thống giao dịch tự động!\n"
            f"🆔 ID định danh riêng của bạn: `{users_data[user_id]['custom_id']}`\n\n"
            f"⚠️ **BẮT BUỘC:** Vui lòng nhập **Họ và Tên chính xác trùng với Tài Khoản Ngân Hàng**:",
            parse_mode="Markdown"
        )
        return

    u = users_data[user_id]
    await send_main_menu(update, u)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    # Chỉ xử lý nhập tên trong chat riêng (private)
    if update.message.chat.type != "private":
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id in users_data and users_data[user_id].get("step") == "waiting_name":
        users_data[user_id]["name"] = text
        users_data[user_id]["step"] = "active"
        
        await update.message.reply_text(
            f"✅ Đăng ký thành công tài khoản cá nhân!\n"
            f"📌 Tên chủ thẻ: **{text}**\n"
            f"🆔 ID của bạn: `{users_data[user_id]['custom_id']}`\n\n"
            f"Bây giờ bạn có thể dùng các lệnh: `/sd`, `/nap`, `/rut`, `/code`",
            parse_mode="Markdown"
        )
        return

async def send_main_menu(update, u):
    await update.message.reply_text(
        f"👤 Tài khoản: **{u['name']}**\n"
        f"🆔 ID: `{u['custom_id']}`\n"
        f"💰 Số dư ví: `{u['balance']:,}` điểm\n\n"
        f"📋 Menu lệnh: `/sd`, `/nap`, `/rut`, `/code`",
        parse_mode="Markdown"
    )


# =========================
# 4. KIỂM TRA SỐ DƯ (/sd & /tk)
# =========================
async def check_sd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text(
            f"⚠️ [{user.first_name}](tg://user?id={user_id}) bạn chưa đăng ký tài khoản!\n"
            "Vui lòng **nhắn tin riêng (Inbox)** cho bot và gõ lệnh `/start` trước nhé!",
            parse_mode="Markdown"
        )
        return
    
    u = users_data[user_id]
    await update.message.reply_text(
        f"👤 Người chơi: [{user.first_name}](tg://user?id={user_id})\n"
        f"📌 Tên chủ thẻ: **{u['name']}**\n"
        f"🆔 ID định danh: `{u['custom_id']}`\n"
        f"💰 Số dư ví hiện tại: `{u['balance']:,}` điểm",
        parse_mode="Markdown"
    )


# =========================
# 5. NẠP, RÚT & NHẬP CODE
# =========================
async def menu_nap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` ở tin nhắn riêng để đăng ký tên trước khi nạp!")
        return

    u = users_data[user_id]
    bank = random.choice(BANK_LIST)

    nap_text = (
        f"💳 **HƯỚNG DẪN NẠP ĐIỂM (BẢO MẬT)**\n\n"
        f"👤 Tên người nạp: *{u['name']}*\n"
        f"🆔 ID của bạn: `{u['custom_id']}`\n"
        f"🏦 Ngân hàng: *{bank['name']}* | STK: `{bank['stk']}`\n"
        f"📌 Nội dung CK bắt buộc:\n`NAP {u['name']} {u['custom_id']}`"
    )
    keyboard = [[InlineKeyboardButton("✅ Đã Chuyển Khoản, Báo Duyệt Ngay", callback_data=f"nap_click_{user_id}")]]
    await update.message.reply_text(nap_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def menu_rut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` trước!")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Sai cú pháp! Dùng: `/rut [số_tiền] [STK - Ngân hàng]`", parse_mode="Markdown")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền rút không hợp lệ!")
        return

    bank_info = " ".join(context.args[1:])
    u = users_data[user_id]

    if u["balance"] < amount:
        await update.message.reply_text("❌ Số dư ví của bạn không đủ!")
        return

    keyboard = [
        [
            InlineKeyboardButton("✅ Duyệt Rút", callback_data=f"rut_yes_{user_id}_{amount}"),
            InlineKeyboardButton("❌ Từ chối", callback_data=f"rut_no_{user_id}")
        ]
    ]

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 **YÊU CẦU RÚT TIỀN**\n👤 Khách: **{u['name']}**\n💰 Số tiền: `{amount:,}`\n🏦 STK: `{bank_info}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("⏳ Yêu cầu rút tiền đã được gửi tới Admin!")

async def nhap_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` để đăng ký trước!")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Vui lòng nhập mã code! Ví dụ: `/code VIP2026`")
        return

    code = context.args[0].strip()
    if code in gift_codes:
        reward = gift_codes[code]
        users_data[user_id]["balance"] += reward
        del gift_codes[code]
        await update.message.reply_text(f"🎉 Nhận mã thành công! Cộng thêm `{reward:,}` điểm.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Mã code không tồn tại hoặc đã được sử dụng!")


# =========================
# 6. LỆNH ADMIN TẠO CODE
# =========================
async def tao_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Dùng: `/taocode [MÃ] [số_tiền]`")
        return
    code_name = context.args[0].strip().upper()
    try:
        amount = int(context.args[1])
    except ValueError:
        return
    gift_codes[code_name] = amount
    await update.message.reply_text(f"✅ Tạo mã `{code_name}` trị giá `{amount:,}` thành công!")


# =========================
# 7. TÍNH NĂNG GAME TÀI XỈU & VÒNG LẶP TỰ ĐỘNG
# =========================
async def dat_cuoc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text(f"⚠️ [{user.first_name}], hãy nhắn tin riêng cho Bot gõ `/start` để đăng ký tài khoản trước!")
        return

    if not context.args:
        command = update.message.text.split()[0].lower()
        await update.message.reply_text(f"⚠️ Dùng: `{command} [số_tiền]` (Ví dụ: `{command} 10000`)")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền cược không hợp lệ!")
        return

    u = users_data[user_id]
    if u["balance"] < amount:
        await update.message.reply_text(f"❌ [{u['name']}]: Số dư không đủ `{amount:,}` điểm!")
        return

    command = update.message.text.split()[0].lower()
    choice = "TÀI" if "tai" in command else "XỈU"

    u["balance"] -= amount
    await update.message.reply_text(f"🎲 **{u['name']}** đặt **{amount:,}** vào cửa **{choice}** thành công! (Ví còn: `{u['balance']:,}`)")

async def xem_lich_su(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not history_phien:
        await update.message.reply_text("📜 Chưa có lịch sử phiên cược nào.")
        return
    text = "📜 **Lịch sử các phiên gần đây:**\n" + "\n".join(history_phien[-10:])
    await update.message.reply_text(text, parse_mode="Markdown")

# 🟢 VÒNG LẶP TỰ ĐỘNG ĐẨY TIN NHẮN VÀO NHÓM CHAT
async def auto_taixiu_loop(application):
    global phien_id
    await asyncio.sleep(5)
    while True:
        try:
            if GROUP_CHAT_ID:
                # 1. Thông báo mở phiên mới
                history_text = "\n".join(history_phien[-5:]) if history_phien else "Chưa có"
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=(
                        f"🎲 **PHIÊN #{phien_id}**\n\n"
                        f"📈 **Lịch sử gần đây:**\n{history_text}\n\n"
                        f"⏰ **Chuẩn bị đặt cược trong 40 giây...**\n\n"
                        f"👉 Cú pháp đặt cược:\n"
                        f"• `/tai [số_tiền]`\n"
                        f"• `/xiu [số_tiền]`"
                    ),
                    parse_mode="Markdown"
                )
            
            # Chờ người chơi đặt cược trong 40 giây
            await asyncio.sleep(40)

            # 2. Khóa sổ và tung xúc xắc ngẫu nhiên
            d1, d2, d3 = random.randint(1, 6), random.randint(1, 6), random.randint(1, 6)
            tong = d1 + d2 + d3
            ket_qua = "TÀI" if tong >= 11 else "XỈU"
            
            history_phien.append(f"Phiên #{phien_id}: {d1}-{d2}-{d3} ({tong}đ - {ket_qua})")
            if len(history_phien) > 20:
                history_phien.pop(0)

            if GROUP_CHAT_ID:
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=f"🔒 **Đã khóa sổ! Kết quả phiên #{phien_id}:**\n🎲 Xúc xắc: `{d1} - {d2} - {d3}` (Tổng: **{tong} điểm**) -> **{ket_qua}**",
                    parse_mode="Markdown"
                )
            
            phien_id += 1
        except Exception as e:
            logging.error(f"Lỗi vòng lặp phiên: {e}")
            
        await asyncio.sleep(5)


# =========================
# 8. XỬ LÝ NÚT BẤM (CALLBACK)
# =========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("nap_click_"):
        target_id = int(data.split("_")[2])
        u = users_data.get(target_id, {})
        admin_keyboard = [
            [
                InlineKeyboardButton("✅ Duyệt +50,000", callback_data=f"nap_yes_{target_id}_50000"),
                InlineKeyboardButton("✅ Duyệt +100,000", callback_data=f"nap_yes_{target_id}_100000"),
            ],
            [InlineKeyboardButton("❌ Từ chối nạp", callback_data=f"nap_no_{target_id}")]
        ]
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔔 Yêu cầu nạp từ **{u.get('name')}** (`{u.get('custom_id')}`)",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(admin_keyboard)
        )
        await query.edit_message_text(text="✅ Đã gửi yêu cầu nạp cho Admin!")

    elif data.startswith("nap_yes_"):
        parts = data.split("_")
        target_id, amount = int(parts[2]), int(parts[3])
        if target_id in users_data:
            users_data[target_id]["balance"] += amount
        await query.edit_message_text(text=f"✅ Đã duyệt cộng `{amount:,}` điểm!")
        try:
            await context.bot.send_message(chat_id=target_id, text=f"🎉 Nạp thành công! Ví được cộng `{amount:,}` điểm.")
        except:
            pass

    elif data.startswith("nap_no_"):
        target_id = int(data.split("_")[2])
        await query.edit_message_text(text="❌ Đã từ chối nạp.")
        try:
            await context.bot.send_message(chat_id=target_id, text="❌ Yêu cầu nạp tiền bị từ chối.")
        except:
            pass

    elif data.startswith("rut_yes_"):
        parts = data.split("_")
        target_id, amount = int(parts[2]), int(parts[3])
        if target_id in users_data:
            users_data[target_id]["balance"] -= amount
        await query.edit_message_text(text="✅ Đã duyệt rút tiền!")
        try:
            await context.bot.send_message(chat_id=target_id, text=f"🎉 Rút `{amount:,}` điểm thành công!")
        except:
            pass

    elif data.startswith("rut_no_"):
        target_id = int(data.split("_")[2])
        await query.edit_message_text(text="❌ Đã từ chối rút.")
        try:
            await context.bot.send_message(chat_id=target_id, text="❌ Yêu cầu rút điểm bị từ chối.")
        except:
            pass


# =========================
# 9. KHỞI CHẠY HỆ THỐNG
# =========================
def main():
    if not TOKEN:
        raise RuntimeError("Chưa cấu hình BOT_TOKEN.")

    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sd", check_sd))
    app.add_handler(CommandHandler("tk", check_sd))
    app.add_handler(CommandHandler("nap", menu_nap))
    app.add_handler(CommandHandler("rut", menu_rut))
    app.add_handler(CommandHandler("code", nhap_code))
    app.add_handler(CommandHandler("taocode", tao_code))
    app.add_handler(CommandHandler("tai", dat_cuoc))
    app.add_handler(CommandHandler("xiu", dat_cuoc))
    app.add_handler(CommandHandler("ls", xem_lich_su))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot đã khởi động và sẵn sàng đẩy game vào nhóm...")
    
    async def post_init(application):
        asyncio.create_task(auto_taixiu_loop(application))
        
    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
