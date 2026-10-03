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
    return "🤖 Bot Tài Xỉu & Chẵn Lẻ VIP đang hoạt động 24/7!"

def run_web():
    port = int(os.getenv("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)


# =========================
# 2. CẤU HÌNH BOT
# =========================
TOKEN = os.getenv("BOT_TOKEN")  # Token của bot
ADMIN_ID = 8013947246         # ID Telegram của Admin
GROUP_CHAT_ID = -1003932050774 # ID Nhóm đã cấu hình

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Lưu trữ dữ liệu người dùng & game
users_data = {}
gift_codes = {"VIP2026": 50000, "TET2026": 100000}
history_phien = [] # Lưu trữ icon lịch sử (⚪ / ⚫)
phien_id = 1

# Dữ liệu cược của phiên hiện tại
current_bets = {
    "tai": {},  # {user_id: amount}
    "xiu": {},  # {user_id: amount}
    "chan": {}, # {user_id: amount}
    "le": {}    # {user_id: amount}
}

# DANH SÁCH NGÂN HÀNG HỆ THỐNG
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

    # Nếu gọi trong Nhóm
    if update.message.chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            "🎲 **HỆ THỐNG TÀI XỈU & CHẴN LẺ VIP**\n\n"
            "📋 **Lệnh chơi tại nhóm:**\n"
            "• `/tai [số_tiền]` - Đặt cửa Tài (⚫)\n"
            "• `/xiu [số_tiền]` - Đặt cửa Xỉu (⚪)\n"
            "• `/chan [số_tiền]` - Đặt cửa Chẵn (⚪)\n"
            "• `/le [số_tiền]` - Đặt cửa Lẻ (⚫)\n"
            "• `/sd` hoặc `/tk` - Kiểm tra số dư ví\n"
            "• `/ls` - Xem lịch sử phiên gần đây\n\n"
            "💡 *Chưa có tài khoản? Hãy nhắn riêng (inbox) cho Bot gõ `/start` để đăng ký!*",
            parse_mode="Markdown"
        )
        return

    # Chat riêng (Inbox) với Bot
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        users_data[user_id] = {
            "step": "waiting_name",
            "custom_id": f"CUBE{random.randint(1000,9999)}",
            "balance": 0
        }
        await update.message.reply_text(
            f"👋 Chào mừng bạn đến với hệ thống giao dịch tự động!\n"
            f"🆔 ID định danh riêng của bạn: `{users_data[user_id]['custom_id']}`\n\n"
            f"⚠️ **BẮT BUỘC:** Vui lòng nhập **Họ và Tên chính xác trùng với Tài Khoản Ngân Hàng** của bạn để rút tiền:",
            parse_mode="Markdown"
        )
        return

    u = users_data[user_id]
    await send_main_menu(update, u)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    if update.message.chat.type != "private":
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id in users_data and users_data[user_id].get("step") == "waiting_name":
        users_data[user_id]["name"] = text
        users_data[user_id]["step"] = "active"
        
        await update.message.reply_text(
            f"✅ Đăng ký tài khoản thành công!\n"
            f"📌 Tên chủ thẻ: **{text}**\n"
            f"🆔 ID của bạn: `{users_data[user_id]['custom_id']}`\n\n"
            f"Sử dụng các lệnh:\n"
            f"• `/sd` - Kiểm tra số dư\n"
            f"• `/nap [số_tiền]` - Nạp điểm (Min 30,000đ)\n"
            f"• `/rut [số_tiền] [STK] [Ngân hàng] [Chủ thẻ]` - Rút điểm (Min 70,000đ)\n"
            f"• `/code [mã]` - Nhập mã quà tặng",
            parse_mode="Markdown"
        )
        return

async def send_main_menu(update, u):
    await update.message.reply_text(
        f"👤 Tài khoản: **{u['name']}**\n"
        f"🆔 ID: `{u['custom_id']}`\n"
        f"💰 Số dư ví: `{u['balance']:,}` điểm\n\n"
        f"📋 Menu lệnh:\n"
        f"• `/sd` - Kiểm tra số dư\n"
        f"• `/nap [số_tiền]` - Nạp điểm (Min 30,000đ)\n"
        f"• `/rut [số_tiền] [STK] [Ngân hàng] [Chủ thẻ]` - Rút điểm (Min 70,000đ)\n"
        f"• `/code [mã]` - Nhập mã quà tặng",
        parse_mode="Markdown"
    )


# =========================
# 4. KIỂM TRA SỐ DƯ
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
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` ở tin nhắn riêng để đăng ký trước khi nạp!")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Vui lòng nhập số tiền muốn nạp! Min nạp: `30,000`\nCú pháp: `/nap 50000`", parse_mode="Markdown")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền nạp không hợp lệ!")
        return

    if amount < 30000:
        await update.message.reply_text("❌ Số tiền nạp tối thiểu là **30,000** điểm!", parse_mode="Markdown")
        return

    u = users_data[user_id]
    bank = random.choice(BANK_LIST)

    nap_text = (
        f"💳 **HƯỚNG DẪN NẠP ĐIỂM (BẢO MẬT)**\n\n"
        f"👤 Tên người nạp: *{u['name']}*\n"
        f"🆔 ID của bạn: `{u['custom_id']}`\n"
        f"💰 Số tiền muốn nạp: `{amount:,}` VNĐ\n"
        f"🏦 Ngân hàng: *{bank['name']}*\n"
        f"📌 Số tài khoản: `{bank['stk']}`\n"
        f"👤 Chủ tài khoản: *{bank['chủ tài khoản']}*\n"
        f"💰 Nội dung CK bắt buộc:\n`NAP {u['name']} {u['custom_id']}`\n\n"
        f"⚠️ Chuyển khoản xong hãy bấm nút bên dưới để báo duyệt!"
    )
    
    keyboard = [[InlineKeyboardButton("✅ Đã Chuyển Khoản, Báo Duyệt Ngay", callback_data=f"nap_click_{user_id}_{amount}")]]
    await update.message.reply_text(nap_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def menu_rut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` trước!")
        return

    if not context.args or len(context.args) < 4:
        await update.message.reply_text(
            "⚠️ Sai cú pháp! Min rút: `70,000`\n"
            "Dùng: `/rut [số_tiền] [STK] [Ngân_hàng] [Tên_chủ_thẻ]`\n"
            "Ví dụ: `/rut 100000 0776876883 MBBank Nguyen Van A`", 
            parse_mode="Markdown"
        )
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền rút không hợp lệ!")
        return

    if amount < 70000:
        await update.message.reply_text("❌ Số tiền rút tối thiểu là **70,000** điểm!", parse_mode="Markdown")
        return

    stk = context.args[1]
    ngan_hang = context.args[2]
    chu_the = " ".join(context.args[3:])
    
    u = users_data[user_id]

    if u["balance"] < amount:
        await update.message.reply_text("❌ Số dư ví của bạn không đủ để rút số tiền này!")
        return

    keyboard = [
        [
            InlineKeyboardButton("✅ Duyệt Rút", callback_data=f"rut_yes_{user_id}_{amount}"),
            InlineKeyboardButton("❌ Từ chối", callback_data=f"rut_no_{user_id}")
        ]
    ]

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"🔔 **YÊU CẦU RÚT TIỀN MỚI**\n\n"
            f"👤 Khách: **{u['name']}**\n"
            f"🆔 ID: `{u['custom_id']}`\n"
            f"💰 Số tiền: `{amount:,}` điểm\n"
            f"📌 STK: `{stk}`\n"
            f"🏦 Ngân hàng: `{ngan_hang}`\n"
            f"👤 Chủ thẻ: `{chu_the}`"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await update.message.reply_text("⏳ Yêu cầu rút tiền đã được gửi tới hệ thống Admin!")

async def nhap_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` để đăng ký trước khi nhập code!")
        return

    if not context.args:
        await update.message.reply_text("⚠️️ Vui lòng nhập mã code! Ví dụ: `/code VIP2026`", parse_mode="Markdown")
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
# 6. LỆNH ADMIN TẠO CODE
# =========================
async def tao_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Bạn không có quyền sử dụng lệnh này!")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Sai cú pháp! Dùng: `/taocode [MÃ] [số_tiền]`", parse_mode="Markdown")
        return

    code_name = context.args[0].strip().upper()
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền thưởng không hợp lệ!")
        return

    gift_codes[code_name] = amount
    await update.message.reply_text(
        f"✅ Tạo mã thành công!\n🎁 Mã: `{code_name}`\n💰 Giá trị: `{amount:,}` điểm",
        parse_mode="Markdown"
    )


# =========================
# 7. TÍNH NĂNG ĐẶT CƯỢC (TÀI / XỈU / CHẴN / LẺ)
# =========================
async def dat_cuoc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text(
            f"⚠️ [{user.first_name}](tg://user?id={user_id}) bạn chưa đăng ký tài khoản!\n"
            "Vui lòng nhắn tin riêng cho Bot và gõ `/start` để đăng ký trước khi chơi!",
            parse_mode="Markdown"
        )
        return

    if not context.args:
        command = update.message.text.split()[0].lower()
        await update.message.reply_text(f"⚠️ Vui lòng nhập số tiền cược! Ví dụ: `{command} 10000`", parse_mode="Markdown")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền cược không hợp lệ!")
        return

    u = users_data[user_id]
    if u["balance"] < amount:
        await update.message.reply_text(f"❌ [{u['name']}]: Số dư ví không đủ `{amount:,}` điểm!", parse_mode="Markdown")
        return

    command = update.message.text.split()[0].lower()
    
    # Trừ tiền cược và lưu vào bộ đệm phiên
    u["balance"] -= amount
    
    if "tai" in command:
        choice = "TÀI (⚫)"
        current_bets["tai"][user_id] = current_bets["tai"].get(user_id, 0) + amount
    elif "xiu" in command:
        choice = "XỈU (⚪)"
        current_bets["xiu"][user_id] = current_bets["xiu"].get(user_id, 0) + amount
    elif "chan" in command:
        choice = "CHẴN (⚪)"
        current_bets["chan"][user_id] = current_bets["chan"].get(user_id, 0) + amount
    elif "le" in command:
        choice = "LẺ (⚫)"
        current_bets["le"][user_id] = current_bets["le"].get(user_id, 0) + amount
    else:
        u["balance"] += amount # Hoàn lại nếu lỗi lệnh
        return

    await update.message.reply_text(
        f"🎲 **{u['name']}** đã đặt **{amount:,}** điểm vào cửa **{choice}** thành công!\n"
        f"💰 Số dư còn lại: `{u['balance']:,}` điểm",
        parse_mode="Markdown"
    )

async def xem_lich_su(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not history_phien:
        await update.message.reply_text("📜 Chưa có lịch sử phiên cược nào gần đây.")
        return
    history_str = " ".join(history_phien[-15:])
    await update.message.reply_text(f"📜 **Lịch sử các phiên gần đây:**\n{history_str}", parse_mode="Markdown")


# =========================
# 8. VÒNG LẶP TỰ ĐỘNG 24/7
# =========================
async def auto_taixiu_loop(application):
    global phien_id, current_bets
    await asyncio.sleep(5)
    while True:
        try:
            # Reset dữ liệu cược đầu phiên mới
            current_bets = {"tai": {}, "xiu": {}, "chan": {}, "le": {}}

            if GROUP_CHAT_ID:
                history_str = " ".join(history_phien[-10:]) if history_phien else "Chưa có"
                
                # 1. Gửi thông báo mở phiên mới
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=(
                        f"📊 **PHIÊN #{phien_id}**\n\n"
                        f"📈 Lịch sử: {history_str}\n"
                        f"⏰ Chuẩn bị đặt cược trong 40 giây...\n\n"
                        f"👉 Cú pháp đặt cược:\n"
                        f"• `/tai [số_tiền]` (⚫ Tài)\n"
                        f"• `/xiu [số_tiền]` (⚪ Xỉu)\n"
                        f"• `/chan [số_tiền]` (⚪ Chẵn)\n"
                        f"• `/le [số_tiền]` (⚫ Lẻ)"
                    ),
                    parse_mode="Markdown"
                )
            
            # Chờ 40 giây đặt cược
            await asyncio.sleep(40)

            # Tính tổng tiền cược cửa Tài và Xỉu trước khi khóa sổ
            total_tai = sum(current_bets["tai"].values())
            total_xiu = sum(current_bets["xiu"].values())
            total_chan = sum(current_bets["chan"].values())
            total_le = sum(current_bets["le"].values())

            if GROUP_CHAT_ID:
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=(
                        f"🔒 **Đã khóa sổ! Tổng kết cược phiên #{phien_id}:**\n\n"
                        f"⚫ **Tổng Tài:** `{total_tai:,}` điểm\n"
                        f"⚪ **Tổng Xỉu:** `{total_xiu:,}` điểm\n"
                        f"⚪ Tổng Chẵn: `{total_chan:,}` điểm\n"
                        f"⚫ Tổng Lẻ: `{total_le:,}` điểm\n\n"
                        f"🎲 **Chuẩn bị tung xúc xắc...**"
                    ),
                    parse_mode="Markdown"
                )
            
            # Chờ ngắn tạo hiệu ứng hồi hộp
            await asyncio.sleep(2)

            # 2. Tung 3 xúc xắc bằng icon native của Telegram
            dice1 = await application.bot.send_dice(chat_id=GROUP_CHAT_ID)
            await asyncio.sleep(1)
            dice2 = await application.bot.send_dice(chat_id=GROUP_CHAT_ID)
            await asyncio.sleep(1)
            dice3 = await application.bot.send_dice(chat_id=GROUP_CHAT_ID)
            
            # Đợi xúc xắc lăn xong
            await asyncio.sleep(4)

            d1 = dice1.dice.value
            d2 = dice2.dice.value
            d3 = dice3.dice.value
            tong = d1 + d2 + d3

            ket_qua_tx = "TÀI (⚫)" if tong >= 11 else "XỈU (⚪)"
            ket_qua_cl = "CHẴN (⚪)" if tong % 2 == 0 else "LẺ (⚫)"
            
            # Cập nhật lịch sử
            icon_history = "⚪" if tong < 11 else "⚫"
            history_phien.append(icon_history)
            if len(history_phien) > 30:
                history_phien.pop(0)

            # Xử lý trả thưởng Tài / Xỉu
            winners_count = 0
            total_reward_paid = 0

            winning_tx_key = "tai" if tong >= 11 else "xiu"
            for uid, amount in current_bets[winning_tx_key].items():
                payout = amount * 2 # Hoàn vốn + thưởng 1:1
                if uid in users_data:
                    users_data[uid]["balance"] += payout
                winners_count += 1
                total_reward_paid += payout

            # Xử lý trả thưởng Chẵn / Lẻ
            winning_cl_key = "chan" if tong % 2 == 0 else "le"
            for uid, amount in current_bets[winning_cl_key].items():
                payout = amount * 2
                if uid in users_data:
                    users_data[uid]["balance"] += payout
                winners_count += 1
                total_reward_paid += payout

            if GROUP_CHAT_ID:
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=(
                        f"🎉 **KẾT QUẢ PHIÊN #{phien_id}**\n\n"
                        f"🎲 Xúc xắc: `{d1} - {d2} - {d3}`\n"
                        f"📌 Tổng điểm: **{tong} điểm**\n"
                        f"🏆 Kết quả: **{ket_qua_tx}** | **{ket_qua_cl}**\n\n"
                        f"👥 Số người thắng: **{winners_count} người**\n"
                        f"💰 Tổng tiền thưởng: `{total_reward_paid:,}` điểm"
                    ),
                    parse_mode="Markdown"
                )
                
            phien_id += 1
        except Exception as e:
            logging.error(f"Lỗi vòng lặp phiên: {e}")
            
        await asyncio.sleep(5)


# =========================
# 9. XỬ LÝ NÚT BẤM (CALLBACK)
# =========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("nap_click_"):
        parts = data.split("_")
        target_id = int(parts[2])
        amount = int(parts[3]) # Lấy chính xác số tiền khách nhập ở lệnh /nap
        u = users_data.get(target_id, {})
        
        admin_keyboard = [
            [
                InlineKeyboardButton(f"✅ Duyệt +{amount:,}", callback_data=f"nap_yes_{target_id}_{amount}"),
            ],
            [
                InlineKeyboardButton("❌ Từ chối", callback_data=f"nap_no_{target_id}")
            ]
        ]
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"🔔 **YÊU CẦU NẠP TIỀN MỚI**\n\n"
                f"👤 Khách: **{u.get('name')}**\n"
                f"🆔 ID: `{u.get('custom_id')}`\n"
                f"💰 Số tiền yêu cầu: `{amount:,}` VNĐ\n"
                f"📝 Nội dung CK: `NAP {u.get('name')} {u.get('custom_id')}`\n"
                f"👉 Kiểm tra ngân hàng và duyệt:"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(admin_keyboard)
        )
        await query.edit_message_text(text="✅ Đã gửi yêu cầu nạp cho hệ thống xử lý!")

    elif data.startswith("nap_yes_"):
        parts = data.split("_")
        target_id = int(parts[2])
        amount = int(parts[3])
        
        if target_id in users_data:
            users_data[target_id]["balance"] += amount # Cộng đúng số tiền khách yêu cầu nạp
            
        await query.edit_message_text(text=f"✅ Đã duyệt cộng chuẩn `{amount:,}` điểm cho khách!")
        try:
            await context.bot.send_message(chat_id=target_id, text=f"🎉 Nạp tiền thành công! Tài khoản được cộng chính xác `{amount:,}` điểm.", parse_mode="Markdown")
        except:
            pass

    elif data.startswith("nap_no_"):
        target_id = int(data.split("_")[2])
        await query.edit_message_text(text="❌ Đã từ chối giao dịch nạp.")
        try:
            await context.bot.send_message(chat_id=target_id, text="❌ Yêu cầu nạp tiền của bạn đã bị từ chối.")
        except:
            pass

    elif data.startswith("rut_yes_"):
        parts = data.split("_")
        target_id = int(parts[2])
        amount = int(parts[3])
        if target_id in users_data:
            users_data[target_id]["balance"] -= amount
        await query.edit_message_text(text="✅ Đã duyệt rút tiền thành công!")
        try:
            await context.bot.send_message(chat_id=target_id, text=f"🎉 Lệnh rút `{amount:,}` điểm đã được thanh toán thành công!")
        except:
            pass

    elif data.startswith("rut_no_"):
        target_id = int(data.split("_")[2])
        await query.edit_message_text(text="❌ Đã từ chối lệnh rút.")
        try:
            await context.bot.send_message(chat_id=target_id, text="❌ Yêu cầu rút điểm của bạn đã bị từ chối.")
        except:
            pass


# =========================
# 10. KHỞI CHẠY HỆ THỐNG
# =========================
def main():
    if not TOKEN:
        raise RuntimeError("Chưa cấu hình BOT_TOKEN.")

    # Chạy Web Server 24/7 trên Render
    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    # Đăng ký các lệnh hệ thống
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sd", check_sd))
    app.add_handler(CommandHandler("tk", check_sd))
    app.add_handler(CommandHandler("nap", menu_nap))
    app.add_handler(CommandHandler("rut", menu_rut))
    app.add_handler(CommandHandler("code", nhap_code))
    
    # Lệnh Admin
    app.add_handler(CommandHandler("taocode", tao_code))

    # Đăng ký lệnh chơi (Tài / Xỉu / Chẵn / Lẻ)
    app.add_handler(CommandHandler("tai", dat_cuoc))
    app.add_handler(CommandHandler("xiu", dat_cuoc))
    app.add_handler(CommandHandler("chan", dat_cuoc))
    app.add_handler(CommandHandler("le", dat_cuoc))
    app.add_handler(CommandHandler("ls", xem_lich_su))

    # Xử lý tin nhắn và nút bấm
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot Tài Xỉu & Chẵn Lẻ 24/7 đã khởi động thành công...")
    
    async def post_init(application):
        asyncio.create_task(auto_taixiu_loop(application))
        
    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
