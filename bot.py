import os
import json
import logging
import random
import asyncio
import threading
from datetime import datetime
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
# 2. CẤU HÌNH BOT & PHÂN QUYỀN (ADMIN / CSKH)
# =========================
TOKEN = os.getenv("BOT_TOKEN")  # Token của bot
MASTER_ADMIN_ID = 8013947246  # ID Telegram của Admin tối cao
GROUP_CHAT_ID = -1003932050774 # ID Nhóm đã cấu hình

sub_admins = set()       # Danh sách QTV phụ (có quyền tạo code,...)
cskh_staffs = set()      # Danh sách nhân viên CSKH

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

users_data = {}
gift_codes = {"VIP2026": 50000, "TET2026": 100000}
history_phien = [] 
phien_id = 1

current_bets = {
    "tai": {},  
    "xiu": {},  
    "chan": {}, 
    "le": {}    
}

BANK_LIST = [
    {"name": "MSB", "stk": "6314072009", "chủ tài khoản": "HỆ THỐNG TỰ ĐỘNG (ANONYMOUS)"},
    {"name": "MBBank", "stk": "0776876883", "chủ tài khoản": "HỆ THỐNG TỰ ĐỘNG (ANONYMOUS)"}
]

def is_admin(user_id):
    return user_id == MASTER_ADMIN_ID or user_id in sub_admins

def is_cskh(user_id):
    return user_id == MASTER_ADMIN_ID or user_id in cskh_staffs


