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
    <title>TKGame | Sảnh Trải Nghiệm VIP</title>
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
        <label>Số tiền cược (Min 1,000):</label>
        <input type="number" id="bet_amount" value="5000" min="1000">
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
    if amount < 1000:
        return jsonify({"success": False, "message": "Cược tối thiểu 1,000 điểm!"})
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
# 2. CẤU HÌNH HỆ THỐNG & PHÂN QUYỀN
# =========================
TOKEN = os.getenv("BOT_TOKEN")  
MASTER_ADMIN_ID = 8013947246  
GROUP_CHAT_ID = -1003932050774 

sub_admins = set()       # QTV phụ
cskh_staffs = set()      # Nhân viên CSKH

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

users_data = {}
gift_codes = {"VIP2026": 50000, "TET2026": 100000, "TANTHU": 5000}
gift_code_limits = {"TANTHU": 99999} 
used_tanthu_users = set() 

history_phien = [] 
phien_id = 66510
jackpot_pool = 283570.0  

history_bau_cua = []
phien_bau_cua_id = 34370

current_bets = {"tai": {}, "xiu": {}, "chan": {}, "le": {}}
bau_cua_bets = {"bau": {}, "cua": {}, "tom": {}, "ca": {}, "ga": {}, "nai": {}}

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

# Hàm tự động xóa tin nhắn lệnh của Admin/QTV để ẩn với người chơi khác
async def an_lenh_admin(update: Update):
    try:
        if update.message and update.message.chat.type in ["group", "supergroup"]:
            await update.message.delete()
    except Exception as e:
        logging.error(f"Không thể xóa tin nhắn lệnh: {e}")

