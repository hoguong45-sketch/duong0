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
        <label>Số tiền cược (Min 10,000):</label>
        <input type="number" id="bet_amount" value="10000" min="10000">
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
    if amount < 10000:
        return jsonify({"success": False, "message": "Cược tối thiểu 10,000 điểm!"})
    u = users_data[user_id]
    if u["balance"] < amount:
        return jsonify({"success": False, "message": "Số dư ví không đủ!"})

    u["balance"] -= amount
    u["total_wagered"] = u.get("total_wagered", 0.0) + amount
    weekly_wager_stats[user_id] = weekly_wager_stats.get(user_id, 0.0) + amount
    u["cashback_fund"] += amount * 0.008
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

phien_id = 66516
jackpot_pool = 294016.0  
phien_bau_cua_id = 34370

weekly_wager_stats = {} 
pending_orders = {}

BANK_LIST_TEXT = (
    "📋 **DANH SÁCH MÃ NGÂN HÀNG HỖ TRỢ RÚT TIỀN:**\n\n"
    "✅ Vietcombank => `VCB`\n"
    "✅ BIDV => `BIDV`\n"
    "✅ Vietinbank => `VTB`\n"
    "✅ Techcombank => `TCB`\n"
    "✅ MB Bank => `MB`\n"
    "✅ Agribank => `AGR`\n"
    "✅ ACB => `ACB`\n"
    "✅ Sacombank => `STB`\n"
    "✅ VP Bank => `VPB`\n\n"
    "💡 **Cú pháp rút tiền ngân hàng:**\n"
    "`/rutbank [Số_tiền] [Mã_NH] [STK] [Tên_chủ_khoản]`"
)

SYSTEM_BANK_LIST = [
    {"name": "MSB", "stk": "6314072009", "chủ tài khoản": "TKGAME AUTO SYSTEM"},
    {"name": "MBBank", "stk": "0776876883", "chủ tài khoản": "TKGAME AUTO SYSTEM"}
]

def tinh_vip(deposited, wagered):
    base_dep = 500.0
    base_wag = 2000000.0
    current_vip = 0
    for level in range(1, 12):
        req_dep = base_dep * (2 ** (level - 1))
        req_wag = base_wag * (2 ** (level - 1))
        if deposited >= req_dep and wagered >= req_wag:
            current_vip = level
        else:
            break
    return current_vip

def is_admin(user_id):
    return user_id == MASTER_ADMIN_ID or user_id in sub_admins

def is_master_admin(user_id):
    return user_id == MASTER_ADMIN_ID

def is_cskh(user_id):
    return user_id == MASTER_ADMIN_ID or user_id in cskh_staffs

