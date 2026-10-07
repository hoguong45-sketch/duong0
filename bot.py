import os
import json
import logging
import random
import asyncio
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
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
# 1. WEB SERVER & MINI APP API (FLASK)
# =========================
web_app = Flask(__name__)

MINI_APP_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mini App Tài Xỉu, Chẵn Lẻ & Bầu Cua VIP</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 15px; }
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
        <p>Số dư ví:</p>
        <div class="balance" id="balance">0 điểm</div>
    </div>

    <div class="card">
        <h3>⚡ Cược Nhanh Mini App</h3>
        <label>Cửa cược:</label>
        <select id="bet_choice">
            <option value="tai">TÀI (⚫)</option>
            <option value="xiu">XỈU (⚪)</option>
            <option value="chan">CHẴN (⚪)</option>
            <option value="le">LẺ (⚫)</option>
            <option value="bau">BẦU 🦀</option>
            <option value="cua">CUA 🦐</option>
            <option value="tom">TÔM 🦞</option>
            <option value="ca">CÁ 🐟</option>
            <option value="ga">GÀ 🐓</option>
            <option value="nai">NAI 🦌</option>
        </select>
        <label>Số tiền cược (Min 5,000):</label>
        <input type="number" id="bet_amount" value="5000" min="5000">
        <button onclick="placeBet()">ĐẶT CƯỢC NGAY</button>
    </div>

    <div class="card">
        <h3>📜 Lịch Sử Hoạt Động Gần Đây</h3>
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
                    } else {
                        alert("Vui lòng gõ /start với Bot Telegram trước!");
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
    return "🤖 Bot Tài Xỉu, Chẵn Lẻ & Bầu Cua VIP kết hợp Mini App đang hoạt động 24/7!"

@web_app.route('/miniapp')
def mini_app():
    return render_template_string(MINI_APP_HTML)

@web_app.route('/api/user', methods=['GET'])
def api_get_user():
    try:
        user_id = int(request.args.get('id'))
    except:
        return jsonify({"success": False, "message": "Invalid ID"})
    
    if user_id in users_data:
        u = users_data[user_id]
        return jsonify({
            "success": True,
            "name": u["name"],
            "custom_id": u["custom_id"],
            "balance": u["balance"],
            "history": u["history_action"]
        })
    return jsonify({"success": False})

@web_app.route('/api/bet', methods=['POST'])
def api_post_bet():
    data = request.json
    user_id = data.get("user_id")
    choice = data.get("choice")
    amount = int(data.get("amount", 0))

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
    
    earned_cashback = amount * 0.008
    u["cashback_fund"] += earned_cashback

    if choice in current_bets:
        current_bets[choice][user_id] = current_bets[choice].get(user_id, 0) + amount
    elif choice in current_bets_bc:
        current_bets_bc[choice][user_id] = current_bets_bc[choice].get(user_id, 0) + amount
    
    choice_names = {
        "tai": "TÀI (⚫)", "xiu": "XỈU (⚪)", "chan": "CHẴN (⚪)", "le": "LẺ (⚫)",
        "bau": "BẦU 🦀", "cua": "CUA 🦐", "tom": "TÔM 🦞", "ca": "CÁ 🐟", "ga": "GÀ 🐓", "nai": "NAI 🦌"
    }
    c_name = choice_names.get(choice, choice)
    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] MiniApp Cược {amount:,} vào {c_name}")

    return jsonify({"success": True, "message": f"Đặt thành công {amount:,} vào {c_name}!"})