# Thanh Menu Cố Định (Reply Keyboard) dưới khung chat
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
# 3. LỆNH START & GIỚI THIỆU GAME UY TÍN
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if update.message.chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            "🎲 **TKGame | Sảnh Game Tự Động**\n\n"
            "📋 **Cú pháp cược Tài Xỉu (Min 1.000):**\n"
            "• `T [số_tiền]` | `X [số_tiền]` | `C [số_tiền]` | `L [số_tiền]`\n\n"
            "🦀 **Cú pháp cược Bầu Cua:**\n"
            "• `Bau [số_tiền]` | `Cua [số_tiền]` | `Tom [số_tiền]`\n"
            "• `Ca [số_tiền]` | `Ga [số_tiền]` | `Nai [số_tiền]`",
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

        # Xử lý giới thiệu bạn bè (Thưởng 3.000 điểm)
        if context.args and context.args[0].startswith("ref_"):
            try:
                ref_id = int(context.args[0].replace("ref_", ""))
                if ref_id != user_id and ref_id in users_data:
                    users_data[user_id]["referred_by"] = ref_id
                    users_data[ref_id]["invited_count"] += 1
                    users_data[ref_id]["ref_balance"] += 3000  
                    try:
                        await context.bot.send_message(
                            chat_id=ref_id,
                            text="🎉 Chúc mừng! Bạn vừa mời thành công 1 bạn mới và nhận thưởng `3.000` điểm vào quỹ giới thiệu!",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
            except Exception as e:
                logging.error(f"Lỗi xử lý ref: {e}")

        # Gửi ảnh giới thiệu game uy tín chất lượng đẹp kèm thông tin
        welcome_img_url = "https://images.unsplash.com/photo-1518609878373-06d740f60d8b?q=80&w=1000&auto=format&fit=crop"
        intro_text = (
            "🌟 **CHÀO MỪNG ĐẾN VỚI TKGAME - SẢNH GIẢI TRÍ ĐỈNH CAO UY TÍN HÀNG ĐẦU** 🌟\n\n"
            "🏰 **VỀ CHÚNG TÔI & CAM KẾT VÀNG:**\n"
            "• 💯 **Uy tín tuyệt đối:** Hệ thống tự động 100%, nạp rút siêu tốc trong 30 giây.\n"
            "• 🛡️ **Minh bạch công khai:** Kết quả xúc xắc hoàn toàn ngẫu nhiên bằng công nghệ chuẩn Telegram (Dice API), chống gian lận tuyệt đối.\n"
            "• 💎 **Quyền lợi thành viên VIP:** Tỷ lệ ăn thưởng cao nhất thị trường (**1 ăn 1.97**), hoàn trả tự động **0.8%** mỗi ngày không giới hạn.\n"
            "• 🎁 **Ưu đãi ngập tràn:** Nạp lần đầu tặng ngay **5%**, nạp thêm tặng **2%**, thưởng giới thiệu bạn bè nhận ngay **3.000 điểm/người**.\n\n"
            "💡 Vui lòng nhập **Họ và Tên trùng với Tài Khoản Ngân Hàng** bên dưới để kích hoạt tài khoản:"
        )
        await update.message.reply_photo(photo=welcome_img_url, caption=intro_text, parse_mode="Markdown")
        return

    await send_user_dashboard(update, user_id)

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
        await update.message.reply_text(f"✅ Đăng ký thành công tài khoản chủ thẻ: **{text}**!", parse_mode="Markdown", reply_markup=MAIN_REPLY_KEYBOARD)
        await send_user_dashboard(update, user_id)
        return

    if text == "🎮 Game":
        keyboard = [
            [InlineKeyboardButton("🎲 Game Tài Xỉu", callback_data="choi_taixiu"), InlineKeyboardButton("🦀 Game Bầu Cua", callback_data="choi_baucua")],
            [InlineKeyboardButton("🎧 CSKH Hỗ Trợ 24/7", url="https://t.me/cskhtelevip")],
            [InlineKeyboardButton("🎡 Vòng quay", callback_data="vong_quay")]
        ]
        await update.message.reply_text("🎮 **SẢNH TRÒ CHƠI TKGAME**\nChọn trò chơi trực tiếp bên dưới:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif text == "👤 Tài khoản":
        await send_user_dashboard(update, user_id)

    elif text == "💰 Nạp":
        await hien_thi_menu_nap(update)

    elif text == "💳 Rút":
        await update.message.reply_text(
            "💳 **HƯỚNG DẪN RÚT TIỀN**\n\n"
            "💡 Cú pháp rút tiền chính thức:\n"
            "`/rut [số_tiền] [STK] [Mã_NH] [Tên_chủ_thẻ]`\n"
            "*(Ví dụ: `/rut 50000 0776876883 VCB NGUYEN VAN A`)*",
            parse_mode="Markdown"
        )

    elif text == "🌸 Giới thiệu bạn bè":
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        await update.message.reply_text(
            f"🌸 **CHƯƠNG TRÌNH GIỚI THIỆU BẠN BÈ**\n\n"
            f"🔗 Link giới thiệu:\n`{ref_link}`\n\n"
            f"🎁 Mời bạn bè, mỗi người tham gia bạn sẽ nhận ngay **3.000 điểm** vào quỹ thưởng!",
            parse_mode="Markdown"
        )

    elif text == "🏆 BXH":
        await top_cuoc_tuan(update, context)

    elif text == "👑 VIP":
        await update.message.reply_text("👑 **HẠNG THÀNH VIÊN VIP**\nBạn đang ở cấp độ: **Thành viên Tiêu Chuẩn**", parse_mode="Markdown")

    elif text == "🔎 Lệnh":
        await update.message.reply_text(
            "🔎 **DANH MỤC LỆNH HỆ THỐNG:**\n"
            "• `/sd` - Kiểm tra ví\n"
            "• `/nap [số_tiền]` - Nạp điểm\n"
            "• `/rut` - Rút tiền\n"
            "• `/ht` - Nhận hoàn trả 0.8%\n"
            "• `/code [MÃ]` - Nhập mã thưởng\n"
            "• `/ls` - Lịch sử cược",
            parse_mode="Markdown"
        )

async def send_user_dashboard(update: Update, user_id: int):
    u = users_data[user_id]
    keyboard = [
        [InlineKeyboardButton("🎲 Game Tài Xỉu", callback_data="choi_taixiu"), InlineKeyboardButton("🦀 Game Bầu Cua", callback_data="choi_baucua")],
        [InlineKeyboardButton("🎧 CSKH Hỗ Trợ 24/7", url="https://t.me/cskhtelevip")],
        [InlineKeyboardButton("🎡 Vòng quay", callback_data="vong_quay")]
    ]
    await update.message.reply_text(
        f"【**TKGame**】\n\n"
        f"🆔 ID: `{u['custom_id']}`\n"
        f"💰 Ví TK: `{u['balance']:,.0f}`\n\n"
        f"🎁 Nạp lần đầu tặng 5% · Nạp thêm tặng 2%\n"
        f"🆔 Mời bạn bè thưởng **3.000** điểm/người\n\n"
        f"💡 Chọn trò chơi trực tiếp bên dưới 🔽",
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
        "✍️ Gõ lệnh: `/nap số_tiền` (Ví dụ: `/nap 60000`)\n\n"
        "🔥 **Lưu ý:** Chuyển đúng số tiền và đúng nội dung. Nạp tối thiểu: `20.000`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# 4. NẠP, RÚT & NHẬP CODE
# =========================
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
        await update.message.reply_text("💡 Cú pháp rút tiền: `/rut [số_tiền] [STK] [Mã_NH] [Tên_chủ_thẻ]`", parse_mode="Markdown")
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
    u["balance"] -= amount
    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Rút: -{amount:,}đ")
    await update.message.reply_text("⏳ Yêu cầu rút tiền đã được ghi nhận và gửi tới Admin xét duyệt!")

async def nhap_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        return
    if not context.args:
        return
    code = context.args[0].strip().upper()
    if code == "TANTHU" and user_id not in used_tanthu_users:
        users_data[user_id]["balance"] += 5000
        used_tanthu_users.add(user_id)
        await update.message.reply_text("🎉 Nhận thành công Code Tân Thủ `5.000` điểm!", parse_mode="Markdown")
    elif code in gift_codes:
        limit = gift_code_limits.get(code, 1)
        if limit <= 0:
            await update.message.reply_text("❌ Mã code này đã hết lượt nhập!")
            return
        reward = gift_codes[code]
        users_data[user_id]["balance"] += reward
        gift_code_limits[code] -= 1
        if gift_code_limits[code] <= 0:
            del gift_codes[code]
        await update.message.reply_text(f"🎉 Nhận mã thành công! Cộng `{reward:,.0f}` điểm vào ví.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Mã code không tồn tại hoặc đã hết hạn!")


# =========================
# 5. TÍNH NĂNG ADMIN & QUẢN LÝ (ẨN LỆNH)
# =========================
async def tao_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await an_lenh_admin(update)
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    if not context.args or len(context.args) < 3:
        return
    code_name = context.args[0].strip().upper()
    try:
        amount = int(context.args[1])
        max_uses = int(context.args[2])
    except ValueError:
        return
    gift_codes[code_name] = amount
    gift_code_limits[code_name] = max_uses
    await update.message.reply_text(f"✅ Tạo mã thành công!\n🎁 Mã: `{code_name}` | Trị giá: `{amount:,}` | Lượt: `{max_uses}`", parse_mode="Markdown")

async def them_mod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await an_lenh_admin(update)
    if not is_master_admin(update.effective_user.id):
        return
    if not context.args:
        return
    try:
        mod_id = int(context.args[0])
        sub_admins.add(mod_id)
        await update.message.reply_text(f"✅ Đã cấp quyền QTV cho ID: `{mod_id}`")
    except ValueError:
        pass

async def them_cskh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await an_lenh_admin(update)
    if not is_master_admin(update.effective_user.id):
        return
    if not context.args:
        return
    try:
        staff_id = int(context.args[0])
        cskh_staffs.add(staff_id)
        await update.message.reply_text(f"✅ Đã cấp quyền CSKH cho ID: `{staff_id}`")
    except ValueError:
        pass

async def check_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await an_lenh_admin(update)
    if not is_cskh(update.effective_user.id):
        return
    if not context.args:
        return
    query_key = context.args[0].strip().upper()
    target_data = None
    for uid, data in users_data.items():
        if data.get("custom_id") == query_key or str(uid) == query_key:
            target_data = data
            break
    if not target_data:
        await update.message.reply_text("❌ Không tìm thấy người chơi!")
        return
    await update.message.reply_text(
        f"🔍 **THÔNG TIN KHÁCH HÀNG**\n"
        f"• Tên: **{target_data.get('name')}** | ID: `{target_data['custom_id']}`\n"
        f"• Ví: `{target_data['balance']:,.0f}` | Hoàn trả: `{target_data['cashback_fund']:,.0f}`\n"
        f"• Nạp: `{target_data.get('total_deposited', 0):,.0f}` | Cược: `{target_data.get('total_wagered', 0):,.0f}`",
        parse_mode="Markdown"
    )

async def check_sd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠ Bạn chưa đăng ký tài khoản! Gõ `/start`.")
        return
    u = users_data[user_id]
    await update.message.reply_text(
        f"👑 Tên: **{u['name']}** | ID: `{u['custom_id']}`\n"
        f"💰 Ví TK: `{u['balance']:,.0f}` điểm\n"
        f"🎁 Hoàn trả: `{u['cashback_fund']:,.0f}` điểm (Dùng `/ht`)",
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
# 6. ĐẶT CƯỢC TÀI XỈU & BẦU CUA
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
        current_bets[key][user_id] = current_bets[key].get(user_id, 0) + amount
    elif cmd in ["x", "/xiu"]:
        choice, key = "Xỉu (X)", "xiu"
        current_bets[key][user_id] = current_bets[key].get(user_id, 0) + amount
    elif cmd in ["c", "/chan"]:
        choice, key = "Chẵn (C)", "chan"
        current_bets[key][user_id] = current_bets[key].get(user_id, 0) + amount
    elif cmd in ["l", "/le"]:
        choice, key = "Lẻ (L)", "le"
        current_bets[key][user_id] = current_bets[key].get(user_id, 0) + amount
    elif cmd in ["bau", "b"]:
        choice, key = "Bầu", "bau"
        bau_cua_bets[key][user_id] = bau_cua_bets[key].get(user_id, 0) + amount
    elif cmd in ["cua"]:
        choice, key = "Cua", "cua"
        bau_cua_bets[key][user_id] = bau_cua_bets[key].get(user_id, 0) + amount
    elif cmd in ["tom", "t"]:
        choice, key = "Tôm", "tom"
        bau_cua_bets[key][user_id] = bau_cua_bets[key].get(user_id, 0) + amount
    elif cmd in ["ca"]:
        choice, key = "Cá", "ca"
        bau_cua_bets[key][user_id] = bau_cua_bets[key].get(user_id, 0) + amount
    elif cmd in ["ga", "g"]:
        choice, key = "Gà", "ga"
        bau_cua_bets[key][user_id] = bau_cua_bets[key].get(user_id, 0) + amount
    elif cmd in ["nai", "n"]:
        choice, key = "Nai", "nai"
        bau_cua_bets[key][user_id] = bau_cua_bets[key].get(user_id, 0) + amount
    else:
        u["balance"] += amount
        return

    await update.message.reply_text(f"✅ Đã cược **{amount:,}** vào cửa **{choice}** thành công!")

async def xem_lich_su(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not history_phien:
        await update.message.reply_text("📜 Chưa có lịch sử phiên.")
        return
    await update.message.reply_text(f"📜 **Lịch sử 10 phiên Tài Xỉu gần nhất:**\n{' '.join(history_phien[-10:])}", parse_mode="Markdown")


# =========================
# 7. VÒNG LẶP TỰ ĐỘNG: TÀI XỈU & BẦU CUA
# =========================
async def auto_taixiu_loop(application):
    global phien_id, current_bets, jackpot_pool, phien_bau_cua_id, bau_cua_bets
    await asyncio.sleep(5)
    
    while True:
        try:
            # --- VÒNG CHƠI TÀI XỈU ---
            current_bets = {"tai": {}, "xiu": {}, "chan": {}, "le": {}}

            if GROUP_CHAT_ID:
                hist_icons = " ".join(history_phien[-10:]) if history_phien else "Chưa có"
                keyboard_nhom = [
                    [InlineKeyboardButton("🔴 Cược Tài 5k", callback_data="bet_tai_5000"), InlineKeyboardButton("🔵 Cược Xỉu 5k", callback_data="bet_xiu_5000")],
                    [InlineKeyboardButton("📥 Nạp tiền", url=f"https://t.me/{application.bot.username}?start=nap"), InlineKeyboardButton("💳 Rút tiền", url=f"https://t.me/{application.bot.username}?start=rut")]
                ]
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=(
                        f"🎲 **GAME TÀI XỈU TRỰC TIẾP · Phiên #{phien_id}**\n"
                        f"💵 Min 1.000 · Max/ng 10.000.000\n\n"
                        f"🔥 **CỬA CƯỢC**\n"
                        f"🔴 Tài T | 🔵 Xỉu X\n"
                        f"⚪ Chẵn C | ⚫ Lẻ L\n\n"
                        f"✅ **Cách cược:** Gõ `T 5000` hoặc bấm nút bên dưới!\n\n"
                        f"📜 Lịch sử gần đây: {hist_icons}"
                    ),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard_nhom)
                )

            await asyncio.sleep(30)

            total_tai = sum(current_bets["tai"].values())
            total_xiu = sum(current_bets["xiu"].values())
            total_chan = sum(current_bets["chan"].values())
            total_le = sum(current_bets["le"].values())

            d1, d2, d3 = 1, 1, 1
            try:
                m1 = await application.bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
                d1 = m1.dice.value
                await asyncio.sleep(0.4)
                m2 = await application.bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
                d2 = m2.dice.value
                await asyncio.sleep(0.4)
                m3 = await application.bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
                d3 = m3.dice.value
            except Exception as e:
                logging.error(f"Lỗi xúc xắc TX: {e}")

            await asyncio.sleep(1)

            tong = d1 + d2 + d3
            ket_qua_tx = "Xỉu" if tong <= 10 else "Tài"
            ket_qua_cl = "Chẵn" if tong % 2 == 0 else "Lẻ"
            
            history_phien.append("🔴" if tong >= 11 else "⚪")
            if len(history_phien) > 30:
                history_phien.pop(0)

            total_thang = 0.0
            total_thua = 0.0

            winning_tx = "tai" if tong >= 11 else "xiu"
            losing_tx = "xiu" if tong >= 11 else "tai"
            
            for uid, amt in current_bets[winning_tx].items():
                payout = amt * 1.97
                total_thang += payout
                if uid in users_data:
                    users_data[uid]["balance"] += payout
                    users_data[uid]["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thắng TX #{phien_id}: +{payout:,.0f}đ")
            for uid, amt in current_bets[losing_tx].items():
                total_thua += amt

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
                        f"🧧 **Kết quả Tài Xỉu phiên #{phien_id}**\n"
                        f"──────────────────\n"
                        f"|  {dice_icons.get(d1, '⚀')}  {dice_icons.get(d2, '⚀')}  {dice_icons.get(d3, '⚀')}\n"
                        f"|  Tổng điểm: **{tong}**\n"
                        f"|  Tài/Xỉu: **{ket_qua_tx}**\n"
                        f"|  Chẵn/Lẻ: **{ket_qua_cl}**\n"
                        f"──────────────────\n"
                        f"|  🌿 Tổng thắng: `{total_thang:,.0f}`\n"
                        f"|  🍂 Tổng thua: `{total_thua:,.0f}`\n"
                        f"|  💰 Cộng hũ: `+0`\n"
                        f"|  🎁 Hũ hiện tại: `{jackpot_pool:,.0f}`\n"
                        f"──────────────────\n"
                        f"📊 **10 phiên gần nhất:**\n"
                        f"{' '.join(history_phien[-10:])}"
                    ),
                    parse_mode="Markdown"
                )
            phien_id += 1

            # --- VÒNG CHƠI BẦU CUA ---
            bau_cua_bets = {"bau": {}, "cua": {}, "tom": {}, "ca": {}, "ga": {}, "nai": {}}
            linh_vat_list = [("Bầu 🎃", "🎃"), ("Cua 🦀", "🦀"), ("Tôm 🦐", "🦐"), ("Cá 🐟", "🐟"), ("Gà 🐓", "🐓"), ("Nai 🦌", "🦌")]
            
            if GROUP_CHAT_ID:
                hist_bc = " ".join(history_bau_cua[-7:]) if history_bau_cua else "Chưa có"
                keyboard_bc = [
                    [InlineKeyboardButton("🎃 Cược Bầu 5k", callback_data="bet_bau_5000"), InlineKeyboardButton("🦀 Cược Cua 5k", callback_data="bet_cua_5000")],
                    [InlineKeyboardButton("🦐 Cược Tôm 5k", callback_data="bet_tom_5000"), InlineKeyboardButton("🐟 Cược Cá 5k", callback_data="bet_ca_5000")]
                ]
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=(
                        f"🦀 **GAME BẦU CUA TRỰC TIẾP · Phiên #{phien_bau_cua_id}**\n"
                        f"💵 Min 1.000 · Max/ng 10.000.000\n\n"
                        f"🔥 **CỬA CƯỢC:**\n"
                        f"• 🎃 Bầu B | 🦀 Cua C | 🦐 Tôm T\n"
                        f"• 🐟 Cá A | 🐓 Gà G | 🦌 Nai N\n\n"
                        f"✅ **Cách cược:** Gõ `Bau 5000` hoặc bấm nút bên dưới!\n\n"
                        f"📜 7 phiên gần nhất: {hist_bc}"
                    ),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard_bc)
                )

            await asyncio.sleep(30)

            bc1, bc2, bc3 = random.choices(linh_vat_list, k=3)
            
            try:
                await application.bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
                await asyncio.sleep(0.4)
            except:
                pass

            history_bau_cua.append(bc1[1] + bc2[1] + bc3[1])
            if len(history_bau_cua) > 20:
                history_bau_cua.pop(0)

            bc_thang = 0.0
            bc_thua = 0.0
            drawn_keys = [bc1[0].split()[0].lower(), bc2[0].split()[0].lower(), bc3[0].split()[0].lower()]

            for name_vn, k_code in [("Bầu", "bau"), ("Cua", "cua"), ("Tôm", "tom"), ("Cá", "ca"), ("Gà", "ga"), ("Nai", "nai")]:
                count_x = drawn_keys.count(name_vn.lower())
                if count_x > 0 and k_code in bau_cua_bets:
                    for uid, amt in bau_cua_bets[k_code].items():
                        payout = amt * (1 + count_x)
                        bc_thang += payout * 0.97
                        if uid in users_data:
                            users_data[uid]["balance"] += payout * 0.97
                elif k_code in bau_cua_bets:
                    for uid, amt in bau_cua_bets[k_code].items():
                        bc_thua += amt

            if GROUP_CHAT_ID:
                await application.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=(
                        f"🦀 **Kết quả Bầu Cua phiên #{phien_bau_cua_id}**\n"
                        f"──────────────────\n"
                        f"|  🎲 {bc1[0]}\n"
                        f"|  🎲 {bc2[0]}\n"
                        f"|  🎲 {bc3[0]}\n"
                        f"──────────────────\n"
                        f"|  🌿 Trả thưởng: `{bc_thang:,.0f}`\n"
                        f"|  🍂 Thua: `{bc_thua:,.0f}`\n"
                        f"──────────────────\n"
                        f"📊 **7 phiên gần nhất:**\n"
                        f"{' '.join(history_bau_cua[-7:])}"
                    ),
                    parse_mode="Markdown"
                )
            phien_bau_cua_id += 1

        except Exception as e:
            logging.error(f"Lỗi vòng lặp game: {e}")
        await asyncio.sleep(5)