async def an_lenh_admin(update: Update):
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
# 3. LỆNH START & GIAO DIỆN CHÍNH
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in users_data or users_data[user_id].get("step") != "active":
        users_data[user_id] = {
            "step": "waiting_name",
            "custom_id": f"{random.randint(10000000,99999999)}",
            "balance": 0.0,  # Số dư mặc định 0đ theo yêu cầu
            "ref_balance": 0.0, 
            "cashback_fund": 0.0,
            "invited_count": 0,
            "referred_by": None,
            "total_deposited": 0.0,
            "total_wagered": 0.0,
            "history_action": []
        }

        welcome_img_url = "https://images.unsplash.com/photo-1518609878373-06d740f60d8b?q=80&w=1000&auto=format&fit=crop"
        intro_text = (
            "🌟 **CHÀO MỪNG ĐẾN VỚI TKGAME - SẢNH GIẢI TRÍ ĐỈNH CAO UY TÍN HÀNG ĐẦU** 🌟\n\n"
            "🏰 **VỀ CHÚNG TÔI & CAM KẾT VÀNG:**\n"
            "• 💯 **Uy tín tuyệt đối:** Hệ thống tự động 100%, nạp rút siêu tốc trong 30 giây.\n"
            "• 🛡️ **Minh bạch công khai:** Kết quả xúc xắc hoàn toàn ngẫu nhiên bằng công nghệ chuẩn Telegram (Dice API).\n\n"
            "💡 Vui lòng nhập **Họ và Tên trùng với Tài Khoản Ngân Hàng** bên dưới để kích hoạt tài khoản:"
        )
        await update.message.reply_photo(photo=welcome_img_url, caption=intro_text, parse_mode="Markdown")
        return

    await send_user_dashboard(update, user_id)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id in users_data and users_data[user_id].get("step") == "waiting_name":
        users_data[user_id]["name"] = text
        users_data[user_id]["step"] = "active"
        await update.message.reply_text(f"✅ Đăng ký thành công tài khoản chủ thẻ: **{text}**!", parse_mode="Markdown", reply_markup=MAIN_REPLY_KEYBOARD)
        await send_user_dashboard(update, user_id)
        return

    parts = text.split()
    if len(parts) >= 2:
        cmd = parts[0].upper()
        try:
            amt = int(parts[1])
        except ValueError:
            amt = 0

        # 1. TRÒ CHƠI CHỌN MẶT XÚC XẮC TÀI XỈU (VD: D 4 50000)
        if cmd == "D" and len(parts) >= 3:
            try:
                target_face = int(parts[1])
                amt_dice = int(parts[2])
                if 1 <= target_face <= 6 and amt_dice >= 10000:
                    if user_id not in users_data or users_data[user_id].get("step") != "active":
                        await update.message.reply_text("⚠️ Vui lòng gõ `/start` trước!")
                        return
                    u = users_data[user_id]
                    if u["balance"] < amt_dice:
                        await update.message.reply_text("❌ Số dư ví không đủ!", parse_mode="Markdown")
                        return
                    u["balance"] -= amt_dice
                    u["total_wagered"] += amt_dice
                    weekly_wager_stats[user_id] = weekly_wager_stats.get(user_id, 0.0) + amt_dice
                    await xu_ly_chon_mat_xucxac(update, context, user_id, target_face, amt_dice)
                    return
            except:
                pass

        # 2. TÀI XỈU HOẶC CHẴN LẺ (T, X, C, L)
        if amt >= 10000:
            if user_id not in users_data or users_data[user_id].get("step") != "active":
                await update.message.reply_text("⚠️ Vui lòng gõ `/start` và đăng ký tài khoản trước!")
                return
            
            u = users_data[user_id]
            if cmd in ["T", "TAI", "X", "XIU", "C", "CHAN", "L", "LE"]:
                if u["balance"] < amt:
                    await update.message.reply_text("❌ Số dư ví không đủ để đặt cược!", parse_mode="Markdown")
                    return
                u["balance"] -= amt
                u["total_wagered"] = u.get("total_wagered", 0.0) + amt
                weekly_wager_stats[user_id] = weekly_wager_stats.get(user_id, 0.0) + amt
                u["cashback_fund"] += amt * 0.008
                
                if cmd in ["T", "TAI"]:
                    choice = "tai"
                elif cmd in ["X", "XIU"]:
                    choice = "xiu"
                elif cmd in ["C", "CHAN"]:
                    choice = "chan"
                else:
                    choice = "le"

                await xu_ly_quay_taixiu_tu_dong(update, context, user_id, choice, amt)
                return

        # 3. BẦU CUA NHIỀU CON
        map_linh_vat = {
            "BAU": "bau", "CUA": "cua", "TOM": "tom", 
            "CA": "ca", "GA": "ga", "NAI": "nai"
        }
        if cmd in map_linh_vat or len(parts) >= 2:
            bets = []
            total_bet = 0
            i = 0
            while i < len(parts) - 1:
                k = parts[i].upper()
                if k in map_linh_vat:
                    try:
                        v = int(parts[i+1])
                        if v >= 10000:
                            bets.append((map_linh_vat[k], v))
                            total_bet += v
                            i += 2
                            continue
                    except:
                        pass
                i += 1

            if bets and total_bet > 0:
                if user_id not in users_data or users_data[user_id].get("step") != "active":
                    await update.message.reply_text("⚠️ Vui lòng gõ `/start` trước!")
                    return
                u = users_data[user_id]
                if u["balance"] < total_bet:
                    await update.message.reply_text(f"❌ Số dư không đủ cược tổng `{total_bet:,}` điểm!", parse_mode="Markdown")
                    return
                u["balance"] -= total_bet
                u["total_wagered"] = u.get("total_wagered", 0.0) + total_bet
                weekly_wager_stats[user_id] = weekly_wager_stats.get(user_id, 0.0) + total_bet
                u["cashback_fund"] += total_bet * 0.008
                await xu_ly_quay_baucua_nhieu_con(update, context, user_id, bets, total_bet)
                return

    if text == "🎮 Game":
        keyboard = [
            [InlineKeyboardButton("🎲 Game Tài Xỉu & Chẵn Lẻ", callback_data="choi_taixiu"), InlineKeyboardButton("🦀 Game Bầu Cua", callback_data="choi_baucua")],
            [InlineKeyboardButton("🎧 CSKH Hỗ Trợ 24/7", url="https://t.me/cskhtelevip")],
            [InlineKeyboardButton("🎡 Vòng quay", callback_data="vong_quay")]
        ]
        await update.message.reply_text("🎮 **SẢNH TRÒ CHƠI TKGAME**\nChọn trò chơi bên dưới hoặc gõ lệnh cược nhanh:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif text == "👤 Tài khoản":
        await send_user_dashboard(update, user_id)

    elif text == "💰 Nạp":
        await hien_thi_menu_nap(update)

    elif text == "💳 Rút":
        await update.message.reply_text(BANK_LIST_TEXT, parse_mode="Markdown")

    elif text == "🌸 Giới thiệu bạn bè":
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        await update.message.reply_text(
            f"🌸 **CHƯƠNG TRÌNH GIỚI THIỆU BẠN BÈ**\n\n"
            f"🔗 Link giới thiệu:\n`{ref_link}`\n\n"
            f"🎁 Mời bạn bè nhận ngay **3.000 điểm** vào quỹ thưởng!",
            parse_mode="Markdown"
        )

    elif text == "🏆 BXH":
        await top_cuoc_tuan(update, context)

    elif text == "👑 VIP":
        u = users_data[user_id]
        vip_lvl = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0))
        await update.message.reply_text(f"👑 **CẤP ĐỘ VIP THÀNH VIÊN**\nCấp hiện tại của bạn: **VIP {vip_lvl}** / Max VIP 11", parse_mode="Markdown")

    elif text == "🔎 Lệnh":
        await update.message.reply_text(
            "🔎 **DANH MỤC LỆNH HỆ THỐNG:**\n"
            "• `T [số]` hoặc `X [số]` - Cược Tài/Xỉu (Min 10k)\n"
            "• `C [số]` hoặc `L [số]` - Cược Chẵn/Lẻ (Min 10k)\n"
            "• `D [mặt_1-6] [số]` - Chọn mặt xúc xắc ăn X5\n"
            "• `BAU [số] CUA [số]` - Đánh Bầu Cua\n"
            "• `/check [ID]` - QTV tra cứu thông tin thành viên\n"
            "• `/sd` - Kiểm tra ví cá nhân",
            parse_mode="Markdown"
        )