# =========================
# 3. XỬ LÝ LỆNH START & MỜI BẠN BÈ
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    keyboard = [
        [InlineKeyboardButton("💬 Liên Hệ CSKH Hỗ Trợ", url="https://t.me/cskhtelevip")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message.chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            "🎲 **HỆ THỐNG TÀI XỈU & CHẴN LẺ VIP**\n\n"
            "📋 **Lệnh chơi tại nhóm (Min cược: 5,000):**\n"
            "• `/tai [số_tiền]` - Đặt cửa Tài (⚫)\n"
            "• `/xiu [số_tiền]` - Đặt cửa Xỉu (⚪)\n"
            "• `/chan [số_tiền]` - Đặt cửa Chẵn (⚪)\n"
            "• `/le [số_tiền]` - Đặt cửa Lẻ (⚫)\n"
            "• `/sd` hoặc `/tk` - Kiểm tra số dư ví\n"
            "• `/ls` - Xem lịch sử phiên gần đây\n"
            "• `/linkmoi` - Lấy link mời bạn bè nhận hoa hồng\n"
            "• `/topmoi` - Xem bảng xếp hạng mời bạn\n"
            "• `/hoantra` - Nhận tiền hoàn trả cược tích lũy",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return

    if user_id not in users_data or users_data[user_id].get("step") != "active":
        users_data[user_id] = {
            "step": "waiting_name",
            "custom_id": f"CUBE{random.randint(1000,9999)}",
            "balance": 0.0,
            "cashback_fund": 0.0,  # Quỹ hoàn trả cược
            "invited_count": 0,
            "referred_by": None,
            "history_action": []  # Lưu lịch sử nạp/rút/cược phục vụ CSKH
        }

        if context.args and context.args[0].startswith("ref_"):
            try:
                ref_id = int(context.args[0].replace("ref_", ""))
                if ref_id != user_id and ref_id in users_data:
                    users_data[user_id]["referred_by"] = ref_id
                    users_data[ref_id]["invited_count"] += 1
                    users_data[ref_id]["balance"] += 1000  
                    
                    try:
                        await context.bot.send_message(
                            chat_id=ref_id,
                            text=f"🎉 Chúc mừng! Bạn vừa mời thành công một thành viên mới và nhận được `1,000` điểm thưởng!",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
            except Exception as e:
                logging.error(f"Lỗi xử lý ref: {e}")

        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        users_data[user_id]["ref_link"] = ref_link

        await update.message.reply_text(
            f"👋 Chào mừng bạn đến với hệ thống giao dịch tự động!\n"
            f"🆔 ID định danh riêng của bạn: `{users_data[user_id]['custom_id']}`\n\n"
            f"⚠️ **BẮT BUỘC:** Vui lòng nhập **Họ và Tên chính xác trùng với Tài Khoản Ngân Hàng** của bạn:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return

    u = users_data[user_id]
    await send_main_menu(update, u, reply_markup)

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
        
        keyboard = [[InlineKeyboardButton("💬 Liên Hệ CSKH Hỗ Trợ", url="https://t.me/cskhtelevip")]]
        await update.message.reply_text(
            f"✅ Đăng ký tài khoản thành công!\n"
            f"📌 Tên chủ thẻ: **{text}**\n"
            f"🆔 ID của bạn: `{users_data[user_id]['custom_id']}`\n\n"
            f"Sử dụng các lệnh:\n"
            f"• `/sd` - Kiểm tra số dư\n"
            f"• `/linkmoi` - Lấy link giới thiệu bạn bè\n"
            f"• `/hoantra` - Nhận tiền hoàn trả cược\n"
            f"• `/nap [số_tiền]` - Nạp điểm (Min 30,000đ)\n"
            f"• `/rut [số_tiền] [STK] [Ngân hàng] [Chủ thẻ]` - Rút điểm",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

async def send_main_menu(update, u, reply_markup):
    await update.message.reply_text(
        f"👤 Tài khoản: **{u['name']}**\n"
        f"🆔 ID: `{u['custom_id']}`\n"
        f"💰 Số dư ví: `{u['balance']:,.0f}` điểm\n"
        f"🎁 Tiền hoàn trả tích lũy: `{u['cashback_fund']:,.0f}` điểm (Dùng `/hoantra` để nhận)\n"
        f"👥 Số bạn đã mời: `{u['invited_count']}` người\n\n"
        f"📋 Menu lệnh:\n"
        f"• `/sd` - Kiểm tra số dư\n"
        f"• `/linkmoi` - Lấy link mời bạn\n"
        f"• `/hoantra` - Nhận hoàn trả cược\n"
        f"• `/nap [số_tiền]` - Nạp điểm\n"
        f"• `/rut [số_tiền] [STK] [Ngân_hàng] [Chủ_thẻ]` - Rút điểm",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


# =========================
# 4. TÍNH NĂNG MỜI BẠN & HOÀN TRẢ CƯỢC (CASHBACK)
# =========================
async def link_moi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` ở tin nhắn riêng để lấy link!")
        return
    
    u = users_data[user_id]
    ref_link = u.get("ref_link", f"https://t.me/{context.bot.username}?start=ref_{user_id}")
    
    await update.message.reply_text(
        f"🔗 **LINK GIỚI THIỆU BẠN BÈ CỦA BẠN**\n\n"
        f"`{ref_link}`\n\n"
        f"📌 *Quyền lợi:* Mỗi khi có bạn bè đăng ký qua link, bạn nhận ngay **1,000 điểm** và tích lũy vào BXH tuần!",
        parse_mode="Markdown"
    )

async def top_moi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_users = sorted(users_data.items(), key=lambda x: x[1].get("invited_count", 0), reverse=True)
    text = "🏆 **BẢNG XẾP HẠNG TOP MỜI BẠN BÈ TUẦN** 🏆\n\n"
    medals = ["🥇", "🥈", "🥉", "🏅"]
    
    for i in range(min(10, len(sorted_users))):
        uid, data = sorted_users[i]
        if data.get("invited_count", 0) <= 0 and i >= 4:
            break
        medal = medals[i] if i < 4 else f"#{i+1}"
        name = data.get("name", "Ẩn danh")
        count = data.get("invited_count", 0)
        text += f"{medal} **{name}** — Mời được: `{count}` người\n"
        
    text += (
        "\n🎁 **CƠ CẤU GIẢI THƯỞNG TUẦN:**\n"
        "• **Top 1:** 200,000 điểm | **Top 2:** 100,000 điểm\n"
        "• **Top 3:** 50,000 điểm | **Top 4:** 20,000 điểm"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def nhan_hoantra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` để đăng ký tài khoản!")
        return

    u = users_data[user_id]
    amount = u.get("cashback_fund", 0.0)

    if amount < 1000:
        format_val = f"{amount:,.0f}"
        await update.message.reply_text(f"❌ Số tiền hoàn trả tích lũy hiện tại của bạn (`{format_val}` điểm) chưa đủ tối thiểu 1,000 điểm để rút về ví!", parse_mode="Markdown")
        return

    u["balance"] += amount
    u["cashback_fund"] = 0.0
    
    # Ghi nhận lịch sử cho CSKH
    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Nhận hoàn trả: +{amount:,.0f}đ")

    await update.message.reply_text(
        f"🎉 **NHẬN HOÀN TRẢ THÀNH CÔNG!**\n\n"
        f"💰 Đã chuyển cộng `{amount:,.0f}` điểm vào ví chính của bạn.",
        parse_mode="Markdown"
    )


# =========================
# 5. KIỂM TRA SỐ DƯ
# =========================
async def check_sd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if user_id not in users_data or users_data[user_id].get("step") != "active":
        keyboard = [[InlineKeyboardButton("💬 Liên Hệ CSKH Hỗ Trợ", url="https://t.me/cskhtelevip")]]
        await update.message.reply_text(
            f"⚠️ [{user.first_name}](tg://user?id={user_id}) bạn chưa đăng ký tài khoản! Hãy nhắn tin riêng cho Bot gõ `/start`.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    u = users_data[user_id]
    keyboard = [[InlineKeyboardButton("💬 Liên Hệ CSKH Hỗ Trợ", url="https://t.me/cskhtelevip")]]
    await update.message.reply_text(
        f"👤 Người chơi: [{user.first_name}](tg://user?id={user_id})\n"
        f"📌 Tên chủ thẻ: **{u['name']}**\n"
        f"🆔 ID định danh: `{u['custom_id']}`\n"
        f"💰 Số dư ví: `{u['balance']:,.0f}` điểm\n"
        f"🎁 Quỹ hoàn trả chưa nhận: `{u['cashback_fund']:,.0f}` điểm\n"
        f"👥 Đã giới thiệu: `{u['invited_count']}` bạn bè",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# 6. NẠP, RÚT & NHẬP CODE (TÍCH HỢP BÁO CƯỚC/NẠP/RÚT VỀ CSKH)
# =========================
async def gui_thong_bao_cskh(context: ContextTypes.DEFAULT_TYPE, message_text: str):
    """Gửi cảnh báo/thông báo giao dịch Nạp, Rút, Cược về cho toàn bộ nhân viên CSKH & Admin"""
    targets = {MASTER_ADMIN_ID} | sub_admins | cskh_staffs
    for staff_id in targets:
        try:
            await context.bot.send_message(chat_id=staff_id, text=message_text, parse_mode="Markdown")
        except:
            pass

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
        f"⚠️️ Chuyển khoản xong hãy bấm nút bên dưới để báo duyệt!"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Đã Chuyển Khoản, Báo Duyệt Ngay", callback_data=f"nap_click_{user_id}_{amount}")],
        [InlineKeyboardButton("💬 Liên Hệ CSKH Hỗ Trợ", url="https://t.me/cskhtelevip")]
    ]
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

    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Yêu cầu rút: -{amount:,}đ về STK {stk}")

    # Gửi báo cáo về cho hệ thống CSKH và Quản trị viên
    await gui_thong_bao_cskh(
        context,
        f"🔔 **YÊU CẦU RÚT TIỀN MỚI**\n\n"
        f"👤 Khách: **{u['name']}**\n"
        f"🆔 ID: `{u['custom_id']}` (Tele ID: `{user_id}`)\n"
        f"💰 Số tiền: `{amount:,}` điểm\n"
        f"📌 STK: `{stk}` | Ngân hàng: `{ngan_hang}` | Chủ thẻ: `{chu_the}`"
    )

    await update.message.reply_text("⏳ Yêu cầu rút tiền đã được gửi tới hệ thống CSKH & Quản trị viên xử lý!")

async def nhap_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` để đăng ký trước khi nhập code!")
        return

    if not context.args:
        await update.message.reply_text("⚠ Vui lòng nhập mã code! Ví dụ: `/code VIP2026`", parse_mode="Markdown")
        return

    code = context.args[0].strip().upper()
    if code in gift_codes:
        reward = gift_codes[code]
        users_data[user_id]["balance"] += reward
        del gift_codes[code]
        users_data[user_id]["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Nhận Code {code}: +{reward:,}đ")
        await update.message.reply_text(f"🎉 Nhận mã thành công! Đã cộng thêm `{reward:,}` điểm vào ví.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Mã code không tồn tại hoặc đã được sử dụng!")


# =========================
# 7. QUẢN LÝ QUYỀN (QTV & CSKH) & CÔNG CỤ CSKH
# =========================
async def tao_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền tạo code! Chỉ QTV (Admin/Mod) mới thực hiện được.")
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
        f"✅ Tạo mã thành công bởi QTV!\n🎁 Mã: `{code_name}`\n💰 Giá trị: `{amount:,}` điểm",
        parse_mode="Markdown"
    )

async def them_cskh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != MASTER_ADMIN_ID:
        await update.message.reply_text("⛔ Chỉ có Admin tối cao mới có quyền thêm nhân viên CSKH!")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Sai cú pháp! Dùng: `/themcskh [user_id]`", parse_mode="Markdown")
        return

    try:
        staff_id = int(context.args[0])
        cskh_staffs.add(staff_id)
        await update.message.reply_text(f"✅ Đã cấp quyền CSKH thành công cho User ID: `{staff_id}`", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=staff_id, text="🎉 Bạn đã được phân quyền nhân viên **CSKH** hệ thống!")
        except:
            pass
    except ValueError:
        await update.message.reply_text("⚠️ User ID không hợp lệ!")

async def xoa_cskh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != MASTER_ADMIN_ID:
        await update.message.reply_text("⛔ Chỉ có Admin tối cao mới có quyền thu hồi quyền CSKH!")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Sai cú pháp! Dùng: `/xoacskh [user_id]`", parse_mode="Markdown")
        return

    try:
        staff_id = int(context.args[0])
        if staff_id in cskh_staffs:
            cskh_staffs.remove(staff_id)
            await update.message.reply_text(f"✅ Đã thu hồi quyền CSKH của User ID: `{staff_id}`", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ User ID này không nằm trong danh sách CSKH!")
    except ValueError:
        await update.message.reply_text("⚠️ User ID không hợp lệ!")

async def them_mod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != MASTER_ADMIN_ID:
        await update.message.reply_text("⛔ Chỉ có Admin tối cao mới có quyền cấp quyền QTV (Mod)!")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Dùng: `/themmod [user_id]`", parse_mode="Markdown")
        return
    try:
        mod_id = int(context.args[0])
        sub_admins.add(mod_id)
        await update.message.reply_text(f"✅ Đã cấp quyền QTV (Mod) thành công cho User ID: `{mod_id}`")
    except ValueError:
        await update.message.reply_text("⚠️ ID không hợp lệ!")

# Lệnh CSKH kiểm tra tài khoản người chơi thông qua ID
async def check_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_cskh(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền truy cập tính năng CSKH này!")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Dùng: `/checkid [Custom_ID hoặc Telegram_ID]`\nVí dụ: `/checkid CUBE1234` hoặc `/checkid 8013947246`", parse_mode="Markdown")
        return

    query_key = context.args[0].strip()
    target_uid = None
    target_data = None

    # Tìm theo Telegram ID hoặc Custom ID
    for uid, data in users_data.items():
        if str(uid) == query_key or data.get("custom_id") == query_key.upper():
            target_uid = uid
            target_data = data
            break

    if not target_data:
        await update.message.reply_text("❌ Không tìm thấy thông tin người chơi khớp với ID này trong hệ thống!")
        return

    history_snippet = "\n".join(target_data["history_action"][-10:]) if target_data["history_action"] else "Chưa có hoạt động"

    await update.message.reply_text(
        f"🔍 **THÔNG TIN TÀI KHOẢN (CSKH TRA CỨU)**\n\n"
        f"• Telegram ID: `{target_uid}`\n"
        f"• Mã định danh: `{target_data['custom_id']}`\n"
        f"• Họ và Tên: **{target_data.get('name', 'Chưa đặt')}**\n"
        f"• Số dư ví chính: `{target_data['balance']:,.0f}` điểm\n"
        f"• Quỹ hoàn trả: `{target_data['cashback_fund']:,.0f}` điểm\n"
        f"• Đã mời: `{target_data['invited_count']}` bạn bè\n\n"
        f"📜 **10 Hoạt động / Lịch sử gần đây:**\n{history_snippet}",
        parse_mode="Markdown"
    )

# Lệnh CSKH thay đổi thông tin người chơi
async def sua_tt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_cskh(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền CSKH để thay đổi thông tin người chơi!")
        return

    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ Sai cú pháp! Dùng:\n"
            "`/suatt [Telegram_ID] [thuộc_tính] [giá_trị_mới]`\n"
            "Thuộc tính hỗ trợ: `balance`, `name`, `cashback`\n"
            "Ví dụ: `/suatt 8013947246 balance 500000`",
            parse_mode="Markdown"
        )
        return

    try:
        target_uid = int(context.args[0])
        prop = context.args[1].lower()
        val_str = context.args[2]
    except ValueError:
        await update.message.reply_text("⚠️ Định dạng tham số không hợp lệ!")
        return

    if target_uid not in users_data:
        await update.message.reply_text("❌ Không tìm thấy User ID này!")
        return

    u = users_data[target_uid]

    if prop == "balance":
        old_val = u["balance"]
        u["balance"] = float(val_str)
        u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] CSKH đổi số dư từ {old_val:,.0f} thành {float(val_str):,.0f}")
        await update.message.reply_text(f"✅ Đã đổi số dư của User `{target_uid}` thành `{float(val_str):,.0f}` điểm!")
    elif prop == "name":
        new_name = " ".join(context.args[2:])
        u["name"] = new_name
        u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] CSKH đổi tên thành {new_name}")
        await update.message.reply_text(f"✅ Đã đổi tên chủ thẻ thành: **{new_name}**", parse_mode="Markdown")
    elif prop == "cashback":
        u["cashback_fund"] = float(val_str)
        await update.message.reply_text(f"✅ Đã cập nhật quỹ hoàn trả thành `{float(val_str):,.0f}` điểm!")
    else:
        await update.message.reply_text("❌ Thuộc tính không hợp lệ! Chỉ hỗ trợ: `balance`, `name`, `cashback`")


# =========================
# 8. ĐẶT CƯỢC TÀI / XỈU / CHẴN / LẺ (MIN 5,000 & HOÀN TRẢ TỰ ĐỘNG)
# =========================
async def dat_cuoc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if user_id not in users_data or users_data[user_id].get("step") != "active":
        keyboard = [[InlineKeyboardButton("💬 Liên Hệ CSKH Hỗ Trợ", url="https://t.me/cskhtelevip")]]
        await update.message.reply_text(
            f"⚠️ [{user.first_name}](tg://user?id={user_id}) bạn chưa đăng ký tài khoản! Gõ `/start` ở tin nhắn riêng.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    if not context.args:
        command = update.message.text.split()[0].lower()
        await update.message.reply_text(f"⚠️ Vui lòng nhập số tiền cược! Min cược: `5,000`\nVí dụ: `{command} 10000`", parse_mode="Markdown")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền cược không hợp lệ!")
        return

    if amount < 5000:
        await update.message.reply_text("❌ Mức cược tối thiểu là **5,000** điểm!", parse_mode="Markdown")
        return

    u = users_data[user_id]
    if u["balance"] < amount:
        await update.message.reply_text(f"❌ [{u['name']}]: Số dư ví không đủ `{amount:,}` điểm!", parse_mode="Markdown")
        return

    command = update.message.text.split()[0].lower()
    u["balance"] -= amount
    
    # 🌟 CƠ CHẾ HOÀN TRẢ CƯỢC QUỐC TẾ (Tỷ lệ hoàn trả: 0.8% tiền cược)
    cashback_rate = 0.008 
    earned_cashback = amount * cashback_rate
    u["cashback_fund"] += earned_cashback

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
        u["balance"] += amount
        u["cashback_fund"] -= earned_cashback
        return

    # Ghi nhận lịch sử cược phục vụ CSKH
    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Cược {amount:,} vào {choice}")

    # Gửi thông báo cược về cho CSKH theo dõi thời gian thực
    await gui_thong_bao_cskh(
        context,
        f"📊 **THÔNG TIN CƯỢC MỚI**\n"
        f"• Khách: **{u['name']}** (ID: `{u['custom_id']}`)\n"
        f"• Cửa: `{choice}` — Tiền cược: `{amount:,}` điểm"
    )

    await update.message.reply_text(
        f"🎲 **{u['name']}** đặt thành công **{amount:,}** vào **{choice}**!\n"
        f"🎁 Đã tích lũy `+{earned_cashback:,.1f}` điểm vào quỹ hoàn trả.\n"
        f"💰 Số dư còn lại: `{u['balance']:,.0f}` điểm",
        parse_mode="Markdown"
    )

async def xem_lich_su(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not history_phien:
        await update.message.reply_text("📜 Chưa có lịch sử phiên cược nào gần đây.")
        return
    history_str = " ".join(history_phien[-15:])
    await update.message.reply_text(f"📜 **Lịch sử các phiên gần đây:**\n{history_str}", parse_mode="Markdown")


# =========================
# 9. VÒNG LẶP TỰ ĐỘNG PHIÊN CƯỢC 24/7
# =========================
async def auto_taixiu_loop(application):
    global phien_id, current_bets
    await asyncio.sleep(5)
    while True:
        try:
            current_bets = {"tai": {}, "xiu": {}, "chan": {}, "le": {}}

            if GROUP_CHAT_ID:
                history_str = " ".join(history_phien[-10:]) if history_phien else "Chưa có"
                
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=(
                        f"📊 **PHIÊN #{phien_id}**\n\n"
                        f"📈 Lịch sử: {history_str}\n"
                        f"⏰ Đặt cược trong 40 giây...\n"
                        f"⚠ **Min cược: 5,000 điểm** | *Tự động hoàn trả 0.8% mỗi cược!*\n\n"
                        f"👉 Cú pháp:\n"
                        f"• `/tai [số_tiền]` | `/xiu [số_tiền]`\n"
                        f"• `/chan [số_tiền]` | `/le [số_tiền]`"
                    ),
                    parse_mode="Markdown"
                )
            
            await asyncio.sleep(40)

            total_tai = sum(current_bets["tai"].values())
            total_xiu = sum(current_bets["xiu"].values())
            total_chan = sum(current_bets["chan"].values())
            total_le = sum(current_bets["le"].values())

            if GROUP_CHAT_ID:
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=(
                        f"🔒 **Khóa sổ phiên #{phien_id}:**\n"
                        f"⚫ Tài: `{total_tai:,}` | ⚪ Xỉu: `{total_xiu:,}`\n"
                        f"⚪ Chẵn: `{total_chan:,}` | ⚫ Lẻ: `{total_le:,}`\n\n"
                        f"🎲 **Đang tung xúc xắc...**"
                    ),
                    parse_mode="Markdown"
                )
            
            try:
                await application.bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
                await asyncio.sleep(0.5)
                await application.bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
                await asyncio.sleep(0.5)
                await application.bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
            except Exception as e:
                logging.error(f"Lỗi ném xúc xắc: {e}")

            await asyncio.sleep(4)

            d1 = random.randint(1, 6)
            d2 = random.randint(1, 6)
            d3 = random.randint(1, 6)

            tong = d1 + d2 + d3
            ket_qua_tx = "TÀI (⚫)" if tong >= 11 else "XỈU (⚪)"
            ket_qua_cl = "CHẴN (⚪)" if tong % 2 == 0 else "LẺ (⚫)"
            
            icon_history = "⚫" if tong >= 11 else "⚪"
            history_phien.append(icon_history)
            if len(history_phien) > 30:
                history_phien.pop(0)

            winners_count = 0
            total_reward_paid = 0

            winning_tx_key = "tai" if tong >= 11 else "xiu"
            for uid, amount in current_bets[winning_tx_key].items():
                payout = amount * 2 
                if uid in users_data:
                    users_data[uid]["balance"] += payout
                    users_data[uid]["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thắng phiên #{phien_id}: +{payout:,}đ")
                winners_count += 1
                total_reward_paid += payout

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
                        f"🎲 Xúc xắc: `{d1} - {d2} - {d3}` (Tổng: **{tong}**)\n"
                        f"🏆 Kết quả: **{ket_qua_tx}** | **{ket_qua_cl}**\n\n"
                        f"👥 Thắng: `{winners_count}` người | Thưởng: `{total_reward_paid:,}` điểm"
                    ),
                    parse_mode="Markdown"
                )
                
            phien_id += 1
        except Exception as e:
            logging.error(f"Lỗi vòng lặp phiên: {e}")
            
        await asyncio.sleep(5)


# =========================
# 10. XỬ LÝ NÚT BẤM CALLBACK
# =========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("nap_click_"):
        parts = data.split("_")
        target_id = int(parts[2])
        amount = int(parts[3])
        u = users_data.get(target_id, {})
        
        admin_keyboard = [
            [InlineKeyboardButton(f"✅ Duyệt +{amount:,}", callback_data=f"nap_yes_{target_id}_{amount}")],
            [InlineKeyboardButton("❌ Từ chối", callback_data=f"nap_no_{target_id}")]
        ]
        
        await gui_thong_bao_cskh(
            context,
            f"🔔 **YÊU CẦU NẠP TIỀN MỚI**\n\n"
            f"👤 Khách: **{u.get('name')}** (ID: `{u.get('custom_id')}`)\n"
            f"💰 Số tiền: `{amount:,}` VNĐ\n"
            f"📝 Nội dung CK: `NAP {u.get('name')} {u.get('custom_id')}`"
        )

        # Gửi thêm các nút duyệt tới admin/cskh
        targets = {MASTER_ADMIN_ID} | sub_admins | cskh_staffs
        for adm in targets:
            try:
                await context.bot.send_message(
                    chat_id=adm,
                    text=f"Bảng điều khiển duyệt nạp cho khách **{u.get('name')}** (`{amount:,}đ`):",
                    reply_markup=InlineKeyboardMarkup(admin_keyboard)
                )
            except:
                pass

        await query.edit_message_text(text="✅ Đã gửi yêu cầu nạp cho hệ thống CSKH & Quản trị viên xử lý!")

    elif data.startswith("nap_yes_"):
        if not is_admin(user_id) and not is_cskh(user_id):
            await query.answer("⛔ Bạn không có quyền!", show_alert=True)
            return

        parts = data.split("_")
        target_id = int(parts[2])
        amount = int(parts[3])
        
        if target_id in users_data:
            users_data[target_id]["balance"] += amount
            users_data[target_id]["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Nạp thành công: +{amount:,}đ")
            
        await query.edit_message_text(text=f"✅ Đã duyệt cộng chính xác `{amount:,}` điểm cho khách!")
        try:
            await context.bot.send_message(chat_id=target_id, text=f"🎉 Nạp tiền thành công! Tài khoản được cộng chính xác `{amount:,}` điểm.", parse_mode="Markdown")
        except:
            pass

    elif data.startswith("nap_no_"):
        if not is_admin(user_id) and not is_cskh(user_id):
            await query.answer("⛔ Bạn không có quyền!", show_alert=True)
            return

        target_id = int(data.split("_")[2])
        await query.edit_message_text(text="❌ Đã từ chối giao dịch nạp.")
        try:
            await context.bot.send_message(chat_id=target_id, text="❌ Yêu cầu nạp tiền của bạn đã bị từ chối.")
        except:
            pass

    elif data.startswith("rut_yes_"):
        if not is_admin(user_id) and not is_cskh(user_id):
            await query.answer("⛔ Bạn không có quyền!", show_alert=True)
            return

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
        if not is_admin(user_id) and not is_cskh(user_id):
            await query.answer("⛔ Bạn không có quyền!", show_alert=True)
            return

        target_id = int(data.split("_")[2])
        await query.edit_message_text(text="❌ Đã từ chối lệnh rút.")
        try:
            await context.bot.send_message(chat_id=target_id, text="❌ Yêu cầu rút điểm của bạn đã bị từ chối.")
        except:
            pass


# =========================
# 11. KHỞI CHẠY HỆ THỐNG
# =========================
def main():
    if not TOKEN:
        raise RuntimeError("Chưa cấu hình BOT_TOKEN.")

    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    # Người chơi & Tiện ích chung
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["sd", "tk"], check_sd))
    app.add_handler(CommandHandler("linkmoi", link_moi))
    app.add_handler(CommandHandler("topmoi", top_moi))
    app.add_handler(CommandHandler("hoantra", nhan_hoantra))
    app.add_handler(CommandHandler("nap", menu_nap))
    app.add_handler(CommandHandler("rut", menu_rut))
    app.add_handler(CommandHandler("code", nhap_code))
    
    # Quyền QTV & CSKH
    app.add_handler(CommandHandler("taocode", tao_code))
    app.add_handler(CommandHandler("themmod", them_mod))
    app.add_handler(CommandHandler("themcskh", them_cskh))
    app.add_handler(CommandHandler("xoacskh", xoa_cskh))
    app.add_handler(CommandHandler("checkid", check_id))
    app.add_handler(CommandHandler("suatt", sua_tt))

    # Cược Tài Xỉu / Chẵn Lẻ
    app.add_handler(CommandHandler("tai", dat_cuoc))
    app.add_handler(CommandHandler("xiu", dat_cuoc))
    app.add_handler(CommandHandler("chan", dat_cuoc))
    app.add_handler(CommandHandler("le", dat_cuoc))
    app.add_handler(CommandHandler("ls", xem_lich_su))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot Tài Xỉu & Chẵn Lẻ VIP đã khởi động thành công với đầy đủ tính năng CSKH & Hoàn trả...")
    
    async def post_init(application):
        asyncio.create_task(auto_taixiu_loop(application))
        
    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