# =========================
# 8. XỬ LÝ NÚT BẤM (CALLBACK & DUYỆT ĐƠN KHÓA TRÙNG)
# =========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data in ["menu_chinh", "tai_khoan"]:
        await send_user_dashboard(query, user_id)
    elif data == "choi_taixiu":
        await query.message.reply_text("🎲 **HƯỚNG DẪN TÀI XỈU:**\nGõ trực tiếp trong nhóm: `T 5000` (Tài) hoặc `X 5000` (Xỉu).", parse_mode="Markdown")
    elif data == "choi_baucua":
        await query.message.reply_text("🦀 **HƯỚNG DẪN BẦU CUA:**\nGõ trực tiếp trong nhóm: `Bau 5000` hoặc `Tom 5000`.", parse_mode="Markdown")
    elif data.startswith("bet_tai_") or data.startswith("bet_xiu_") or data.startswith("bet_bau_") or data.startswith("bet_cua_") or data.startswith("bet_tom_") or data.startswith("bet_ca_"):
        parts = data.split("_")
        choice_key, amt = parts[1], int(parts[2])
        if user_id not in users_data or users_data[user_id]["balance"] < amt:
            await query.answer("❌ Số dư ví không đủ hoặc chưa đăng ký tài khoản!", show_alert=True)
            return
        users_data[user_id]["balance"] -= amt
        if choice_key in ["tai", "xiu"]:
            current_bets[choice_key][user_id] = current_bets[choice_key].get(user_id, 0) + amt
        else:
            bau_cua_bets[choice_key][user_id] = bau_cua_bets[choice_key].get(user_id, 0) + amt
        await query.answer(f"✅ Đặt cược thành công {amt:,} vào {choice_key.upper()}!", show_alert=True)
    elif data.startswith("nap_yes_"):
        if not is_admin(user_id):
            await query.answer("⛔ Bạn không có quyền duyệt đơn!", show_alert=True)
            return
        order_id = data.replace("nap_yes_", "")
        if order_id in pending_orders:
            order = pending_orders[order_id]
            # Kiểm tra nếu đơn đã được xử lý trước đó bởi QTV/Admin khác thì chặn ngay
            if order.get("admin_status") == "processed":
                await query.answer("⚠ Đơn này đã được xử lý bởi Quản trị viên khác trước đó!", show_alert=True)
                await query.edit_message_text(text=f"🔒 Đơn #{order_id} đã được khóa (Đã duyệt trước đó).")
                return

            order["admin_status"] = "processed"
            target_id = order["user_id"]
            amount = order["amount"]
            if target_id in users_data:
                users_data[target_id]["balance"] += amount
                users_data[target_id]["total_deposited"] = users_data[target_id].get("total_deposited", 0.0) + amount
                users_data[target_id]["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Nạp: +{amount:,}đ")
            try:
                await context.bot.send_message(chat_id=target_id, text=f"🎉 Nạp tiền thành công! Đã cộng `{amount:,}` điểm vào ví.", parse_mode="Markdown")
            except:
                pass
            await query.edit_message_text(text=f"✅ **Đã duyệt thành công đơn nạp #{order_id}!** (Bởi ID: {user_id})")
    elif data.startswith("nap_no_"):
        if not is_admin(user_id):
            await query.answer("⛔ Bạn không có quyền từ chối!", show_alert=True)
            return
        order_id = data.replace("nap_no_", "")
        if order_id in pending_orders:
            order = pending_orders[order_id]
            if order.get("admin_status") == "processed":
                await query.answer("⚠ Đơn này đã được xử lý trước đó!", show_alert=True)
                return
            order["admin_status"] = "processed"
            await query.edit_message_text(text=f"❌ Đã từ chối đơn #{order_id}.")
    elif data == "nap_bank":
        await query.message.reply_text("💳 **NẠP QUA NGÂN HÀNG BANK**\nGõ lệnh: `/nap [số_tiền]`", parse_mode="Markdown")
    elif data == "nap_momo":
        await query.message.reply_text("🟢 **NẠP QUA MOMO**\nGõ lệnh: `/nap [số_tiền]`", parse_mode="Markdown")
    elif data == "nap_zalo":
        await query.message.reply_text("💬 **NẠP QUA ZALOPAY**\nGõ lệnh: `/nap [số_tiền]`", parse_mode="Markdown")
    elif data == "lich_su_nap":
        await query.message.reply_text("📊 Bạn chưa có lịch sử giao dịch nạp nào.")
    elif data == "vong_quay":
        await query.message.reply_text("🎡 Vòng quay may mắn đang diễn ra trong các sự kiện tuần!")
    elif data.startswith("nap_click_"):
        order_id = data.replace("nap_click_", "")
        if order_id in pending_orders:
            info = pending_orders[order_id]
            noti_text = f"🔔 **DUYỆT NẠP TIỀN CHO KHÁCH**\nKhách: **{info['name']}** (`{info['custom_id']}`)\nSố tiền: `{info['amount']:,}`"
            await gui_thong_bao_qtv_admin_nap(context, order_id, noti_text)
            await query.message.reply_text("✅ Đã gửi yêu cầu nạp tới hệ thống Quản trị viên xét duyệt!")