async def send_user_dashboard(update: Update, user_id: int):
    u = users_data[user_id]
    vip_lvl = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0))
    keyboard = [
        [InlineKeyboardButton("🎲 Game Tài Xỉu & Chẵn Lẻ", callback_data="choi_taixiu"), InlineKeyboardButton("🦀 Game Bầu Cua", callback_data="choi_baucua")],
        [InlineKeyboardButton("🎧 CSKH Hỗ Trợ 24/7", url="https://t.me/cskhtelevip")],
        [InlineKeyboardButton("🎡 Vòng quay", callback_data="vong_quay")]
    ]
    chat_obj = update.message if update.message else update.callback_query.message
    await chat_obj.reply_text(
        f"【**TKGame**】\n\n"
        f"🆔 ID: `{u['custom_id']}` (Tele ID: `{user_id}`)\n"
        f"👑 **VIP {vip_lvl}** | 💰 Ví TK: `{u['balance']:,.0f}` điểm\n\n"
        f"💡 *Gõ lệnh cược: `T 50000`, `C 30000`, `D 4 20000`* 🔽",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def hien_thi_menu_nap(update: Update):
    keyboard = [
        [InlineKeyboardButton("💳 BANK", callback_data="nap_bank"), InlineKeyboardButton("🟢 MoMo", callback_data="nap_momo")],
        [InlineKeyboardButton("🔙 Quay lại", callback_data="menu_chinh")]
    ]
    chat_obj = update.message if update.message else update.callback_query.message
    await chat_obj.reply_text(
        "📥 Bấm BANK hoặc MoMo bên dưới, rồi gõ lệnh `/nap số_tiền` (Min 20.000).",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# 4. HỆ THỐNG TRÒ CHƠI & XÚC XẮC
# =========================
async def xu_ly_quay_taixiu_tu_dong(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, choice: str, amt: int):
    chat_id = update.effective_chat.id
    global phien_id
    phien_id += 1
    ma_gd = random.randint(100000, 999999)

    try:
        m1 = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        d1 = m1.dice.value
        await asyncio.sleep(0.4)
        m2 = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        d2 = m2.dice.value
        await asyncio.sleep(0.4)
        m3 = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        d3 = m3.dice.value
    except:
        d1, d2, d3 = random.randint(1,6), random.randint(1,6), random.randint(1,6)

    await asyncio.sleep(0.8)
    tong = d1 + d2 + d3
    
    # Xác định kết quả
    winning_tx = "tai" if tong >= 11 else "xiu"
    winning_cl = "chan" if tong % 2 == 0 else "le"

    is_win = False
    if choice in ["tai", "xiu"]:
        is_win = (choice == winning_tx)
    else:
        is_win = (choice == winning_cl)

    u = users_data[user_id]
    total_thang = 0.0
    if is_win:
        total_thang = amt * 1.97
        u["balance"] += total_thang
        ket_qua_str = f"Chiến thắng - +{total_thang:,.0f}đ"
        u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thắng {choice.upper()}: +{total_thang:,.0f}đ")
    else:
        ket_qua_str = f"Thua cuộc - -{amt:,}đ"
        u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thua {choice.upper()}: -{amt:,}đ")

    msg = (
        f"┏━━━━━━━━━━━━━┓\n"
        f"┣➤ Trò chơi: Tài Xỉu & Chẵn Lẻ\n"
        f"┣➤ Kết quả: {d1} + {d2} + {d3} = {tong} ({winning_tx.upper()} - {winning_cl.upper()})\n"
        f"┣➤ Cửa đặt : {choice.upper()}\n"
        f"┣➤ Mã giao dịch: {ma_gd}\n"
        f"┣➤ Tiền cược: {amt:,.0f}đ\n"
        f"┣━━━━━━━━━━━━━\n"
        f"┣➤ Kết quả: {ket_qua_str}\n"
        f"┗━━━━━━━━━━━━━┛\n"
        f"Số dư: {u['balance']:,.0f}đ"
    )
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

async def xu_ly_chon_mat_xucxac(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, target_face: int, amt: int):
    chat_id = update.effective_chat.id
    ma_gd = random.randint(100000, 999999)

    try:
        m1 = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        face_val = m1.dice.value
    except:
        face_val = random.randint(1,6)

    await asyncio.sleep(0.6)
    is_win = (face_val == target_face)
    u = users_data[user_id]

    if is_win:
        total_thang = amt * 5.0
        u["balance"] += total_thang
        ket_qua_str = f"Trúng mặt {target_face} - +{total_thang:,.0f}đ (X5)"
        u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thắng chọn mặt {target_face}: +{total_thang:,.0f}đ")
    else:
        ket_qua_str = f"Trượt - -{amt:,}đ"
        u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thua chọn mặt {target_face}: -{amt:,}đ")

    msg = (
        f"┏━━━━━━━━━━━━━┓\n"
        f"┣➤ Trò chơi: Chọn Mặt Xúc Xắc (X5)\n"
        f"┣➤ Mặt ra mắt: ⚀⚁⚂⚃⚄⚅"[target_face-1] + f" (Mặt {face_val})\n"
        f"┣➤ Bạn chọn : Mặt {target_face}\n"
        f"┣➤ Tiền cược: {amt:,.0f}đ\n"
        f"┣━━━━━━━━━━━━━\n"
        f"┣➤ Kết quả: {ket_qua_str}\n"
        f"┗━━━━━━━━━━━━━┛\n"
        f"Số dư: {u['balance']:,.0f}đ"
    )
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

async def xu_ly_quay_baucua_nhieu_con(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, bets: list, total_bet: int):
    chat_id = update.effective_chat.id
    global phien_bau_cua_id
    phien_bau_cua_id += 1
    ma_gd = random.randint(100000, 999999)

    try:
        m1 = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        r1_val = m1.dice.value
        await asyncio.sleep(0.4)
        m2 = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        r2_val = m2.dice.value
        await asyncio.sleep(0.4)
        m3 = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        r3_val = m3.dice.value
    except:
        r1_val, r2_val, r3_val = random.randint(1,6), random.randint(1,6), random.randint(1,6)

    dice_to_linhvat = {
        1: ("bau", "Bầu 🎃", "⚀"),
        2: ("cua", "Cua 🦀", "⚁"),
        3: ("tom", "Tôm 🦐", "⚂"),
        4: ("ca", "Cá 🐟", "⚃"),
        5: ("ga", "Gà 🐓", "⚄"),
        6: ("nai", "Nai 🦌", "⚅")
    }

    lv1 = dice_to_linhvat[r1_val]
    lv2 = dice_to_linhvat[r2_val]
    lv3 = dice_to_linhvat[r3_val]

    drawn_keys = [lv1[0], lv2[0], lv3[0]]
    hien_thi_ket_qua = f"{lv1[1]} · {lv2[1]} · {lv3[1]}"

    tong_thuong = 0.0
    chi_tiet_cua = []
    for c_key, c_amt in bets:
        count = drawn_keys.count(c_key)
        chi_tiet_cua.append(f"{c_key.upper()} ({c_amt:,}đ)")
        if count > 0:
            tong_thuong += c_amt * (1 + count) * 0.97

    u = users_data[user_id]
    if tong_thuong > 0:
        u["balance"] += tong_thuong
        ket_qua_str = f"Chiến thắng - +{tong_thuong:,.0f}đ"
        u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thắng Bầu Cua: +{tong_thuong:,.0f}đ")
    else:
        ket_qua_str = f"Thua cuộc - -{total_bet:,}đ"
        u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thua Bầu Cua: -{total_bet:,}đ")

    msg = (
        f"┏━━━━━━━━━━━━━┓\n"
        f"┣➤ Trò chơi: Bầu Cua\n"
        f"┣➤ Kết quả: {hien_thi_ket_qua}\n"
        f"┣➤ Cửa đặt : {', '.join(chi_tiet_cua)}\n"
        f"┣➤ Mã giao dịch: {ma_gd}\n"
        f"┣➤ Tổng cược: {total_bet:,.0f}đ\n"
        f"┣━━━━━━━━━━━━━\n"
        f"┣➤ Kết quả: {ket_qua_str}\n"
        f"┗━━━━━━━━━━━━━┛\n"
        f"Số dư: {u['balance']:,.0f}đ"
    )
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")


# =========================
# 5. CHỨC NĂNG QTV CHECK TK & QUẢN LÝ
# =========================
async def check_user_by_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await an_lenh_admin(update)
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Bạn không có quyền sử dụng lệnh này!")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Cú pháp: `/check [Telegram_ID]`", parse_mode="Markdown")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID không hợp lệ!")
        return

    if target_id not in users_data:
        await update.message.reply_text(f"❌ Không tìm thấy dữ liệu của ID `{target_id}`!", parse_mode="Markdown")
        return

    u = users_data[target_id]
    vip_lvl = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0))
    info_text = (
        f"🔍 **THÔNG TIN TÀI KHOẢN (QTV CHECK)**\n\n"
        f"🆔 Telegram ID: `{target_id}`\n"
        f"📌 Mã ID Game: `{u['custom_id']}`\n"
        f"👤 Họ tên: **{u.get('name', 'Chưa cập nhật')}**\n"
        f"👑 Cấp VIP: **VIP {vip_lvl}**\n"
        f"💰 Số dư ví: `{u['balance']:,.0f}` điểm\n"
        f"📥 Tổng nạp: `{u.get('total_deposited', 0):,.0f}` điểm\n"
        f"📤 Tổng cược: `{u.get('total_wagered', 0):,.0f}` điểm"
    )
    await update.message.reply_text(info_text, parse_mode="Markdown")

