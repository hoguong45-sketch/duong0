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
# 2. CẤU HÌNH BOT & PHÂN QUYỀN
# =========================
TOKEN = os.getenv("BOT_TOKEN")  # Token của bot
MASTER_ADMIN_ID = 8013947246  # ID Telegram của Admin tối cao
GROUP_CHAT_ID = -1003932050774 # ID Nhóm đã cấu hình

sub_admins = set()       # QTV phụ
cskh_staffs = set()      # Nhân viên CSKH

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
# 3. XỬ LÝ LỆNH START & MENU PHÂN QUYỀN
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    # Tạo menu bàn phím mặc định cho người chơi
    keyboard = [
        [InlineKeyboardButton("💬 Liên Hệ CSKH Hỗ Trợ", url="https://t.me/cskhtelevip")]
    ]

    # Nếu người dùng là QTV (Admin/Mod), bổ sung thêm bảng điều khiển QTV
    if is_admin(user_id):
        keyboard.insert(0, [InlineKeyboardButton("🛠 [QTV] Tạo Code Thưởng (/taocode)", callback_data="admin_help_code")])
        keyboard.insert(1, [InlineKeyboardButton("👥 [QTV] Thêm/Xóa Mod/CSKH", callback_data="admin_help_staff")])

    # Nếu người dùng là CSKH, bổ sung menu CSKH
    elif is_cskh(user_id):
        keyboard.insert(0, [InlineKeyboardButton("🔍 [CSKH] Kiểm tra ID (/checkid)", callback_data="cskh_help_check")])
        keyboard.insert(1, [InlineKeyboardButton("✏️ [CSKH] Sửa thông tin (/suatt)", callback_data="cskh_help_sua")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message.chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            "🎲 **HỆ THỐNG TÀI XỈU & CHẴN LẺ VIP**\n\n"
            "📋 **Lệnh chơi tại nhóm (Min cược: 5,000):**\n"
            "• `/tai [số_tiền]` | `/xiu [số_tiền]`\n"
            "• `/chan [số_tiền]` | `/le [số_tiền]`\n"
            "• `/sd` - Kiểm tra ví | `/ls` - Xem lịch sử\n"
            "• `/linkmoi` - Lấy link mời bạn | `/topmoi` - Xem BXH\n"
            "• `/hoantra` - Nhận tiền hoàn trả cược (0.8%)",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return

    if user_id not in users_data or users_data[user_id].get("step") != "active":
        users_data[user_id] = {
            "step": "waiting_name",
            "custom_id": f"CUBE{random.randint(1000,9999)}",
            "balance": 0.0,
            "cashback_fund": 0.0,
            "invited_count": 0,
            "referred_by": None,
            "history_action": []
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
                            text=f"🎉 Chúc mừng! Bạn vừa mời thành công thành viên mới và nhận `1,000` điểm!",
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
            f"🆔 ID định danh riêng: `{users_data[user_id]['custom_id']}`\n\n"
            f"⚠️ **BẮT BUỘC:** Vui lòng nhập **Họ và Tên trùng với Tài Khoản Ngân Hàng**:",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return

    u = users_data[user_id]
    await send_main_menu(update, u, reply_markup, user_id)

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
            f"• `/linkmoi` - Lấy link giới thiệu\n"
            f"• `/hoantra` - Nhận hoàn trả\n"
            f"• `/nap [số_tiền]` | `/rut [số_tiền] [STK] [Ngân hàng] [Chủ thẻ]`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

async def send_main_menu(update, u, reply_markup, user_id):
    role_text = "👤 Thành viên"
    if user_id == MASTER_ADMIN_ID:
        role_text = "👑 Admin Tối Cao"
    elif user_id in sub_admins:
        role_text = "🛠 Quản Trị Viên (QTV)"
    elif user_id in cskh_staffs:
        role_text = "🎧 Nhân Viên CSKH"

    await update.message.reply_text(
        f"🌟 Vai trò: **{role_text}**\n"
        f"👤 Tài khoản: **{u['name']}**\n"
        f"🆔 ID: `{u['custom_id']}`\n"
        f"💰 Số dư ví: `{u['balance']:,.0f}` điểm\n"
        f"🎁 Quỹ hoàn trả: `{u['cashback_fund']:,.0f}` điểm (Dùng `/hoantra`)\n"
        f"👥 Đã mời: `{u['invited_count']}` người\n\n"
        f"📋 Menu tính năng chính:\n"
        f"• `/sd` - Kiểm tra số dư\n"
        f"• `/linkmoi` - Link mời bạn bè\n"
        f"• `/topmoi` - BXH mời bạn\n"
        f"• `/hoantra` - Nhận hoàn trả 0.8%\n"
        f"• `/nap [số_tiền]` - Nạp điểm\n"
        f"• `/rut [số_tiền] [STK] [Ngân_hàng] [Chủ_thẻ]` - Rút điểm",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


# =========================
# 4. MỜI BẠN & HOÀN TRẢ
# =========================
async def link_moi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` ở tin nhắn riêng!")
        return
    u = users_data[user_id]
    ref_link = u.get("ref_link", f"https://t.me/{context.bot.username}?start=ref_{user_id}")
    await update.message.reply_text(f"🔗 **LINK GIỚI THIỆU CỦA BẠN:**\n\n`{ref_link}`", parse_mode="Markdown")

async def top_moi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_users = sorted(users_data.items(), key=lambda x: x[1].get("invited_count", 0), reverse=True)
    text = "🏆 **BẢNG XẾP HẠNG TOP MỜI BẠN** 🏆\n\n"
    medals = ["🥇", "🥈", "🥉", "🏅"]
    for i in range(min(10, len(sorted_users))):
        uid, data = sorted_users[i]
        if data.get("invited_count", 0) <= 0 and i >= 4:
            break
        medal = medals[i] if i < 4 else f"#{i+1}"
        text += f"{medal} **{data.get('name', 'Ẩn danh')}** — `{data.get('invited_count', 0)}` người\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def nhan_hoantra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` để đăng ký!")
        return
    u = users_data[user_id]
    amount = u.get("cashback_fund", 0.0)
    if amount < 1000:
        await update.message.reply_text(f"❌ Quỹ hoàn trả (`{amount:,.0f}` điểm) chưa đạt tối thiểu 1,000 điểm!", parse_mode="Markdown")
        return
    u["balance"] += amount
    u["cashback_fund"] = 0.0
    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Nhận hoàn trả: +{amount:,.0f}đ")
    await update.message.reply_text(f"🎉 Nhận hoàn trả thành công! Đã cộng `{amount:,.0f}` điểm vào ví chính.", parse_mode="Markdown")


# =========================
# 5. KIỂM TRA SỐ DƯ
# =========================
async def check_sd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Bạn chưa đăng ký tài khoản! Hãy nhắn tin riêng cho Bot gõ `/start`.", parse_mode="Markdown")
        return
    u = users_data[user_id]
    await update.message.reply_text(
        f"👤 Tên: **{u['name']}** | ID: `{u['custom_id']}`\n"
        f"💰 Số dư: `{u['balance']:,.0f}` điểm\n"
        f"🎁 Hoàn trả: `{u['cashback_fund']:,.0f}` điểm\n"
        f"👥 Đã mời: `{u['invited_count']}` người",
        parse_mode="Markdown"
    )


# =========================
# 6. NẠP, RÚT & NHẬP CODE
# =========================
async def gui_thong_bao_cskh(context: ContextTypes.DEFAULT_TYPE, message_text: str):
    targets = {MASTER_ADMIN_ID} | sub_admins | cskh_staffs
    for staff_id in targets:
        try:
            await context.bot.send_message(chat_id=staff_id, text=message_text, parse_mode="Markdown")
        except:
            pass

async def menu_nap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` ở tin nhắn riêng trước!")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Dùng: `/nap [số_tiền]` (Min: 30,000)", parse_mode="Markdown")
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền không hợp lệ!")
        return
    if amount < 30000:
        await update.message.reply_text("❌ Nạp tối thiểu **30,000** điểm!", parse_mode="Markdown")
        return

    u = users_data[user_id]
    bank = random.choice(BANK_LIST)
    nap_text = (
        f"💳 **HƯỚNG DẪN NẠP ĐIỂM**\n"
        f"🏦 Ngân hàng: *{bank['name']}* | STK: `{bank['stk']}`\n"
        f"👤 Chủ TK: *{bank['chủ tài khoản']}*\n"
        f"💰 Số tiền: `{amount:,}` VNĐ\n"
        f"📝 Nội dung CK: `NAP {u['name']} {u['custom_id']}`\n\n"
        f"⚠️ Chuyển khoản xong bấm nút bên dưới báo duyệt!"
    )
    keyboard = [[InlineKeyboardButton("✅ Đã Chuyển Khoản, Báo Duyệt", callback_data=f"nap_click_{user_id}_{amount}")]]
    await update.message.reply_text(nap_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def menu_rut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` trước!")
        return
    if not context.args or len(context.args) < 4:
        await update.message.reply_text("⚠️ Dùng: `/rut [số_tiền] [STK] [Ngân_hàng] [Tên_chủ_thẻ]`", parse_mode="Markdown")
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền không hợp lệ!")
        return
    if amount < 70000:
        await update.message.reply_text("❌ Rút tối thiểu **70,000** điểm!", parse_mode="Markdown")
        return

    stk, ngan_hang, chu_the = context.args[1], context.args[2], " ".join(context.args[3:])
    u = users_data[user_id]
    if u["balance"] < amount:
        await update.message.reply_text("❌ Số dư không đủ!")
        return

    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Yêu cầu rút: -{amount:,}đ")
    await gui_thong_bao_cskh(
        context,
        f"🔔 **YÊU CẦU RÚT TIỀN MỚI**\n"
        f"👤 Khách: **{u['name']}** (`{u['custom_id']}`)\n"
        f"💰 Số tiền: `{amount:,}` | STK: `{stk}` | `{ngan_hang}` | `{chu_the}`"
    )
    await update.message.reply_text("⏳ Yêu cầu rút tiền đã được gửi tới CSKH & Quản trị viên!")

async def nhap_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Gõ `/start` trước khi nhập code!")
        return
    if not context.args:
        await update.message.reply_text("⚠️️ Dùng: `/code [MÃ]`", parse_mode="Markdown")
        return
    code = context.args[0].strip().upper()
    if code in gift_codes:
        reward = gift_codes[code]
        users_data[user_id]["balance"] += reward
        del gift_codes[code]
        users_data[user_id]["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Nhận Code {code}: +{reward:,}đ")
        await update.message.reply_text(f"🎉 Nhận mã thành công! Cộng thêm `{reward:,}` điểm.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Mã code không tồn tại hoặc đã được dùng!")


# =========================
# 7. CÔNG CỤ QTV & CSKH
# =========================
async def tao_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền tạo code!")
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠️ Dùng: `/taocode [MÃ] [số_tiền]`", parse_mode="Markdown")
        return
    code_name = context.args[0].strip().upper()
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ Tiền thưởng không hợp lệ!")
        return
    gift_codes[code_name] = amount
    await update.message.reply_text(f"✅ Tạo mã thành công!\n🎁 Mã: `{code_name}` | Trị giá: `{amount:,}` điểm", parse_mode="Markdown")

async def them_cskh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MASTER_ADMIN_ID:
        await update.message.reply_text("⛔ Chỉ Admin tối cao mới có quyền!")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Dùng: `/themcskh [user_id]`", parse_mode="Markdown")
        return
    try:
        staff_id = int(context.args[0])
        cskh_staffs.add(staff_id)
        await update.message.reply_text(f"✅ Đã cấp quyền CSKH cho ID: `{staff_id}`")
    except ValueError:
        await update.message.reply_text("⚠️️ ID không hợp lệ!")

async def xoa_cskh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MASTER_ADMIN_ID:
        await update.message.reply_text("⛔ Chỉ Admin tối cao mới có quyền!")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Dùng: `/xoacskh [user_id]`", parse_mode="Markdown")
        return
    try:
        staff_id = int(context.args[0])
        if staff_id in cskh_staffs:
            cskh_staffs.remove(staff_id)
            await update.message.reply_text(f"✅ Đã thu hồi quyền CSKH của ID: `{staff_id}`")
        else:
            await update.message.reply_text("⚠️ ID không có trong danh sách CSKH!")
    except ValueError:
        await update.message.reply_text("⚠️ ID không hợp lệ!")

async def them_mod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MASTER_ADMIN_ID:
        await update.message.reply_text("⛔ Chỉ Admin tối cao mới có quyền!")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Dùng: `/themmod [user_id]`", parse_mode="Markdown")
        return
    try:
        mod_id = int(context.args[0])
        sub_admins.add(mod_id)
        await update.message.reply_text(f"✅ Đã cấp quyền QTV cho ID: `{mod_id}`")
    except ValueError:
        await update.message.reply_text("⚠️ ID không hợp lệ!")

async def check_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_cskh(update.effective_user.id):
        await update.message.reply_text("⛔ Bạn không có quyền CSKH!")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Dùng: `/checkid [Custom_ID hoặc Telegram_ID]`", parse_mode="Markdown")
        return
    query_key = context.args[0].strip()
    target_data = None
    for uid, data in users_data.items():
        if str(uid) == query_key or data.get("custom_id") == query_key.upper():
            target_data = data
            break
    if not target_data:
        await update.message.reply_text("❌ Không tìm thấy người chơi!")
        return
    history_snippet = "\n".join(target_data["history_action"][-10:]) if target_data["history_action"] else "Chưa có"
    await update.message.reply_text(
        f"🔍 **THÔNG TIN TÀI KHOẢN**\n"
        f"• Tên: **{target_data.get('name')}** | ID: `{target_data['custom_id']}`\n"
        f"• Số dư: `{target_data['balance']:,.0f}` | Hoàn trả: `{target_data['cashback_fund']:,.0f}`\n"
        f"📜 **Lịch sử gần đây:**\n{history_snippet}",
        parse_mode="Markdown"
    )

async def sua_tt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_cskh(update.effective_user.id):
        await update.message.reply_text("⛔ Bạn không có quyền CSKH!")
        return
    if not context.args or len(context.args) < 3:
        await update.message.reply_text("⚠️ Dùng: `/suatt [Telegram_ID] [balance/name/cashback] [giá_trị]`", parse_mode="Markdown")
        return
    try:
        target_uid = int(context.args[0])
        prop = context.args[1].lower()
        val_str = context.args[2]
    except ValueError:
        await update.message.reply_text("⚠️ Sai định dạng tham số!")
        return
    if target_uid not in users_data:
        await update.message.reply_text("❌ Không tìm thấy User ID!")
        return
    u = users_data[target_uid]
    if prop == "balance":
        u["balance"] = float(val_str)
        await update.message.reply_text(f"✅ Đã đổi số dư thành `{float(val_str):,.0f}` điểm!")
    elif prop == "name":
        u["name"] = " ".join(context.args[2:])
        await update.message.reply_text(f"✅ Đã đổi tên thành: **{u['name']}**", parse_mode="Markdown")
    elif prop == "cashback":
        u["cashback_fund"] = float(val_str)
        await update.message.reply_text(f"✅ Đã đổi quỹ hoàn trả thành `{float(val_str):,.0f}` điểm!")
    else:
        await update.message.reply_text("❌ Thuộc tính không hợp lệ (`balance`, `name`, `cashback`)!")


# =========================
# 8. ĐẶT CƯỢC & HOÀN TRẢ TỰ ĐỘNG
# =========================
async def dat_cuoc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Bạn chưa đăng ký tài khoản! Gõ `/start` ở tin nhắn riêng.", parse_mode="Markdown")
        return
    if not context.args:
        cmd = update.message.text.split()[0].lower()
        await update.message.reply_text(f"⚠️ Dùng: `{cmd} [số_tiền]` (Min: 5,000)", parse_mode="Markdown")
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền cược không hợp lệ!")
        return
    if amount < 5000:
        await update.message.reply_text("❌ Cược tối thiểu **5,000** điểm!", parse_mode="Markdown")
        return

    u = users_data[user_id]
    if u["balance"] < amount:
        await update.message.reply_text("❌ Số dư không đủ!")
        return

    command = update.message.text.split()[0].lower()
    u["balance"] -= amount
    
    # Hoàn trả 0.8%
    earned_cashback = amount * 0.008
    u["cashback_fund"] += earned_cashback

    if "tai" in command:
        choice, key = "TÀI (⚫)", "tai"
    elif "xiu" in command:
        choice, key = "XỈU (⚪)", "xiu"
    elif "chan" in command:
        choice, key = "CHẴN (⚪)", "chan"
    elif "le" in command:
        choice, key = "LẺ (⚫)", "le"
    else:
        u["balance"] += amount
        u["cashback_fund"] -= earned_cashback
        return

    current_bets[key][user_id] = current_bets[key].get(user_id, 0) + amount
    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Cược {amount:,} vào {choice}")

    await gui_thong_bao_cskh(
        context,
        f"📊 **CƯỢC MỚI**\n• Khách: **{u['name']}** (`{u['custom_id']}`)\n• Cửa: `{choice}` — Tiền: `{amount:,}`"
    )
    await update.message.reply_text(f"🎲 Đặt thành công **{amount:,}** vào **{choice}**! (Tích lũy `+{earned_cashback:,.1f}` hoàn trả).", parse_mode="Markdown")

async def xem_lich_su(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not history_phien:
        await update.message.reply_text("📜 Chưa có lịch sử phiên cược.")
        return
    await update.message.reply_text(f"📜 **Lịch sử phiên:**\n{' '.join(history_phien[-15:])}", parse_mode="Markdown")


# =========================
# 9. VÒNG LẶP TỰ ĐỘNG & KHỚP KẾT QUẢ XÚC XẮC THỰC TẾ
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
                        f"⚠ **Min cược: 5,000 điểm** (Hoàn trả 0.8%)\n\n"
                        f"👉 Cú pháp: `/tai`, `/xiu`, `/chan`, `/le [số_tiền]`"
                    ),
                    parse_mode="Markdown"
                )
            
            await asyncio.sleep(40)

            # Tính tổng số người và tổng tiền trước khi ném xúc xắc
            total_tai = sum(current_bets["tai"].values())
            count_tai = len(current_bets["tai"])
            total_xiu = sum(current_bets["xiu"].values())
            count_xiu = len(current_bets["xiu"])
            total_chan = sum(current_bets["chan"].values())
            count_chan = len(current_bets["chan"])
            total_le = sum(current_bets["le"].values())
            count_le = len(current_bets["le"])

            if GROUP_CHAT_ID:
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=(
                        f"🔒 **Khóa sổ phiên #{phien_id}**\n\n"
                        f"⚫ **Tài:** `{count_tai}` người — ` {total_tai:,}` điểm\n"
                        f"⚪ **Xỉu:** `{count_xiu}` người — `{total_xiu:,}` điểm\n"
                        f"⚪ **Chẵn:** `{count_chan}` người — `{total_chan:,}` điểm\n"
                        f"⚫ **Lẻ:** `{count_le}` người — `{total_le:,}` điểm\n\n"
                        f"🎲 **Đang tung xúc xắc...**"
                    ),
                    parse_mode="Markdown"
                )
            
            # Gửi 3 xúc xắc và lấy CHÍNH XÁC giá trị từ Telegram trả về
            d1, d2, d3 = 1, 1, 1
            try:
                m1 = await application.bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
                d1 = m1.dice.value
                await asyncio.sleep(0.6)
                
                m2 = await application.bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
                d2 = m2.dice.value
                await asyncio.sleep(0.6)
                
                m3 = await application.bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
                d3 = m3.dice.value
            except Exception as e:
                logging.error(f"Lỗi ném xúc xắc: {e}")

            await asyncio.sleep(2)

            # Khớp chính xác kết quả từ tổng 3 mặt xúc xắc thực tế
            tong = d1 + d2 + d3
            ket_qua_tx = "TÀI (⚫)" if tong >= 11 else "XỈU (⚪)"
            ket_qua_cl = "CHẴN (⚪)" if tong % 2 == 0 else "LẺ (⚫)"
            
            icon_history = "⚫" if tong >= 11 else "⚪"
            history_phien.append(icon_history)
            if len(history_phien) > 30:
                history_phien.pop(0)

            winners_count = 0
            total_reward_paid = 0

            # Trả thưởng Tài / Xỉu
            winning_tx_key = "tai" if tong >= 11 else "xiu"
            for uid, amount in current_bets[winning_tx_key].items():
                payout = amount * 2 
                if uid in users_data:
                    users_data[uid]["balance"] += payout
                    users_data[uid]["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thắng #{phien_id}: +{payout:,}đ")
                winners_count += 1
                total_reward_paid += payout

            # Trả thưởng Chẵn / Lẻ
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
# 10. XỬ LÝ NÚT BẤM (CALLBACK)
# =========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "admin_help_code":
        await query.message.reply_text("💡 Hướng dẫn QTV tạo mã code:\nDùng lệnh: `/taocode [MÃ] [số_tiền]`\nVí dụ: `/taocode KHUYENMAI 100000`", parse_mode="Markdown")
    elif data == "admin_help_staff":
        await query.message.reply_text("💡 Hướng dẫn phân quyền:\n• Thêm Mod: `/themmod [id]`\n• Thêm CSKH: `/themcskh [id]`\n• Xóa CSKH: `/xoacskh [id]`", parse_mode="Markdown")
    elif data == "cskh_help_check":
        await query.message.reply_text("💡 Hướng dẫn tra cứu:\nDùng lệnh: `/checkid [Custom_ID hoặc Telegram_ID]`", parse_mode="Markdown")
    elif data == "cskh_help_sua":
        await query.message.reply_text("💡 Hướng dẫn sửa thông tin:\nDùng lệnh: `/suatt [ID] [balance/name/cashback] [giá_trị]`", parse_mode="Markdown")

    elif data.startswith("nap_click_"):
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
            f"🔔 **YÊU CẦU NẠP MỚI**\n• Khách: **{u.get('name')}** (`{u.get('custom_id')}`)\n• Tiền: `{amount:,}` VNĐ"
        )
        targets = {MASTER_ADMIN_ID} | sub_admins | cskh_staffs
        for adm in targets:
            try:
                await context.bot.send_message(chat_id=adm, text=f"Duyệt nạp cho **{u.get('name')}** (`{amount:,}đ`):", reply_markup=InlineKeyboardMarkup(admin_keyboard))
            except:
                pass
        await query.edit_message_text(text="✅ Đã gửi yêu cầu nạp cho CSKH & QTV duyệt!")

    elif data.startswith("nap_yes_"):
        if not is_admin(user_id) and not is_cskh(user_id):
            await query.answer("⛔ Không có quyền!", show_alert=True)
            return
        parts = data.split("_")
        target_id, amount = int(parts[2]), int(parts[3])
        if target_id in users_data:
            users_data[target_id]["balance"] += amount
            users_data[target_id]["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Nạp: +{amount:,}đ")
        await query.edit_message_text(text=f"✅ Đã duyệt cộng `{amount:,}` điểm!")
        try:
            await context.bot.send_message(chat_id=target_id, text=f"🎉 Nạp tiền thành công! Đã cộng `{amount:,}` điểm.", parse_mode="Markdown")
        except:
            pass

    elif data.startswith("nap_no_"):
        if not is_admin(user_id) and not is_cskh(user_id):
            await query.answer("⛔ Không có quyền!", show_alert=True)
            return
        target_id = int(data.split("_")[2])
        await query.edit_message_text(text="❌ Đã từ chối nạp.")
        try:
            await context.bot.send_message(chat_id=target_id, text="❌ Yêu cầu nạp tiền bị từ chối.")
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

    # Người chơi & Tiện ích
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["sd", "tk"], check_sd))
    app.add_handler(CommandHandler("linkmoi", link_moi))
    app.add_handler(CommandHandler("topmoi", top_moi))
    app.add_handler(CommandHandler("hoantra", nhan_hoantra))
    app.add_handler(CommandHandler("nap", menu_nap))
    app.add_handler(CommandHandler("rut", menu_rut))
    app.add_handler(CommandHandler("code", nhap_code))
    
    # QTV & CSKH
    app.add_handler(CommandHandler("taocode", tao_code))
    app.add_handler(CommandHandler("themmod", them_mod))
    app.add_handler(CommandHandler("themcskh", them_cskh))
    app.add_handler(CommandHandler("xoacskh", xoa_cskh))
    app.add_handler(CommandHandler("checkid", check_id))
    app.add_handler(CommandHandler("suatt", sua_tt))

    # Cược
    app.add_handler(CommandHandler("tai", dat_cuoc))
    app.add_handler(CommandHandler("xiu", dat_cuoc))
    app.add_handler(CommandHandler("chan", dat_cuoc))
    app.add_handler(CommandHandler("le", dat_cuoc))
    app.add_handler(CommandHandler("ls", xem_lich_su))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot Tài Xỉu & Chẵn Lẻ VIP đã khởi động thành công...")
    
    async def post_init(application):
        asyncio.create_task(auto_taixiu_loop(application))
        
    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