def run_web():
    port = int(os.getenv("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)


# =========================
# 2. CẤU HÌNH BOT & PHÂN QUYỀN
# =========================
TOKEN = os.getenv("BOT_TOKEN")  
MASTER_ADMIN_ID = 8013947246  
GROUP_CHAT_ID = -1003932050774 

sub_admins = set()       
cskh_staffs = set()      

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

users_data = {}
gift_codes = {"VIP2026": 50000, "TET2026": 100000, "TANTHU": 5000}
gift_code_limits = {"TANTHU": 99999} 
used_tanthu_users = set() 

history_phien = [] 
history_phien_bc = []
phien_id = 1
phien_id_bc = 1
jackpot_pool = 100000.0  

current_bets = {
    "tai": {},  
    "xiu": {},  
    "chan": {}, 
    "le": {}    
}

# Biến cược cho trò Bầu Cua
current_bets_bc = {
    "bau": {},
    "cua": {},
    "tom": {},
    "ca": {},
    "ga": {},
    "nai": {}
}

weekly_wager_stats = {} 

BANK_LIST = [
    {"name": "Vietcombank", "code": "VCB"}, {"name": "BIDV", "code": "BIDV"},
    {"name": "Vietinbank", "code": "VTB"}, {"name": "Techcombank", "code": "TCB"},
    {"name": "MB Bank", "code": "MB"}, {"name": "Agribank", "code": "AGR"},
    {"name": "TienPhong Bank", "code": "TPB"}, {"name": "SHB bank", "code": "SHB"},
    {"name": "ACB", "code": "ACB"}, {"name": "Maritime Bank", "code": "MSB"},
    {"name": "VIB", "code": "VIB"}, {"name": "Sacombank", "code": "STB"},
    {"name": "VP Bank", "code": "VPB"}, {"name": "SeaBank", "code": "SEAB"},
    {"name": "Shinhan bank Việt Nam", "code": "SHBVN"}, {"name": "Eximbank", "code": "EIB"},
    {"name": "KienLong Bank", "code": "KLB"}, {"name": "Dong A Bank", "code": "DAB"},
    {"name": "HD Bank", "code": "HDB"}, {"name": "LienVietPostBank", "code": "LPB"},
    {"name": "VietBank", "code": "VBB"}, {"name": "ABBANK", "code": "ABB"},
    {"name": "PG Bank", "code": "PGB"}, {"name": "PVComBank", "code": "PVC"},
    {"name": "Bac A Bank", "code": "BAB"}, {"name": "Sai Gon Commercial Bank", "code": "SCB"},
    {"name": "BanVietBank", "code": "VCCB"}, {"name": "Saigonbank", "code": "SGB"},
    {"name": "Bao Viet Bank", "code": "BVB"}, {"name": "Orient Commercial Bank", "code": "OCB"}
]

SYSTEM_BANK_LIST = [
    {"name": "MSB", "stk": "6314072009", "chủ tài khoản": "HỆ THỐNG TỰ ĐỘNG (ANONYMOUS)"},
    {"name": "MBBank", "stk": "0776876883", "chủ tài khoản": "HỆ THỐNG TỰ ĐỘNG (ANONYMOUS)"}
]

def is_admin(user_id):
    return user_id == MASTER_ADMIN_ID or user_id in sub_admins

def is_master_admin(user_id):
    return user_id == MASTER_ADMIN_ID

def is_cskh(user_id):
    return user_id == MASTER_ADMIN_ID or user_id in cskh_staffs


# =========================
# 3. XỬ LÝ LỆNH START & MENU RIÊNG TƯ
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if update.message.chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            "🎲 **HỆ THỐNG TÀI XỈU, CHẴN LẺ & BẦU CUA VIP**\n\n"
            "📋 **Lệnh chơi tại nhóm (Min cược: 5,000):**\n"
            "• Tài Xỉu: `/tai [số_tiền]` | `/xiu [số_tiền]` | `/chan [số_tiền]` | `/le [số_tiền]`\n"
            "• Bầu Cua: `/bau [số_tiền]` | `/cua [số_tiền]` | `/tom [số_tiền]` | `/ca [số_tiền]` | `/ga [số_tiền]` | `/nai [số_tiền]`\n"
            "• `/sd` - Kiểm tra ví | `/ls` - Xem lịch sử\n"
            "• `/linkmoi` - Lấy link mời bạn | `/topmoi` - Xem BXH mời\n"
            "• `/top tuan` - Xem Bảng Xếp Hạng Cược Tuần\n"
            "• `/ht` (hoặc `/hoantra`) - Nhận tiền hoàn trả cược (0.8%)\n"
            "• `/code [MÃ]` - Nhập mã code thưởng",
            parse_mode="Markdown"
        )
        return

    keyboard = [
        [InlineKeyboardButton("🎮 Mở Mini App Trải Nghiệm", web_app={"url": "https://hoguong45-sketch.github.io/Bacarat/"})],
        [InlineKeyboardButton("💬 Liên Hệ CSKH Hỗ Trợ", url="https://t.me/cskhtelevip")]
    ]

    if is_admin(user_id):
        keyboard.insert(0, [InlineKeyboardButton("🛠 [QTV] Tạo Code Thưởng (/taocode)", callback_data="admin_help_code")])
        keyboard.insert(1, [InlineKeyboardButton("👥 [QTV] Thêm/Xóa Mod/CSKH", callback_data="admin_help_staff")])
    elif user_id in cskh_staffs:
        keyboard.insert(0, [InlineKeyboardButton("🔍 [CSKH] Kiểm tra ID (/checkid)", callback_data="cskh_help_check")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if user_id not in users_data or users_data[user_id].get("step") != "active":
        users_data[user_id] = {
            "step": "waiting_name",
            "custom_id": f"CUBE{random.randint(1000,9999)}",
            "balance": 0.0,
            "ref_balance": 0.0, 
            "cashback_fund": 0.0,
            "invited_count": 0,
            "referred_by": None,
            "total_deposited": 0.0,
            "total_wagered": 0.0,
            "history_action": []
        }

        if context.args and context.args[0].startswith("ref_"):
            try:
                ref_id = int(context.args[0].replace("ref_", ""))
                if ref_id != user_id and ref_id in users_data:
                    users_data[user_id]["referred_by"] = ref_id
                    users_data[ref_id]["invited_count"] += 1
                    users_data[ref_id]["ref_balance"] += 1000  
                    try:
                        await context.bot.send_message(
                            chat_id=ref_id,
                            text=f"🎉 Chúc mừng! Bạn vừa mời thành công thành viên mới và nhận `1,000` điểm vào quỹ giới thiệu!",
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
            f"🎁 **CHÀO MỪNG ĐẾN VỚI HỆ THỐNG GAME VIP!**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 Vui lòng nhập **Họ và Tên trùng với Tài Khoản Ngân Hàng** để bắt đầu:",
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
        
        keyboard = [
            [InlineKeyboardButton("🎮 Mở Mini App Trải Nghiệm", web_app={"url": "https://hoguong45-sketch.github.io/Bacarat/"})],
            [InlineKeyboardButton("💬 Liên Hệ CSKH Hỗ Trợ", url="https://t.me/cskhtelevip")]
        ]
        
        await update.message.reply_text(
            f"✅ **ĐĂNG KÝ VÀ KHỞI TẠO TÀI KHOẢN THÀNH CÔNG!**\n\n"
            f"👑 **Hạng tài khoản:** Thành viên Tân Thủ\n"
            f"📌 Tên chủ thẻ: **{text}**\n"
            f"🆔 ID của bạn: `{users_data[user_id]['custom_id']}`\n\n"
            f"🎮 **GIỚI THIỆU TRÒ CHƠI & ƯU ĐÃI TÂN THỦ:**\n"
            f"• Sảnh Tài Xỉu, Chẵn Lẻ & Bầu Cua siêu tốc hoạt động 24/7.\n"
            f"• Tỷ lệ ăn cực cao | Hoàn trả tự động **0.8%**.\n"
            f"• Nhập ngay mã code khởi đầu: `/code TANTHU` để nhận ngay **5,000 điểm** trải nghiệm miễn phí.\n\n"
            f"💡 Sử dụng các lệnh:\n"
            f"• `/sd` - Kiểm tra số dư\n"
            f"• `/ht` - Nhận hoàn trả\n"
            f"• `/nap [số_tiền]` | `/rut` - Xem danh sách ngân hàng rút tiền",
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
        f"👑 Hạng tài khoản: **Thành viên**\n"
        f"👤 Tài khoản: **{u['name']}**\n"
        f"🆔 ID cá nhân: `{u['custom_id']}`\n"
        f"💰 Số dư ví: `{u['balance']:,.0f}` điểm\n"
        f"🎁 Quỹ hoàn trả: `{u['cashback_fund']:,.0f}` điểm (Dùng `/ht`)\n"
        f"🎟 Quỹ mời bạn: `{u['ref_balance']:,.0f}` điểm (Dùng `/rutcode` khi đạt từ 10k+)\n"
        f"👥 Đã mời: `{u['invited_count']}` người\n\n"
        f"📋 Menu tính năng chính:\n"
        f"• `/sd` - Kiểm tra số dư\n"
        f"• `/linkmoi` - Link mời bạn bè\n"
        f"• `/topmoi` - BXH mời bạn\n"
        f"• `/top tuan` - BXH Cược Tuần\n"
        f"• `/ht` - Nhận hoàn trả 0.8%\n"
        f"• `/code TANTHU` - Nhận code tân thủ (5,000 điểm)\n"
        f"• `/nap [số_tiền]` - Nạp điểm (Min 40k)\n"
        f"• `/rut` - Xem danh sách mã ngân hàng rút tiền",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


# =========================
# 4. MỜI BẠN, HOÀN TRẢ & TẠO CODE GIỚI THIỆU (/rutcode)
# =========================
async def link_moi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` ở tin nhắn riêng!")
        return
    u = users_data[user_id]
    ref_link = u.get("ref_link", f"https://t.me/{context.bot.username}?start=ref_{user_id}")
    await update.message.reply_text(f"🔗 **LINK GIỚI THIỆU CỦA BẠN:**\n\n`{ref_link}`\n\n💡 Mỗi lượt giới thiệu bạn nhận `1,000` điểm vào quỹ mời bạn.", parse_mode="Markdown")

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

async def rut_code_gioi_thieu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠ Vui lòng gõ `/start` trước!")
        return

    u = users_data[user_id]
    ref_bal = u.get("ref_balance", 0.0)
    
    if ref_bal < 10000:
        await update.message.reply_text(f"❌ Quỹ mời bạn hiện tại là `{ref_bal:,.0f}` điểm. Cần đạt tối thiểu `10,000` điểm mới được rút thành mã code!", parse_mode="Markdown")
        return

    code_val = 10000.0
    max_uses = 1
    random_code_name = f"REF{random.randint(100000, 999999)}"
    
    gift_codes[random_code_name] = code_val
    gift_code_limits[random_code_name] = max_uses
    
    u["ref_balance"] -= 10000.0
    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Đổi code mời bạn: {random_code_name} (Trị giá 10k, 1 lượt)")
    
    await update.message.reply_text(
        f"🎉 **TẠO MÃ CODE QUỸ MỜI BẠN THÀNH CÔNG!**\n"
        f"🎟 Mã của bạn: `{random_code_name}`\n"
        f"💰 Trị giá mã code: `10,000` điểm\n"
        f"👥 Số lượng lượt nhập: `1` lượt duy nhất\n\n"
        f"💡 Bạn có thể gửi mã này cho người khác nhập qua lệnh `/code {random_code_name}`.",
        parse_mode="Markdown"
    )

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
# 5. KIỂM TRA SỐ DƯ & BXH CƯỢC TUẦN
# =========================
async def check_sd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠ Bạn chưa đăng ký tài khoản! Hãy nhắn tin riêng cho Bot gõ `/start`.", parse_mode="Markdown")
        return
    u = users_data[user_id]
    await update.message.reply_text(
        f"👑 Hạng tài khoản: **Thành viên**\n"
        f"👤 Tên: **{u['name']}** | ID cá nhân: `{u['custom_id']}`\n"
        f"💰 Số dư ví: `{u['balance']:,.0f}` điểm\n"
        f"🎁 Hoàn trả: `{u['cashback_fund']:,.0f}` điểm\n"
        f"🎟 Quỹ mời bạn: `{u['ref_balance']:,.0f}` điểm\n"
        f"👥 Đã mời: `{u['invited_count']}` người",
        parse_mode="Markdown"
    )

async def top_cuoc_tuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_weekly = sorted(weekly_wager_stats.items(), key=lambda x: x[1], reverse=True)
    text = "🏆 **BẢNG XẾP HẠNG CƯỢC TUẦN (TOP 1 - TOP 5)** 🏆\n\n"
    medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
    
    count = 0
    for i in range(min(5, len(sorted_weekly))):
        uid, total_wager = sorted_weekly[i]
        if total_wager <= 0:
            continue
        user_info = users_data.get(uid, {})
        name = user_info.get("name", "Thành viên")
        medal = medals[i]
        text += f"{medal} **{name}** — Cược: `{total_wager:,.0f}` điểm\n"
        count += 1
        
    if count == 0:
        text += "Chưa có dữ liệu cược trong tuần này."
    else:
        text += "\n🎁 **Lưu ý:** Top 1 đến Top 5 cược tuần vui lòng liên hệ Admin để nhận thưởng phần quà giá trị!"
        
    await update.message.reply_text(text, parse_mode="Markdown")

async def user_menu_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 **DANH SÁCH LỆNH HỆ THỐNG:**\n\n"
        "🎲 **Lệnh Cược Tài Xỉu & Chẵn Lẻ (Min 5,000):**\n"
        "• `/tai [số_tiền]` | `/xiu [số_tiền]`\n"
        "• `/chan [số_tiền]` | `/le [số_tiền]`\n\n"
        "🦀 **Lệnh Cược Bầu Cua (Min 5,000):**\n"
        "• `/bau [số_tiền]` | `/cua [số_tiền]` | `/tom [số_tiền]`\n"
        "• `/ca [số_tiền]` | `/ga [số_tiền]` | `/nai [số_tiền]`\n\n"
        "💰 **Giao Dịch & Tài Chính:**\n"
        "• `/nap [số_tiền]` - Nạp điểm (Min 40,000)\n"
        "• `/rut` - Xem danh sách ngân hàng rút tiền\n"
        "• `/sd` - Kiểm tra số dư | `/ht` - Nhận hoàn trả 0.8%\n"
        "• `/code TANTHU` - Nhận code tân thủ (5,000 điểm)",
        parse_mode="Markdown"
    )


# =========================
# 6. NẠP, RÚT & NHẬP CODE
# =========================
async def gui_thong_bao_admin_rut(context: ContextTypes.DEFAULT_TYPE, order_id: str, message_text: str):
    try:
        keyboard = [
            [InlineKeyboardButton("✅ Duyệt Rút", callback_data=f"rut_yes_{order_id}")],
            [InlineKeyboardButton("❌ Từ chối", callback_data=f"rut_no_{order_id}")]
        ]
        await context.bot.send_message(
            chat_id=MASTER_ADMIN_ID,
            text=message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Lỗi gửi thông báo rút cho Admin: {e}")

async def gui_thong_bao_qtv_admin_nap(context: ContextTypes.DEFAULT_TYPE, order_id: str, message_text: str):
    targets = {MASTER_ADMIN_ID} | sub_admins
    for target_id in targets:
        try:
            keyboard = [
                [InlineKeyboardButton("✅ Duyệt Nạp", callback_data=f"nap_yes_{order_id}")],
                [InlineKeyboardButton("❌ Từ chối", callback_data=f"nap_no_{order_id}")]
            ]
            await context.bot.send_message(
                chat_id=target_id,
                text=message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown"
            )
        except:
            pass

pending_orders = {}

async def menu_nap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` ở tin nhắn riêng trước!")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Dùng: `/nap [số_tiền]` (Min: 40,000)", parse_mode="Markdown")
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền không hợp lệ!")
        return
    if amount < 40000:
        await update.message.reply_text("❌ Nạp tối thiểu **40,000** điểm!", parse_mode="Markdown")
        return

    u = users_data[user_id]
    bank = random.choice(SYSTEM_BANK_LIST)
    order_id = f"NAP{random.randint(10000,99999)}"
    
    pending_orders[order_id] = {
        "user_id": user_id, "type": "nap", "amount": amount,
        "name": u["name"], "custom_id": u["custom_id"], "admin_status": "pending"
    }

    nap_text = (
        f"💳 **HƯỚNG DẪN NẠP ĐIỂM**\n"
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
        bank_list_msg = "🏦 **DANH SÁCH MÃ NGÂN HÀNG HỖ TRỢ RÚT TIỀN**\n\n"
        for b in BANK_LIST:
            bank_list_msg += f"✅ {b['name']} => `{b['code']}`\n"
        bank_list_msg += "\n💡 **Cú pháp rút tiền chính thức:**\n`/rut [số_tiền] [STK] [Mã_NH] [Tên_chủ_thẻ]`"
        await update.message.reply_text(bank_list_msg, parse_mode="Markdown")
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
    if u.get("total_deposited", 0.0) < 40000:
        await update.message.reply_text("❌ Bạn cần nạp tối thiểu lần đầu **40,000** điểm mới được mở khóa tính năng rút tiền!", parse_mode="Markdown")
        return
    if u.get("total_wagered", 0.0) < u.get("total_deposited", 0.0):
        con_thieu = u.get("total_deposited", 0.0) - u.get("total_wagered", 0.0)
        await update.message.reply_text(f"❌ Chưa đủ điều kiện rút! Cần cược thêm: `{con_thieu:,.0f}` điểm nữa.", parse_mode="Markdown")
        return

    stk, ngan_hang, chu_the = context.args[1], context.args[2].upper(), " ".join(context.args[3:])
    if u["balance"] < amount:
        await update.message.reply_text("❌ Số dư ví không đủ để rút!", parse_mode="Markdown")
        return

    order_id = f"RUT{random.randint(10000,99999)}"
    pending_orders[order_id] = {
        "user_id": user_id, "type": "rut", "amount": amount,
        "stk": stk, "ngan_hang": ngan_hang, "chu_the": chu_the,
        "name": u["name"], "custom_id": u["custom_id"], "admin_status": "pending"
    }

    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Yêu cầu rút: -{amount:,}đ")
    rut_notify_text = f"🔔 **YÊU CẦU RÚT TIỀN MỚI (#{order_id})**\n👤 Khách: **{u['name']}** (`{u['custom_id']}`)\n💰 Số tiền: `{amount:,}`\n🏦 STK: `{stk}` | NH: `{ngan_hang}`"
    await gui_thong_bao_admin_rut(context, order_id, rut_notify_text)
    await update.message.reply_text("⏳ Yêu cầu rút tiền đã được gửi tới Admin hệ thống để xét duyệt!")

async def nhap_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Gõ `/start` trước khi nhập code!")
        return
    if not context.args:
        await update.message.reply_text("⚠ Dùng: `/code [MÃ]`", parse_mode="Markdown")
        return
    code = context.args[0].strip().upper()

    if code == "TANTHU":
        if user_id in used_tanthu_users:
            await update.message.reply_text("❌ Bạn đã nhận mã code tân thủ này rồi!", parse_mode="Markdown")
            return
        reward = 5000
        users_data[user_id]["balance"] += reward
        used_tanthu_users.add(user_id)
        users_data[user_id]["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Nhận Code TANTHU: +{reward:,}đ")
        await update.message.reply_text(f"🎉 Nhận Code Tân Thủ thành công! Cộng thêm `{reward:,}` điểm.", parse_mode="Markdown")
        return

    if code in gift_codes:
        limit = gift_code_limits.get(code, 1)
        if limit <= 0:
            await update.message.reply_text("❌ Mã code này đã hết lượt nhập!")
            return
        reward = gift_codes[code]
        users_data[user_id]["balance"] += reward
        gift_code_limits[code] -= 1
        if gift_code_limits[code] <= 0:
            del gift_codes[code]
        users_data[user_id]["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Nhận Code {code}: +{reward:,.0f}đ")
        await update.message.reply_text(f"🎉 Nhận mã thành công! Cộng thêm `{reward:,.0f}` điểm vào ví.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Mã code không tồn tại hoặc đã hết lượt!")


# =========================
# 7. CÔNG CỤ QTV & CSKH
# =========================
async def tao_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args or len(context.args) < 3:
        await update.message.reply_text("⚠ Dùng: `/taocode [MÃ] [số_tiền] [số_lượng_nhập]`", parse_mode="Markdown")
        return
    code_name = context.args[0].strip().upper()
    try:
        amount, max_uses = int(context.args[1]), int(context.args[2])
    except ValueError:
        return
    gift_codes[code_name] = amount
    gift_code_limits[code_name] = max_uses
    await update.message.reply_text(f"✅ Tạo mã thành công: `{code_name}` | Trị giá: `{amount:,}` điểm", parse_mode="Markdown")

async def them_cskh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_master_admin(update.effective_user.id): return
    try:
        staff_id = int(context.args[0])
        cskh_staffs.add(staff_id)
        await update.message.reply_text(f"✅ Đã cấp quyền CSKH cho ID: `{staff_id}`")
    except: pass

async def xoa_cskh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_master_admin(update.effective_user.id): return
    try:
        staff_id = int(context.args[0])
        cskh_staffs.discard(staff_id)
        await update.message.reply_text(f"✅ Đã thu hồi quyền CSKH ID: `{staff_id}`")
    except: pass

async def them_mod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_master_admin(update.effective_user.id): return
    try:
        mod_id = int(context.args[0])
        sub_admins.add(mod_id)
        await update.message.reply_text(f"✅ Đã cấp quyền QTV cho ID: `{mod_id}`")
    except: pass

async def check_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_cskh(update.effective_user.id): return
    query_key = context.args[0].strip().upper()
    target_data = next((data for uid, data in users_data.items() if data.get("custom_id") == query_key or str(uid) == query_key), None)
    if not target_data:
        await update.message.reply_text("❌ Không tìm thấy thông tin khách hàng!")
        return
    history_snippet = "\n".join(target_data["history_action"][-10:]) if target_data["history_action"] else "Chưa có"
    await update.message.reply_text(f"🔍 **THÔNG TIN KHÁCH HÀNG**\n• Tên: **{target_data.get('name')}**\n• Số dư: `{target_data['balance']:,.0f}`\n📜 Lịch sử:\n{history_snippet}", parse_mode="Markdown")

async def admin_view_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    text = "👑 **QUẢN LÝ ĐƠN HÀNG**\n\n" + ("Chưa có đơn hàng nào." if not pending_orders else "\n".join([f"• Mã: `{oid}` | Loại: `{info['type'].upper()}` | Tiền: `{info['amount']:,}`" for oid, info in pending_orders.items()]))
    await update.message.reply_text(text, parse_mode="Markdown")


# =========================
# 8. ĐẶT CƯỢC TÀI XỈU, CHẴN LẺ & BẦU CUA
# =========================
async def dat_cuoc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Gõ `/start` ở tin nhắn riêng trước!", parse_mode="Markdown")
        return
    if not context.args:
        cmd = update.message.text.split()[0].lower()
        await update.message.reply_text(f"⚠️ Dùng: `{cmd} [số_tiền]` (Min: 5,000)", parse_mode="Markdown")
        return
    try:
        amount = int(context.args[0])
    except ValueError:
        return
    if amount < 5000:
        await update.message.reply_text("❌ Cược tối thiểu **5,000** điểm!", parse_mode="Markdown")
        return

    u = users_data[user_id]
    if u["balance"] < amount:
        await update.message.reply_text("❌ Số dư ví không đủ!", parse_mode="Markdown")
        return

    command = update.message.text.split()[0].lower().replace("/", "")
    u["balance"] -= amount
    u["total_wagered"] = u.get("total_wagered", 0.0) + amount
    weekly_wager_stats[user_id] = weekly_wager_stats.get(user_id, 0.0) + amount

    earned_cashback = amount * 0.008
    u["cashback_fund"] += earned_cashback

    mapping_tx = {"tai": ("TÀI (⚫)", "tai"), "xiu": ("XỈU (⚪)", "xiu"), "chan": ("CHẴN (⚪)", "chan"), "le": ("LẺ (⚫)", "le")}
    mapping_bc = {"bau": ("BẦU 🦀", "bau"), "cua": ("CUA 🦐", "cua"), "tom": ("TÔM 🦞", "tom"), "ca": ("CÁ 🐟", "ca"), "ga": ("GÀ 🐓", "ga"), "nai": ("NAI 🦌", "nai")}

    if command in mapping_tx:
        choice_name, key = mapping_tx[command]
        current_bets[key][user_id] = current_bets[key].get(user_id, 0) + amount
        u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Cược {amount:,} vào {choice_name}")
        await update.message.reply_text(f"🎲 Đặt thành công **{amount:,}** vào **{choice_name}**!", parse_mode="Markdown")
    elif command in mapping_bc:
        choice_name, key = mapping_bc[command]
        current_bets_bc[key][user_id] = current_bets_bc[key].get(user_id, 0) + amount
        u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Bầu Cua Cược {amount:,} vào {choice_name}")
        await update.message.reply_text(f"🦀 Bầu Cua: Đặt thành công **{amount:,}** vào **{choice_name}**!", parse_mode="Markdown")
    else:
        u["balance"] += amount
        u["total_wagered"] -= amount
        weekly_wager_stats[user_id] -= amount
        u["cashback_fund"] -= earned_cashback

async def xem_lich_su(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"📜 **Lịch sử Tài Xỉu:**\n{' '.join(history_phien[-15:]) if history_phien else 'Chưa có'}\n\n📜 **Lịch sử Bầu Cua:**\n{' '.join(history_phien_bc[-10:]) if history_phien_bc else 'Chưa có'}", parse_mode="Markdown")


# =========================
# 9. VÒNG LẶP TỰ ĐỘNG (TÀI XỈU & BẦU CUA CHẠY SONG SONG)
# =========================
async def auto_taixiu_loop(application):
    global phien_id, phien_id_bc, current_bets, current_bets_bc, jackpot_pool, weekly_wager_stats
    last_reset_time = datetime.now()
    
    await asyncio.sleep(5)
    while True:
        try:
            if datetime.now() - last_reset_time > timedelta(days=7):
                weekly_wager_stats.clear()
                last_reset_time = datetime.now()

            # --- VÒNG QUAY TÀI XỈU ---
            current_bets = {"tai": {}, "xiu": {}, "chan": {}, "le": {}}
            if GROUP_CHAT_ID:
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=f"📊 **TÀI XỈU - PHIÊN #{phien_id}**\n⏳ Đặt cược trong 35 giây...\n👉 Cú pháp: `/tai`, `/xiu`, `/chan`, `/le [số_tiền]`",
                    parse_mode="Markdown"
                )
            
            # --- VÒNG QUAY BẦU CUA ---
            current_bets_bc = {"bau": {}, "cua": {}, "tom": {}, "ca": {}, "ga": {}, "nai": {}}
            if GROUP_CHAT_ID:
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=f"🦀 **BẦU CUA - PHIÊN #{phien_id_bc}**\n⏳ Đặt cược trong 35 giây...\n👉 Cú pháp: `/bau`, `/cua`, `/tom`, `/ca`, `/ga`, `/nai [số_tiền]`",
                    parse_mode="Markdown"
                )

            await asyncio.sleep(35)

            # --- XỬ LÝ KẾT QUẢ TÀI XỈU ---
            d1, d2, d3 = random.randint(1, 6), random.randint(1, 6), random.randint(1, 6)
            tong = d1 + d2 + d3
            winning_tx_key = "tai" if tong >= 11 else "xiu"
            winning_cl_key = "chan" if tong % 2 == 0 else "le"

            for uid, amount in current_bets[winning_tx_key].items():
                payout = amount + (amount * 0.97)
                if uid in users_data:
                    users_data[uid]["balance"] += payout
            for uid, amount in current_bets[winning_cl_key].items():
                payout = amount + (amount * 0.97)
                if uid in users_data:
                    users_data[uid]["balance"] += payout

            icon_history = "⚫" if tong >= 11 else "⚪"
            history_phien.append(icon_history)
            if len(history_phien) > 30: history_phien.pop(0)

            if GROUP_CHAT_ID:
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=f"🎉 **KẾT QUẢ TÀI XỈU PHIÊN #{phien_id}**\n🎲 Xúc xắc: `{d1} - {d2} - {d3}` (Tổng: **{tong}** - **{'TÀI' if tong >= 11 else 'XỈU'}**)",
                    parse_mode="Markdown"
                )
            phien_id += 1

            # --- XỬ LÝ KẾT QUẢ BẦU CUA ---
            symbols = ["bau", "cua", "tom", "ca", "ga", "nai"]
            symbol_icons = {"bau": "🦀 Bầu", "cua": "🦐 Cua", "tom": "🦞 Tôm", "ca": "🐟 Cá", "ga": "🐓 Gà", "nai": "🦌 Nai"}
            bc1, bc2, bc3 = random.choice(symbols), random.choice(symbols), random.choice(symbols)
            ket_qua_bc = [bc1, bc2, bc3]

            for sym in symbols:
                matches = ket_qua_bc.count(sym)
                if matches > 0 and sym in current_bets_bc:
                    for uid, amount in current_bets_bc[sym].items():
                        # Tỷ lệ thưởng bầu cua: Trúng 1 mặt hoàn vốn + 1x, trúng 2 mặt hoàn vốn + 2x...
                        payout = amount + (amount * matches)
                        if uid in users_data:
                            users_data[uid]["balance"] += payout

            history_phien_bc.append(f"{symbol_icons[bc1][0]}{symbol_icons[bc2][0]}{symbol_icons[bc3][0]}")
            if len(history_phien_bc) > 20: history_phien_bc.pop(0)

            if GROUP_CHAT_ID:
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=f"🦀 **KẾT QUẢ BẦU CUA PHIÊN #{phien_id_bc}**\n🎲 Mở ra: `{symbol_icons[bc1]} - {symbol_icons[bc2]} - {symbol_icons[bc3]}`",
                    parse_mode="Markdown"
                )
            phien_id_bc += 1

        except Exception as e:
            logging.error(f"Lỗi vòng lặp game: {e}")
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
        await query.message.reply_text("💡 Hướng dẫn QTV/Admin tạo mã code:\nDùng lệnh: `/taocode [MÃ] [số_tiền] [số_lượng]`", parse_mode="Markdown")
    elif data == "admin_help_staff":
        await query.message.reply_text("💡 Hướng dẫn phân quyền:\n• Thêm Mod: `/themmod [id]`\n• Thêm CSKH: `/themcskh [id]`", parse_mode="Markdown")
    elif data == "cskh_help_check":
        await query.message.reply_text("💡 Hướng dẫn tra cứu:\nDùng lệnh: `/checkid [ID_riêng]`", parse_mode="Markdown")

    elif data.startswith("nap_click_"):
        order_id = data.replace("nap_click_", "")
        if order_id in pending_orders:
            info = pending_orders[order_id]
            noti_text = f"🔔 **DUYỆT NẠP TIỀN**\nKhách: **{info['name']}** (`{info['custom_id']}`)\nSố tiền: `{info['amount']:,}`"
            await gui_thong_bao_qtv_admin_nap(context, order_id, noti_text)
            await query.edit_message_text(text="✅ Đã gửi yêu cầu nạp tới Quản trị viên xử lý!")

    elif data.startswith("nap_yes_") or data.startswith("rut_yes_"):
        if not is_admin(user_id): return
        parts = data.split("_")
        action_type, order_id = parts[0], parts[2]
        if order_id in pending_orders:
            order = pending_orders[order_id]
            target_id, amount = order["user_id"], order["amount"]
            if action_type == "nap":
                if target_id in users_data:
                    users_data[target_id]["balance"] += amount
                    users_data[target_id]["total_deposited"] = users_data[target_id].get("total_deposited", 0.0) + amount
            else:
                if target_id in users_data:
                    users_data[target_id]["balance"] -= amount
            await query.edit_message_text(text=f"✅ **Đã duyệt thành công đơn #{order_id}!**")
            try:
                await context.bot.send_message(chat_id=target_id, text=f"🎉 Giao dịch của bạn đã được duyệt thành công!")
            except: pass

    elif data.startswith("nap_no_") or data.startswith("rut_no_"):
        if not is_admin(user_id): return
        order_id = data.split("_")[2]
        if order_id in pending_orders:
            await query.edit_message_text(text=f"❌ Đã từ chối đơn #{order_id}.")


# =========================
# 11. KHỞI CHẠY HỆ THỐNG
# =========================
def main():
    if not TOKEN:
        raise RuntimeError("Chưa cấu hình BOT_TOKEN.")

    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["sd", "tk"], check_sd))
    app.add_handler(CommandHandler("linkmoi", link_moi))
    app.add_handler(CommandHandler("topmoi", top_moi))
    app.add_handler(CommandHandler("rutcode", rut_code_gioi_thieu))
    app.add_handler(CommandHandler("ht", nhan_hoantra))
    app.add_handler(CommandHandler("hoantra", nhan_hoantra))
    app.add_handler(CommandHandler("nap", menu_nap))
    app.add_handler(CommandHandler("rut", menu_rut))
    app.add_handler(CommandHandler("code", nhap_code))
    app.add_handler(CommandHandler("menu", user_menu_help)) 
    
    app.add_handler(CommandHandler("taocode", tao_code))
    app.add_handler(CommandHandler("themmod", them_mod))
    app.add_handler(CommandHandler("themcskh", them_cskh))
    app.add_handler(CommandHandler("xoacskh", xoa_cskh))
    app.add_handler(CommandHandler("checkid", check_id))
    app.add_handler(CommandHandler("orders", admin_view_orders))

    # Lệnh cược Tài Xỉu & Chẵn Lẻ
    app.add_handler(CommandHandler("tai", dat_cuoc))
    app.add_handler(CommandHandler("xiu", dat_cuoc))
    app.add_handler(CommandHandler("chan", dat_cuoc))
    app.add_handler(CommandHandler("le", dat_cuoc))
    
    # Lệnh cược Bầu Cua mới thêm
    app.add_handler(CommandHandler("bau", dat_cuoc))
    app.add_handler(CommandHandler("cua", dat_cuoc))
    app.add_handler(CommandHandler("tom", dat_cuoc))
    app.add_handler(CommandHandler("ca", dat_cuoc))
    app.add_handler(CommandHandler("ga", dat_cuoc))
    app.add_handler(CommandHandler("nai", dat_cuoc))

    app.add_handler(CommandHandler("ls", xem_lich_su))
    app.add_handler(CommandHandler("top", top_cuoc_tuan))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot Tài Xỉu, Chẵn Lẻ & Bầu Cua VIP đã khởi động thành công...")
    
    async def post_init(application):
        asyncio.create_task(auto_taixiu_loop(application))
        
    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
