import os
import json
import logging
import random
import asyncio
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# 1. WEB SERVER & MINI APP API (FLASK)
# =========================
web_app = Flask(__name__)

MINI_APP_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TKGame | Sảnh Trải Nghiệm</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 15px; }
        .card { background: #1e293b; border-radius: 12px; padding: 15px; margin-bottom: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        h2, h3 { margin-top: 0; color: #38bdf8; }
        .balance { font-size: 24px; font-weight: bold; color: #4ade80; }
        button { background: #38bdf8; color: #0f172a; border: none; padding: 10px 15px; border-radius: 8px; font-weight: bold; cursor: pointer; width: 100%; margin-top: 5px; }
        button:active { background: #0284c7; }
        input, select { width: 100%; padding: 10px; margin: 5px 0 10px 0; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: #fff; box-sizing: border-box; }
        .history-item { font-size: 13px; border-bottom: 1px solid #334155; padding: 6px 0; }
    </style>
</head>
<body>
    <div class="card">
        <h2>👤 Tài Khoản Thành Viên</h2>
        <p>Xin chào, <span id="username" style="font-weight:bold;">Đang tải...</span></p>
        <p>Mã ID: <span id="custom_id" style="color: #cbd5e1;">---</span></p>
        <p>Ví TK:</p>
        <div class="balance" id="balance">0 điểm</div>
    </div>

    <div class="card">
        <h3>⚡ Cược Nhanh Mini App</h3>
        <label>Cửa cược:</label>
        <select id="bet_choice">
            <option value="tai">TÀI (T)</option>
            <option value="xiu">XỈU (X)</option>
            <option value="chan">CHẴN (C)</option>
            <option value="le">LẺ (L)</option>
        </select>
        <label>Số tiền cược (Min 5,000):</label>
        <input type="number" id="bet_amount" value="5000" min="5000">
        <button onclick="placeBet()">ĐẶT CƯỢC NGAY</button>
    </div>

    <div class="card">
        <h3>📜 Lịch Sử Gần Đây</h3>
        <div id="history-list">Đang tải lịch sử...</div>
    </div>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();
        const userId = tg.initDataUnsafe?.user?.id || 8013947246;

        function loadUserData() {
            fetch(`/api/user?id=${userId}`)
                .then(res => res.json())
                .then(data => {
                    if(data.success) {
                        document.getElementById('username').innerText = data.name;
                        document.getElementById('custom_id').innerText = data.custom_id;
                        document.getElementById('balance').innerText = data.balance.toLocaleString() + " điểm";
                        
                        let histHtml = "";
                        data.history.slice(-5).reverse().forEach(h => {
                            histHtml += `<div class="history-item">${h}</div>`;
                        });
                        document.getElementById('history-list').innerText = histHtml || "Chưa có lịch sử.";
                    }
                });
        }

        function placeBet() {
            const choice = document.getElementById('bet_choice').value;
            const amount = parseInt(document.getElementById('bet_amount').value);
            
            fetch('/api/bet', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: userId, choice: choice, amount: amount })
            })
            .then(res => res.json())
            .then(data => {
                alert(data.message);
                loadUserData();
            });
        }

        loadUserData();
        setInterval(loadUserData, 5000);
    </script>
</body>
</html>
"""

@web_app.route('/')
def home():
    return "🤖 TKGame Bot & Mini App đang hoạt động 24/7!"

@web_app.route('/miniapp')
def mini_app():
    return render_template_string(MINI_APP_HTML)

@web_app.route('/api/user', methods=['GET'])
def api_get_user():
    try:
        user_id = int(request.args.get('id'))
    except:
        return jsonify({"success": False})
    if user_id in users_data:
        u = users_data[user_id]
        return jsonify({
            "success": True, "name": u["name"], "custom_id": u["custom_id"],
            "balance": u["balance"], "history": u["history_action"]
        })
    return jsonify({"success": False})

@web_app.route('/api/bet', methods=['POST'])
def api_post_bet():
    data = request.json
    user_id, choice, amount = data.get("user_id"), data.get("choice"), int(data.get("amount", 0))
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        return jsonify({"success": False, "message": "Tài khoản chưa được kích hoạt qua Bot!"})
    if amount < 5000:
        return jsonify({"success": False, "message": "Cược tối thiểu 5,000 điểm!"})
    u = users_data[user_id]
    if u["balance"] < amount:
        return jsonify({"success": False, "message": "Số dư ví không đủ!"})

    u["balance"] -= amount
    u["total_wagered"] = u.get("total_wagered", 0.0) + amount
    weekly_wager_stats[user_id] = weekly_wager_stats.get(user_id, 0.0) + amount
    u["cashback_fund"] += amount * 0.008
    current_bets[choice][user_id] = current_bets[choice].get(user_id, 0) + amount
    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] MiniApp cược {amount:,} vào {choice.upper()}")
    return jsonify({"success": True, "message": f"Đặt thành công {amount:,} vào {choice.upper()}!"})

def run_web():
    port = int(os.getenv("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)


# =========================
# 2. CẤU HÌNH HỆ THỐNG
# =========================
TOKEN = os.getenv("BOT_TOKEN")  
MASTER_ADMIN_ID = 8013947246  
GROUP_CHAT_ID = -1003932050774 

sub_admins = set()       
cskh_staffs = set()      

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

users_data = {}
gift_codes = {"VIP2026": 50000, "TET2026": 100000, "TANTHU": 5000}
gift_code_limits = {"TANTHU": 99999} 
used_tanthu_users = set() 

history_phien = [] 
phien_id = 66510
jackpot_pool = 283570.0  

current_bets = {"tai": {}, "xiu": {}, "chan": {}, "le": {}}
weekly_wager_stats = {} 
pending_orders = {}

SYSTEM_BANK_LIST = [
    {"name": "MSB", "stk": "6314072009", "chủ tài khoản": "TKGAME AUTO SYSTEM"},
    {"name": "MBBank", "stk": "0776876883", "chủ tài khoản": "TKGAME AUTO SYSTEM"}
]

def is_admin(user_id):
    return user_id == MASTER_ADMIN_ID or user_id in sub_admins

def is_master_admin(user_id):
    return user_id == MASTER_ADMIN_ID

def is_cskh(user_id):
    return user_id == MASTER_ADMIN_ID or user_id in cskh_staffs

# Thanh Menu Cố Định (Reply Keyboard) dưới khung chat giống mẫu
MAIN_REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🎮 Game"), KeyboardButton("👤 Tài khoản")],
        [KeyboardButton("💰 Nạp"), KeyboardButton("💳 Rút")],
        [KeyboardButton("🌸 Giới thiệu bạn bè"), KeyboardButton("🏆 BXH")],
        [KeyboardButton("👑 VIP"), KeyboardButton("🔎 Lệnh")]
    ],
    resize_keyboard=True
)


# =========================
# 3. LỆNH START & GIAO DIỆN CHÍNH
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if update.message.chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            "🎲 **TKGame | Sảnh Game Tự Động**\n\n"
            "📋 **Cú pháp cược nhanh tại nhóm (Min 1.000):**\n"
            "• `T [số_tiền]` hoặc `/tai [số_tiền]`\n"
            "• `X [số_tiền]` hoặc `/xiu [số_tiền]`\n"
            "• `C [số_tiền]` hoặc `/chan [số_tiền]`\n"
            "• `L [số_tiền]` hoặc `/le [số_tiền]`\n"
            "• `/sd` - Kiểm tra ví | `/ls` - Lịch sử",
            parse_mode="Markdown"
        )
        return

    if user_id not in users_data or users_data[user_id].get("step") != "active":
        users_data[user_id] = {
            "step": "waiting_name",
            "custom_id": f"{random.randint(10000000,99999999)}",
            "balance": 2000.0,
            "ref_balance": 0.0, 
            "cashback_fund": 0.0,
            "invited_count": 0,
            "referred_by": None,
            "total_deposited": 0.0,
            "total_wagered": 0.0,
            "history_action": []
        }
        await update.message.reply_text(
            "【**TKGame**】\n\n"
            "💡 Vui lòng nhập **Họ và Tên trùng với Tài Khoản Ngân Hàng** để bắt đầu đăng ký:",
            parse_mode="Markdown",
            reply_markup=MAIN_REPLY_KEYBOARD
        )
        return

    await send_user_dashboard(update, user_id)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if update.message.chat.type != "private":
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Xử lý nhập tên đăng ký
    if user_id in users_data and users_data[user_id].get("step") == "waiting_name":
        users_data[user_id]["name"] = text
        users_data[user_id]["step"] = "active"
        await update.message.reply_text(f"✅ Đăng ký thành công tài khoản chủ thẻ: **{text}**!", parse_mode="Markdown")
        await send_user_dashboard(update, user_id)
        return

    # Xử lý các nút bấm từ Menu cố định (Reply Keyboard)
    if text == "🎮 Game":
        keyboard = [
            [InlineKeyboardButton("🎲 Nhóm Tài Xỉu", url="https://t.me/+xyz")],
            [InlineKeyboardButton("🃏 Baccarat Xúc Xắc", url="https://t.me/+xyz")],
            [InlineKeyboardButton("🎰 Hổ Tài Lộc", callback_data="coming_soon"), InlineKeyboardButton("🎰 Olympus", callback_data="coming_soon")],
            [InlineKeyboardButton("📢 Kênh TKGame", url="https://t.me/vhaxstore")],
            [InlineKeyboardButton("🎡 Vòng quay", callback_data="vong_quay")]
        ]
        await update.message.reply_text("🎮 **SẢNH TRÒ CHƠI TKGAME**\nChọn sảnh chơi bên dưới:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif text == "👤 Tài khoản":
        await send_user_dashboard(update, user_id)

    elif text == "💰 Nạp":
        await hien_thi_menu_nap(update)

    elif text == "💳 Rút":
        await update.message.reply_text(
            "💳 **HƯỚNG DẪN RÚT TIỀN**\n\n"
            "💡 Cú pháp rút tiền chính thức:\n"
            "`/rut [số_tiền] [STK] [Mã_NH] [Tên_chủ_thẻ]`\n"
            "*(Ví dụ: `/rut 50000 0776876883 VCB NGUYEN VAN A`)*\n\n"
            "⚠ Điều kiện: Đã nạp tối thiểu 40.000 và hoàn thành x1 vòng cược.",
            parse_mode="Markdown"
        )

    elif text == "🌸 Giới thiệu bạn bè":
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        await update.message.reply_text(
            f"🌸 **CHƯƠNG TRÌNH GIỚI THIỆU BẠN BÈ**\n\n"
            f"🔗 Link giới thiệu của bạn:\n`{ref_link}`\n\n"
            f"🎁 Mời bạn, mỗi người đạt mốc được thưởng ngay `20.000` điểm vào quỹ mời bạn!",
            parse_mode="Markdown"
        )

    elif text == "🏆 BXH":
        await top_cuoc_tuan(update, context)

    elif text == "👑 VIP":
        await update.message.reply_text("👑 **HẠNG THÀNH VIÊN VIP**\nBạn đang ở cấp độ: **Thành viên Tiêu Chuẩn**\nTiếp tục nạp và cược để thăng hạng nhận quà khủng mỗi tuần!", parse_mode="Markdown")

    elif text == "🔎 Lệnh":
        await update.message.reply_text(
            "🔎 **DANH MỤC LỆNH HỆ THỐNG:**\n"
            "• `/sd` hoặc `/tk` - Kiểm tra ví\n"
            "• `/nap [số_tiền]` - Nạp điểm\n"
            "• `/rut [số_tiền] [STK] [Ngân_hàng] [Chủ_thẻ]` - Rút tiền\n"
            "• `/ht` - Nhận hoàn trả 0.8%\n"
            "• `/code [MÃ]` - Nhập mã code thưởng\n"
            "• `/ls` - Xem lịch sử cược",
            parse_mode="Markdown"
        )

async def send_user_dashboard(update: Update, user_id: int):
    u = users_data[user_id]
    keyboard = [
        [InlineKeyboardButton("🎲 Nhóm Tài Xỉu", url="https://t.me/+xyz"), InlineKeyboardButton("🃏 Baccarat Xúc Xắc", url="https://t.me/+xyz")],
        [InlineKeyboardButton("🎰 Hổ Tài Lộc", callback_data="coming_soon"), InlineKeyboardButton("🎰 Olympus", callback_data="coming_soon")],
        [InlineKeyboardButton("📢 Kênh TKGame", url="https://t.me/vhaxstore")],
        [InlineKeyboardButton("🎡 Vòng quay", callback_data="vong_quay")]
    ]
    await update.message.reply_text(
        f"【**TKGame**】\n\n"
        f"🆔 ID: `{u['custom_id']}`\n"
        f"💰 Ví TK: `{u['balance']:,.0f}`\n\n"
        f"🎁 Nạp lần đầu tặng 5% · Nạp thêm tặng 2%\n"
        f"🆔 Mời bạn, mỗi người đạt mốc được thưởng `20.000`\n\n"
        f"💡 Vào kênh TKGame xem thêm ưu đãi 🔽",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def hien_thi_menu_nap(update: Update):
    keyboard = [
        [InlineKeyboardButton("💳 BANK", callback_data="nap_bank"), InlineKeyboardButton("🟢 MoMo", callback_data="nap_momo"), InlineKeyboardButton("💬 Zalo", callback_data="nap_zalo")],
        [InlineKeyboardButton("📊 Lịch sử nạp", callback_data="lich_su_nap")],
        [InlineKeyboardButton("🔙 Quay lại", callback_data="menu_chinh"), InlineKeyboardButton("👤 Tài khoản", callback_data="tai_khoan")]
    ]
    await update.message.reply_text(
        "📥 Bấm BANK, MoMo hoặc Zalo bên dưới, rồi chọn số tiền.\n\n"
        "✍️ Gõ lệnh: `/nap số_tiền`\n"
        "Ví dụ: `/nap 60000` · cũng nhận `60.000` / `60k`\n\n"
        "🔥 **Lưu ý**\n"
        "🌸 Chuyển đúng số tiền và đúng nội dung.\n"
        "🌸 Mỗi lần nạp phải lấy thông tin mới.\n"
        "🚫 Đừng dùng thông tin cũ để chuyển lần sau.\n\n"
        "🏦 Nạp tối thiểu: `20.000`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# 4. NẠP, RÚT & NHẬP CODE
# =========================
async def menu_nap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` trước!")
        return
    if not context.args:
        await hien_thi_menu_nap(update)
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền không hợp lệ!")
        return
    if amount < 20000:
        await update.message.reply_text("❌ Nạp tối thiểu **20.000** điểm!", parse_mode="Markdown")
        return

    u = users_data[user_id]
    bank = random.choice(SYSTEM_BANK_LIST)
    order_id = f"NAP{random.randint(10000,99999)}"
    
    pending_orders[order_id] = {
        "user_id": user_id, "type": "nap", "amount": amount,
        "name": u["name"], "custom_id": u["custom_id"], "admin_status": "pending"
    }

    nap_text = (
        f"💳 **HƯỚNG DẪN NẠP ĐIỂM (#{order_id})**\n"
        f"🏦 Ngân hàng: *{bank['name']}* | STK: `{bank['stk']}`\n"
        f"👤 Chủ TK: *{bank['chủ tài khoản']}*\n"
        f"💰 Số tiền: `{amount:,}` VNĐ\n"
        f"📝 Nội dung CK: `NAP {u['name']} {u['custom_id']}`\n\n"
        f"⚠️ Chuyển khoản xong bấm nút bên dưới báo duyệt!"
    )
    keyboard = [[InlineKeyboardButton("✅ Đã Chuyển Khoản, Báo Duyệt", callback_data=f"nap_click_{order_id}")]]
    await update.message.reply_text(nap_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def menu_rut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` trước!")
        return
        
    if not context.args or len(context.args) < 4:
        await update.message.reply_text(
            "💡 **Cú pháp rút tiền chính thức:**\n"
            "`/rut [số_tiền] [STK] [Mã_NH] [Tên_chủ_thẻ]`\n"
            "*(Ví dụ: `/rut 50000 0776876883 VCB NGUYEN VAN A`)*",
            parse_mode="Markdown"
        )
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠ Số tiền không hợp lệ!")
        return
    
    if amount < 30000:
        await update.message.reply_text("❌ Rút tối thiểu **30,000** điểm!", parse_mode="Markdown")
        return

    u = users_data[user_id]
    if u["balance"] < amount:
        await update.message.reply_text("❌ Số dư ví không đủ để rút!", parse_mode="Markdown")
        return

    order_id = f"RUT{random.randint(10000,99999)}"
    pending_orders[order_id] = {
        "user_id": user_id, "type": "rut", "amount": amount,
        "stk": context.args[1], "ngan_hang": context.args[2].upper(), "chu_the": " ".join(context.args[3:]),
        "name": u["name"], "custom_id": u["custom_id"], "admin_status": "pending"
    }
    u["balance"] -= amount
    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Yêu cầu rút: -{amount:,}đ")
    await update.message.reply_text("⏳ Yêu cầu rút tiền đã được ghi nhận và gửi tới Admin xét duyệt!")

async def nhap_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or user_id not in users_data or users_data[user_id].get("step") != "active":
        return
    if not context.args:
        return
    code = context.args[0].strip().upper()
    if code == "TANTHU" and user_id not in used_tanthu_users:
        users_data[user_id]["balance"] += 5000
        used_tanthu_users.add(user_id)
        await update.message.reply_text("🎉 Nhận thành công Code Tân Thủ `5.000` điểm!", parse_mode="Markdown")
    elif code in gift_codes:
        reward = gift_codes[code]
        users_data[user_id]["balance"] += reward
        del gift_codes[code]
        await update.message.reply_text(f"🎉 Nhận mã thành công! Cộng `{reward:,.0f}` điểm vào ví.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Mã code không tồn tại hoặc đã hết hạn!")


# =========================
# 5. CÁC LỆNH KIỂM TRA & TÀI CHÍNH KHÁC
# =========================
async def check_sd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠ Bạn chưa đăng ký tài khoản! Gõ `/start`.")
        return
    u = users_data[user_id]
    await update.message.reply_text(
        f"👑 Tên: **{u['name']}** | ID: `{u['custom_id']}`\n"
        f"💰 Ví TK: `{u['balance']:,.0f}` điểm\n"
        f"🎁 Quỹ hoàn trả: `{u['cashback_fund']:,.0f}` điểm (Dùng `/ht`)",
        parse_mode="Markdown"
    )

async def nhan_hoantra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data:
        return
    u = users_data[user_id]
    amt = u.get("cashback_fund", 0.0)
    if amt < 1000:
        await update.message.reply_text("❌ Quỹ hoàn trả chưa đạt tối thiểu 1,000 điểm!")
        return
    u["balance"] += amt
    u["cashback_fund"] = 0.0
    await update.message.reply_text(f"🎉 Nhận hoàn trả thành công `+{amt:,.0f}` vào ví chính.")

async def top_cuoc_tuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_weekly = sorted(weekly_wager_stats.items(), key=lambda x: x[1], reverse=True)
    text = "🏆 **BẢNG XẾP HẠNG CƯỢC TUẦN** 🏆\n\n"
    for i in range(min(5, len(sorted_weekly))):
        uid, w = sorted_weekly[i]
        name = users_data.get(uid, {}).get("name", "Thành viên")
        text += f"#{i+1} **{name}** — `{w:,.0f}` điểm\n"
    await update.message.reply_text(text, parse_mode="Markdown")


# =========================
# 6. ĐẶT CƯỢC & VÒNG LẶP PHIÊN CHƠI (TUNG XÚC XẮC ICON TELE)
# =========================
async def dat_cuoc_nhanh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        return
    if not context.args:
        return
    try:
        amount = int(context.args[0])
    except:
        return
    if amount < 1000:
        await update.message.reply_text("❌ Cược tối thiểu 1.000 điểm!")
        return

    cmd = update.message.text.split()[0].lower()
    u = users_data[user_id]
    if u["balance"] < amount:
        await update.message.reply_text("❌ Số dư ví không đủ!")
        return

    u["balance"] -= amount
    u["total_wagered"] = u.get("total_wagered", 0.0) + amount
    weekly_wager_stats[user_id] = weekly_wager_stats.get(user_id, 0.0) + amount
    u["cashback_fund"] += amount * 0.008

    if cmd in ["t", "/tai"]:
        choice, key = "Tài (T)", "tai"
    elif cmd in ["x", "/xiu"]:
        choice, key = "Xỉu (X)", "xiu"
    elif cmd in ["c", "/chan"]:
        choice, key = "Chẵn (C)", "chan"
    elif cmd in ["l", "/le"]:
        choice, key = "Lẻ (L)", "le"
    else:
        u["balance"] += amount
        return

    current_bets[key][user_id] = current_bets[key].get(user_id, 0) + amount
    await update.message.reply_text(f"✅ Đã cược **{amount:,}** vào cửa **{choice}** thành công!")

async def xem_lich_su(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not history_phien:
        await update.message.reply_text("📜 Chưa có lịch sử phiên.")
        return
    await update.message.reply_text(f"📜 **Lịch sử 10 phiên gần nhất:**\n{' '.join(history_phien[-10:])}", parse_mode="Markdown")

async def auto_taixiu_loop(application):
    global phien_id, current_bets, jackpot_pool
    await asyncio.sleep(5)
    
    while True:
        try:
            current_bets = {"tai": {}, "xiu": {}, "chan": {}, "le": {}}

            if GROUP_CHAT_ID:
                hist_icons = " ".join(history_phien[-10:]) if history_phien else "Chưa có"
                keyboard_nhom = [[InlineKeyboardButton("📥 Nạp tiền", url=f"https://t.me/{application.bot.username}?start=nap"), InlineKeyboardButton("💳 Rút tiền", url=f"https://t.me/{application.bot.username}?start=rut")]]
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=(
                        f"🎲 **Bắt đầu nhận cược · Phiên #{phien_id}**\n"
                        f"💵 Min 1.000 · Max/ng 10.000.000 · Max/cửa 50.000.000\n\n"
                        f"🔥 **CỬA CƯỢC**\n"
                        f"🔴 Tài T | 🔵 Xỉu X\n"
                        f"⚪ Chẵn C | ⚫ Lẻ L\n\n"
                        f"✅ **Cách cược:** `T 5000` hoặc `/tai 5000`\n\n"
                        f"📜 Lịch sử gần đây: {hist_icons}"
                    ),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard_nhom)
                )

            await asyncio.sleep(40)

            total_tai = sum(current_bets["tai"].values())
            total_xiu = sum(current_bets["xiu"].values())
            total_chan = sum(current_bets["chan"].values())
            total_le = sum(current_bets["le"].values())

            # Tung xúc xắc bằng icon xúc xắc chính thức của Telegram (send_dice)
            d1, d2, d3 = 1, 1, 1
            try:
                m1 = await application.bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
                d1 = m1.dice.value
                await asyncio.sleep(0.5)
                m2 = await application.bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
                d2 = m2.dice.value
                await asyncio.sleep(0.5)
                m3 = await application.bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
                d3 = m3.dice.value
            except Exception as e:
                logging.error(f"Lỗi xúc xắc: {e}")

            await asyncio.sleep(1.5)

            tong = d1 + d2 + d3
            ket_qua_tx = "Tài" if tong >= 11 else "Xỉu"
            ket_qua_cl = "Chẵn" if tong % 2 == 0 else "Lẻ"
            
            history_phien.append("🔴" if tong >= 11 else "⚪")
            if len(history_phien) > 30:
                history_phien.pop(0)

            total_thang = 0.0
            total_thua = 0.0

            # Tính tiền thắng/thua cho Tài/Xỉu
            winning_tx = "tai" if tong >= 11 else "xiu"
            losing_tx = "xiu" if tong >= 11 else "tai"
            
            for uid, amt in current_bets[winning_tx].items():
                payout = amt * 1.97
                total_thang += payout
                if uid in users_data:
                    users_data[uid]["balance"] += payout
                    users_data[uid]["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thắng phiên #{phien_id}: +{payout:,.0f}đ")
            for uid, amt in current_bets[losing_tx].items():
                total_thua += amt

            # Tính tiền thắng/thua cho Chẵn/Lẻ
            winning_cl = "chan" if tong % 2 == 0 else "le"
            losing_cl = "le" if tong % 2 == 0 else "chan"

            for uid, amt in current_bets[winning_cl].items():
                payout = amt * 1.97
                total_thang += payout
                if uid in users_data:
                    users_data[uid]["balance"] += payout
            for uid, amt in current_bets[losing_cl].items():
                total_thua += amt

            jackpot_pool += (total_tai + total_xiu + total_chan + total_le) * 0.01

            if GROUP_CHAT_ID:
                dice_icons = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=(
                        f"🎉 **Kết quả phiên #{phien_id}**\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"🎲 {dice_icons.get(d1, '⚀')}  {dice_icons.get(d2, '⚀')}  {dice_icons.get(d3, '⚀')}  · Tổng điểm: **{tong}**\n"
                        f"🔵 Tài/Xỉu: **{ket_qua_tx}**\n"
                        f"⚫ Chẵn/Lẻ: **{ket_qua_cl}**\n\n"
                        f"💵 Tổng thắng: `{total_thang:,.0f}`\n"
                        f"💸 Tổng thua: `{total_thua:,.0f}`\n"
                        f"💰 Cộng hũ: `+0`\n"
                        f"🎁 Hũ hiện tại: `{jackpot_pool:,.0f}`\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"📊 **10 phiên gần nhất:**\n"
                        f"{' '.join(history_phien[-10:])}"
                    ),
                    parse_mode="Markdown"
                )

            phien_id += 1
        except Exception as e:
            logging.error(f"Lỗi vòng lặp: {e}")
        await asyncio.sleep(5)


# =========================
# 7. XỬ LÝ NÚT BẤM (CALLBACK)
# =========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "menu_chinh" or data == "tai_khoan":
        await send_user_dashboard(query, user_id)
    elif data == "nap_bank":
        await query.message.reply_text("💳 **NẠP QUA NGÂN HÀNG BANK**\nCú pháp: `/nap [số_tiền]` (Ví dụ: `/nap 50000`)", parse_mode="Markdown")
    elif data == "nap_momo":
        await query.message.reply_text("🟢 **NẠP QUA MOMO**\nCú pháp: `/nap [số_tiền]` (Ví dụ: `/nap 50000`)", parse_mode="Markdown")
    elif data == "nap_zalo":
        await query.message.reply_text("💬 **NẠP QUA ZALOPAY**\nCú pháp: `/nap [số_tiền]` (Ví dụ: `/nap 50000`)", parse_mode="Markdown")
    elif data == "lich_su_nap":
        await query.message.reply_text("📊 Bạn chưa có lịch sử giao dịch nạp nào gần đây.")
    elif data == "vong_quay":
        await query.message.reply_text("🎡 Vòng quay may mắn hiện đang bảo trì để nâng cấp phần thưởng lớn hơn!")
    elif data.startswith("nap_click_"):
        await query.message.reply_text("✅ Đã ghi nhận thông báo chuyển khoản của bạn. Admin sẽ kiểm tra và duyệt trong ít phút!")


# =========================
# 8. MAIN KHỞI CHẠY
# =========================
def main():
    if not TOKEN:
        raise RuntimeError("Chưa cấu hình BOT_TOKEN.")

    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    # Các lệnh người dùng
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["sd", "tk"], check_sd))
    app.add_handler(CommandHandler("nap", menu_nap))
    app.add_handler(CommandHandler("rut", menu_rut))
    app.add_handler(CommandHandler("code", nhap_code))
    app.add_handler(CommandHandler("ht", nhan_hoantra))
    app.add_handler(CommandHandler("ls", xem_lich_su))
    app.add_handler(CommandHandler("top", top_cuoc_tuan))

    # Lệnh cược nhanh (Cả cú pháp chữ viết tắt lẫn cú pháp gạch chéo)
    app.add_handler(CommandHandler(["tai", "xiu", "chan", "le", "t", "x", "c", "l"], dat_cuoc_nhanh))
    app.add_handler(MessageHandler(filters.Regex(r"^[tTxXcCvVlL]\s+\d+"), dat_cuoc_nhanh))

    # Xử lý tin nhắn văn bản (menu cố định) và nút bấm callback
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 TKGame Bot đã khởi động thành công...")

    async def post_init(application):
        asyncio.create_task(auto_taixiu_loop(application))

    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
