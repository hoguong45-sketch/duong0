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
    user_private_bets[user_id] = {"game": "taixiu", "choice": choice, "amount": amount}
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

sub_admins = set()       # Quản Trị Viên (QTV)
cskh_staffs = set()      # Nhân Viên CSKH

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

users_data = {}
gift_codes = {"VIP2026": 50000, "TET2026": 100000, "TANTHU": 5000}
gift_code_limits = {"TANTHU": 99999} 
used_tanthu_users = set() 

user_private_bets = {} # Lưu cược 1-1 riêng cho từng user
history_phien = [] 
phien_id = 66510
jackpot_pool = 283570.0  

history_bau_cua = []
phien_bau_cua_id = 34370

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

async def an_lenh_admin(update: Update):
    """Tự động xóa tin nhắn lệnh của Admin/QTV/CSKH để ẩn với mọi người"""
    try:
        if update.message and update.message.chat.type in ["group", "supergroup"]:
            await update.message.delete()
    except Exception as e:
        logging.error(f"Không thể xóa tin nhắn lệnh: {e}")

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
        await update.message.reply_text("🎲 **TKGame Bot** đang hoạt động!", parse_mode="Markdown")
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
            [InlineKeyboardButton("🎲 Game Tài Xỉu (1-1)", callback_data="choi_taixiu"), InlineKeyboardButton("🦀 Game Bầu Cua (1-1)", callback_data="choi_baucua")],
            [InlineKeyboardButton("🎧 CSKH Hỗ Trợ 24/7", url="https://t.me/cskhtelevip")],
            [InlineKeyboardButton("🎡 Vòng quay", callback_data="vong_quay")]
        ]
        await update.message.reply_text("🎮 **SẢNH TRÒ CHƠI TKGAME (CHƠI TỰ ĐỘNG 1-1)**\nChọn trò chơi bên dưới để bắt đầu:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    
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
        [InlineKeyboardButton("🎲 Game Tài Xỉu (1-1)", callback_data="choi_taixiu"), InlineKeyboardButton("🦀 Game Bầu Cua (1-1)", callback_data="choi_baucua")],
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
# 5. TÍNH NĂNG ADMIN & PHÂN QUYỀN
# =========================
async def lenh_nhận_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gõ lệnh /admin để nhận quyền Admin tối cao và tự động ẩn tin nhắn"""
    await an_lenh_admin(update)
    user_id = update.effective_user.id
    global MASTER_ADMIN_ID
    MASTER_ADMIN_ID = user_id
    await update.message.reply_text("👑 Bạn đã được cấp quyền **Admin Tối Cao** thành công!")

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
        await update.message.reply_text(f"✅ Đã cấp quyền **Quản Trị Viên (QTV)** cho ID: `{mod_id}`")
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
        await update.message.reply_text(f"✅ Đã cấp quyền **Nhân Viên CSKH** cho ID: `{staff_id}`")
    except ValueError:
        pass

async def check_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await an_lenh_admin(update)
    user_id = update.effective_user.id
    if not is_cskh(user_id):
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
    
    role_title = "Thành viên Tiêu Chuẩn"
    if user_id == MASTER_ADMIN_ID:
        role_title = "👑 Admin Tối Cao"
    elif user_id in sub_admins:
        role_title = "🛡 Quản Trị Viên (QTV)"
    elif user_id in cskh_staffs:
        role_title = "🎧 Nhân Viên CSKH"

    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text(f"🏷 Chức vụ hệ thống của bạn: **{role_title}**\n⚠ Bạn chưa đăng ký tài khoản chơi game! Gõ `/start`.")
        return
        
    u = users_data[user_id]
    await update.message.reply_text(
        f"🏷 Chức vụ: **{role_title}**\n"
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
# 6. GIAO DIỆN CHƠI TỰ ĐỘNG 1-1 NGAY TRONG INBOX (CHUẨN MẪU ĐẸP)
# =========================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data in ["menu_chinh", "tai_khoan"]:
        await send_user_dashboard(query, user_id)
        
    elif data == "choi_taixiu":
        keyboard = [
            [InlineKeyboardButton("🔴 Cược Tài 5.000", callback_data="tx_tai_5000"), InlineKeyboardButton("🔵 Cược Xỉu 5.000", callback_data="tx_xiu_5000")],
            [InlineKeyboardButton("🎲 Quay Thưởng & Tung Xúc Xắc Ngay", callback_data="tx_quay_ngay")],
            [InlineKeyboardButton("🔙 Quay lại Sảnh", callback_data="menu_chinh")]
        ]
        await query.message.reply_text(
            "🎲 **SẢNH TÀI XỈU 1-1 VỚI BOT**\n\n"
            "• **Bước 1:** Bấm chọn cửa cược **Tài** hoặc **Xỉu** (Mặc định 5.000 điểm).\n"
            "• **Bước 2:** Bấm **Quay Thưởng** để bot tự động tung xúc xắc Telegram và trả kết quả thắng thua chi tiết ngay lập tức!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif data == "choi_baucua":
        keyboard = [
            [InlineKeyboardButton("🎃 Bầu 5k", callback_data="bc_bau_5000"), InlineKeyboardButton("🦀 Cua 5k", callback_data="bc_cua_5000"), InlineKeyboardButton("🦐 Tôm 5k", callback_data="bc_tom_5000")],
            [InlineKeyboardButton("🐟 Cá 5k", callback_data="bc_ca_5000"), InlineKeyboardButton("🐓 Gà 5k", callback_data="bc_ga_5000"), InlineKeyboardButton("🦌 Nai 5k", callback_data="bc_nai_5000")],
            [InlineKeyboardButton("🎲 Tung Xúc Xắc Bầu Cua Ngay", callback_data="bc_quay_ngay")],
            [InlineKeyboardButton("🔙 Quay lại Sảnh", callback_data="menu_chinh")]
        ]
        await query.message.reply_text(
            "🦀 **SẢNH BẦU CUA 1-1 VỚI BOT**\n\n"
            "• **Bước 1:** Bấm chọn linh vật muốn cược.\n"
            "• **Bước 2:** Bấm **Tung Xúc Xắc** để bot lắc kết quả và trả thưởng siêu tốc!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("tx_tai_") or data.startswith("tx_xiu_"):
        parts = data.split("_")
        choice, amt = parts[1], int(parts[2])
        if user_id not in users_data or users_data[user_id]["balance"] < amt:
            await query.answer("❌ Số dư ví không đủ!", show_alert=True)
            return
        users_data[user_id]["balance"] -= amt
        user_private_bets[user_id] = {"game": "taixiu", "choice": choice, "amount": amt}
        await query.answer(f"✅ Đã chọn cược {amt:,} vào {choice.upper()}! Bấm nút Quay Thưởng bên dưới.", show_alert=True)

    elif data == "tx_quay_ngay":
        if user_id not in user_private_bets or user_private_bets[user_id]["game"] != "taixiu":
            await query.answer("⚠ Vui lòng bấm chọn cửa Tài hoặc Xỉu trước!", show_alert=True)
            return
            
        bet_info = user_private_bets[user_id]
        amt = bet_info["amount"]
        choice = bet_info["choice"]
        
        global phien_id, jackpot_pool
        phien_id += 1
        
        # Gửi hiệu ứng xúc xắc Telegram sinh động ngay trong inbox
        d1, d2, d3 = 1, 1, 1
        try:
            m1 = await context.bot.send_dice(chat_id=query.message.chat_id, emoji="🎲")
            d1 = m1.dice.value
            await asyncio.sleep(0.4)
            m2 = await context.bot.send_dice(chat_id=query.message.chat_id, emoji="🎲")
            d2 = m2.dice.value
            await asyncio.sleep(0.4)
            m3 = await context.bot.send_dice(chat_id=query.message.chat_id, emoji="🎲")
            d3 = m3.dice.value
        except Exception as e:
            logging.error(f"Lỗi xúc xắc: {e}")

        await asyncio.sleep(1)
        tong = d1 + d2 + d3
        is_bao = (d1 == d2 == d3)
        ket_qua_tx = "Bão" if is_bao else ("Tài" if tong >= 11 else "Xỉu")
        ket_qua_cl = "Chẵn" if tong % 2 == 0 else "Lẻ"
        
        history_phien.append("🔴" if tong >= 11 else "⚪")
        if len(history_phien) > 10:
            history_phien.pop(0)

        winning_tx = "tai" if tong >= 11 else "xiu"
        is_win = (choice == winning_tx)
        
        total_thang = 0.0
        total_thua = amt
        if is_win:
            total_thang = amt * 1.97
            users_data[user_id]["balance"] += total_thang
            users_data[user_id]["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thắng TX: +{total_thang:,.0f}đ")
            result_label = f"🎉 **THẮNG! Nhận `+{total_thang:,.0f}` điểm**"
        else:
            users_data[user_id]["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thua TX: -{amt:,}đ")
            result_label = f"😢 **THUA! Mất `{amt:,}` điểm**"

        jackpot_pool += 500.0
        dice_num_icons = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}
        
        # Hiển thị bảng kết quả phiên 1-1 siêu đẹp y hệt mẫu yêu cầu
        await query.message.reply_text(
            f"🎉 **Kết quả phiên Tài Xỉu #{phien_id}**\n"
            f"──────────────────\n"
            f"|  {dice_num_icons.get(d1, '⚀')}  🏆\n"
            f"|  {dice_num_icons.get(d2, '⚀')}  🏆\n"
            f"|  {dice_num_icons.get(d3, '⚀')}  🏆\n"
            f"|  🧮 Tổng điểm: **{tong}**\n"
            f"|  🔵 Tài/Xỉu: **{ket_qua_tx}** {'· 🐟 Bão' if is_bao else ''}\n"
            f"|  ⚫ Chẵn/Lẻ: **{ket_qua_cl}**\n"
            f"──────────────────\n"
            f"|  🎯 Cửa bạn chọn: **{choice.upper()}** (`{amt:,}`)\n"
            f"|  ✨ Kết quả: {result_label}\n"
            f"|  💰 Tổng thắng: `{total_thang:,.0f}`\n"
            f"|  🍂 Tổng thua: `{total_thua:,.0f}`\n"
            f"|  🎁 Hũ hiện tại: `{jackpot_pool:,.0f}`\n"
            f"──────────────────\n"
            f"📊 **Lịch sử gần nhất:**\n"
            f"{' '.join(history_phien[-10:])}",
            parse_mode="Markdown"
        )
        del user_private_bets[user_id]

    elif data.startswith("bc_") and data.endswith("_5000"):
        parts = data.split("_")
        choice = parts[1]
        amt = int(parts[2])
        if user_id not in users_data or users_data[user_id]["balance"] < amt:
            await query.answer("❌ Số dư ví không đủ!", show_alert=True)
            return
        users_data[user_id]["balance"] -= amt
        user_private_bets[user_id] = {"game": "baucua", "choice": choice, "amount": amt}
        await query.answer(f"✅ Đã chọn cược {amt:,} vào {choice.upper()}! Bấm Tung Xúc Xắc.", show_alert=True)

    elif data == "bc_quay_ngay":
        if user_id not in user_private_bets or user_private_bets[user_id]["game"] != "baucua":
            await query.answer("⚠ Vui lòng chọn linh vật bầu cua trước!", show_alert=True)
            return
            
        bet_info = user_private_bets[user_id]
        amt = bet_info["amount"]
        choice = bet_info["choice"]
        
        global phien_bau_cua_id
        phien_bau_cua_id += 1
        
        try:
            await context.bot.send_dice(chat_id=query.message.chat_id, emoji="🎲")
            await asyncio.sleep(1)
        except:
            pass

        linh_vat_list = [("bầu 🎃", "🎃"), ("cua 🦀", "🦀"), ("tôm 🦐", "🦐"), ("cá 🐟", "🐟"), ("gà 🐓", "🐓"), ("nai 🦌", "🦌")]
        bc1, bc2, bc3 = random.choices(linh_vat_list, k=3)
        
        history_bau_cua.append(bc1[1] + bc2[1] + bc3[1])
        if len(history_bau_cua) > 7:
            history_bau_cua.pop(0)

        drawn_keys = [bc1[0].split()[0], bc2[0].split()[0], bc3[0].split()[0]]
        count_x = drawn_keys.count(choice)
        
        bc_thang = 0.0
        bc_thua = amt
        if count_x > 0:
            bc_thang = amt * (1 + count_x) * 0.97
            users_data[user_id]["balance"] += bc_thang
            result_bc = f"🎉 **THẮNG {count_x} nháy! Nhận `+{bc_thang:,.0f}` điểm**"
        else:
            result_bc = f"😢 **THUA! Mất `{amt:,}` điểm**"

        await query.message.reply_text(
            f"🦀 **Kết quả phiên Bầu Cua #{phien_bau_cua_id}**\n"
            f"──────────────────\n"
            f"|  🎲 {bc1[0].title()}\n"
            f"|  🎲 {bc2[0].title()}\n"
            f"|  🎲 {bc3[0].title()}\n"
            f"──────────────────\n"
            f"|  🎯 Cửa chọn: **{choice.upper()}** (`{amt:,}`)\n"
            f"|  ✨ Kết quả: {result_bc}\n"
            f"|  🌿 Trả thưởng: `{bc_thang:,.0f}`\n"
            f"|  🍂 Thua: `{bc_thua:,.0f}`\n"
            f"──────────────────\n"
            f"📊 **7 phiên gần nhất:**\n"
            f"{' '.join(history_bau_cua[-7:])}",
            parse_mode="Markdown"
        )
        del user_private_bets[user_id]

    elif data.startswith("nap_yes_"):
        if not is_admin(user_id):
            await query.answer("⛔ Bạn không có quyền duyệt đơn!", show_alert=True)
            return
        order_id = data.replace("nap_yes_", "")
        if order_id in pending_orders:
            order = pending_orders[order_id]
            if order.get("admin_status") == "processed":
                await query.answer("⚠ Đơn này đã được xử lý bởi Quản trị viên khác trước đó!", show_alert=True)
                await query.edit_message_text(text=f"🔒 Đơn #{order_id} đã bị khóa.")
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
            await query.edit_message_text(text=f"✅ **Đã duyệt thành công đơn nạp #{order_id}!**")
            
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
            await query.message.reply_text("✅ Đã ghi nhận báo chuyển khoản. Admin sẽ duyệt trong ít phút!")


# =========================
# 7. MAIN KHỞI CHẠY
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

    # Lệnh Admin / QTV / CSKH (Thêm lệnh /admin nhận quyền và tự ẩn)
    app.add_handler(CommandHandler("admin", lenh_nhận_admin))
    app.add_handler(CommandHandler("taocode", tao_code))
    app.add_handler(CommandHandler("themmod", them_mod))
    app.add_handler(CommandHandler("themcskh", them_cskh))
    app.add_handler(CommandHandler("checkid", check_id))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 TKGame Bot đã hoàn thiện chế độ chơi tự động 1-1 với bot và giao diện kết quả cực đẹp...")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