async def menu_rut_bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` trước!")
        return
    if not context.args or len(context.args) < 4:
        await update.message.reply_text(BANK_LIST_TEXT, parse_mode="Markdown")
        return
    try:
        amount = int(context.args[0])
        bank_code = context.args[1].upper()
        stk = context.args[2]
        chủ_tk = " ".join(context.args[3:])
    except ValueError:
        await update.message.reply_text("⚠️ Sai cú pháp!", parse_mode="Markdown")
        return

    if amount < 30000:
        await update.message.reply_text("❌ Rút tối thiểu **30.000** điểm!", parse_mode="Markdown")
        return
    u = users_data[user_id]
    if u["balance"] < amount:
        await update.message.reply_text("❌ Số dư ví không đủ để rút!", parse_mode="Markdown")
        return

    u["balance"] -= amount
    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Rút {amount:,} về {bank_code} ({stk})")
    await update.message.reply_text(f"✅ Gửi yêu cầu rút `{amount:,}` về `{bank_code}` thành công!", parse_mode="Markdown")

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
        await update.message.reply_text(f"🏷 Chức vụ: **{role_title}**\n⚠ Chưa đăng ký tài khoản! Gõ `/start`.")
        return
        
    u = users_data[user_id]
    vip_lvl = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0))
    await update.message.reply_text(
        f"🏷 Chức vụ: **{role_title}** | 👑 **VIP {vip_lvl}**\n"
        f"👑 Tên: **{u['name']}** | ID: `{u['custom_id']}` (Tele: `{user_id}`)\n"
        f"💰 Ví TK: `{u['balance']:,.0f}` điểm",
        parse_mode="Markdown"
    )

async def top_cuoc_tuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorted_weekly = sorted(weekly_wager_stats.items(), key=lambda x: x[1], reverse=True)
    text = "🏆 **BẢNG XẾP HẠNG CƯỢC TUẦN** 🏆\n\n"
    for i in range(min(5, len(sorted_weekly))):
        uid, w = sorted_weekly[i]
        name = users_data.get(uid, {}).get("name", "Thành viên")
        text += f"#{i+1} **{name}** — `{w:,.0f}` điểm\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data in ["menu_chinh", "tai_khoan"]:
        await send_user_dashboard(query, user_id)
    elif data == "choi_taixiu":
        tx_info = (
            "🔥 **CỬA CƯỢC TÀI XỈU & CHẴN LẺ**\n"
            "🔴 Tài T | 🔵 Xỉu X\n"
            "⚪ Chẵn C | ⚫ Lẻ L\n"
            "🎲 Chọn mặt xúc xắc X5: `D [mặt_1-6] [số_tiền]`\n\n"
            "💡 **Gõ trực tiếp vào chat:** `T 50000`, `C 20000`, `D 4 30000` (Min 10k)"
        )
        await query.message.reply_text(tx_info, parse_mode="Markdown")
    elif data == "choi_baucua":
        bc_info = (
            "🔥 **CỬA CƯỢC BẦU CUA**\n"
            "⚀ Bầu B | ⚁ Cua C\n"
            "⚂ Tôm T | ⚃ Cá A\n"
            "⚄ Gà G | ⚅ Nai N\n\n"
            "💡 **Gõ trực tiếp vào chat:** `BAU 30000` hoặc `BAU 10000 CUA 20000` (Min 10k)"
        )
        await query.message.reply_text(bc_info, parse_mode="Markdown")
    elif data == "nap_bank":
        await query.message.reply_text("💳 **NẠP QUA BANK**\nGõ lệnh: `/nap [số_tiền]`", parse_mode="Markdown")
    elif data == "nap_momo":
        await query.message.reply_text("🟢 **NẠP QUA MOMO**\nGõ lệnh: `/nap [số_tiền]`", parse_mode="Markdown")
    elif data == "vong_quay":
        await query.message.reply_text("🎡 Vòng quay may mắn đang diễn ra!")
    elif data.startswith("nap_yes_"):
        if not is_admin(user_id):
            return
        order_id = data.replace("nap_yes_", "")
        if order_id in pending_orders:
            order = pending_orders[order_id]
            order["admin_status"] = "processed"
            target_id = order["user_id"]
            amount = order["amount"]
            if target_id in users_data:
                users_data[target_id]["balance"] += amount
                users_data[target_id]["total_deposited"] = users_data[target_id].get("total_deposited", 0.0) + amount
            try:
                await context.bot.send_message(chat_id=target_id, text=f"🎉 Nạp thành công `+{amount:,}` điểm!", parse_mode="Markdown")
            except:
                pass
            await query.edit_message_text(text=f"✅ **Đã duyệt đơn nạp #{order_id}!**")
    elif data.startswith("nap_no_"):
        if not is_admin(user_id):
            return
        order_id = data.replace("nap_no_", "")
        if order_id in pending_orders:
            pending_orders[order_id]["admin_status"] = "processed"
            await query.edit_message_text(text=f"❌ Đã từ chối đơn #{order_id}.")
    elif data.startswith("nap_click_"):
        order_id = data.replace("nap_click_", "")
        if order_id in pending_orders:
            info = pending_orders[order_id]
            noti_text = f"🔔 **DUYỆT NẠP TIỀN**\nKhách: **{info['name']}** (`{info['custom_id']}`)\nSố tiền: `{info['amount']:,}`"
            targets = {MASTER_ADMIN_ID} | sub_admins
            for tid in targets:
                try:
                    kb = [
                        [
                            InlineKeyboardButton("✅ Duyệt", callback_data=f"nap_yes_{order_id}"),
                            InlineKeyboardButton("❌ Từ chối", callback_data=f"nap_no_{order_id}")
                        ]
                    ]
                    await context.bot.send_message(chat_id=tid, text=noti_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
                except:
                    pass
            await query.message.reply_text("✅ Đã báo chuyển khoản thành công!")


# =========================
# 6. MAIN KHỞI CHẠY
# =========================
def main():
    if not TOKEN:
        raise RuntimeError("Chưa cấu hình BOT_TOKEN.")

    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["sd", "tk"], check_sd))
    app.add_handler(CommandHandler("nap", menu_nap))
    app.add_handler(CommandHandler("rutbank", menu_rut_bank))
    app.add_handler(CommandHandler("rut", menu_rut_bank))
    app.add_handler(CommandHandler("code", nhap_code))
    app.add_handler(CommandHandler("check", check_user_by_admin))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 TKGame Bot đã cập nhật hoàn tất Chẵn Lẻ, Chọn mặt X5, Check ID và số dư 0đ...")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