# =========================
# 9. MAIN KHỞI CHẠY
# =========================
def main():
    if not TOKEN:
        raise RuntimeError("Chưa cấu hình BOT_TOKEN.")

    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    # Các lệnh cơ bản
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["sd", "tk"], check_sd))
    app.add_handler(CommandHandler("nap", menu_nap))
    app.add_handler(CommandHandler("rut", menu_rut))
    app.add_handler(CommandHandler("code", nhap_code))
    app.add_handler(CommandHandler("ht", nhan_hoantra))
    app.add_handler(CommandHandler("ls", xem_lich_su))
    app.add_handler(CommandHandler("top", top_cuoc_tuan))

    # Lệnh Admin / QTV / CSKH (Có tính năng tự xóa tin nhắn để ẩn với thành viên khác)
    app.add_handler(CommandHandler("taocode", tao_code))
    app.add_handler(CommandHandler("themmod", them_mod))
    app.add_handler(CommandHandler("themcskh", them_cskh))
    app.add_handler(CommandHandler("checkid", check_id))

    # Cược nhanh Tài Xỉu & Bầu Cua
    app.add_handler(CommandHandler(["tai", "xiu", "chan", "le", "t", "x", "c", "l", "bau", "cua", "tom", "ca", "ga", "nai", "b", "g", "n"], dat_cuoc_nhanh))
    app.add_handler(MessageHandler(filters.Regex(r"^[a-zA-Zа-яА-ЯёЁà-ỹÀ-Ỹ]\s+\d+"), dat_cuoc_nhanh))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 TKGame Bot đã cập nhật thành công các tính năng nâng cao (Ẩn lệnh, Cam kết uy tín, Khóa đơn trùng)...")

    async def post_init(application):
        asyncio.create_task(auto_taixiu_loop(application))

    app.post_init = post_init
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
