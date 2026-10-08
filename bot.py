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
    u["wager_remaining"] = max(0.0, u.get("wager_remaining", 0.0) - amount)
    weekly_wager_stats[user_id] = weekly_wager_stats.get(user_id, 0.0) + amount
    u["cashback_fund"] += amount * 0.008
    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] MiniApp cược {amount:,} vào {choice.upper()}")
    return jsonify({"success": True, "message": f"Đặt thành công {amount:,} vào {choice.upper()}!"})

def run_web():
    port = int(os.getenv("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)


# =========================
# 2. CẤU HÌNH HỆ THỐNG & TÀI KHOẢN
# =========================
TOKEN = os.getenv("BOT_TOKEN")  
MASTER_ADMIN_ID = 8013947246  

sub_admins = set()       
cskh_staffs = set()      

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

# SỐ TÀI KHOẢN DUY NHẤT MSB: 6314072009
SINGLE_BANK_INFO = {
    "name": "MSB", 
    "stk": "6314072009", 
    "chủ tài khoản": "TKGAME AUTO SYSTEM"
}

ZALOPAY_QR_URL = "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=600&auto=format&fit=crop" # Hoặc link ảnh QR ZaloPay thực tế

BANK_LIST_TEXT = (
    f"📋 **CỔNG RÚT TIỀN TỰ ĐỘNG - MSB: 6314072009**\n\n"
    "✅ Vietcombank => `VCB`\n"
    "✅ BIDV => `BIDV`\n"
    "✅ Techcombank => `TCB`\n"
    "✅ MB Bank => `MB`\n\n"
    "⚠️ **Lưu ý:** Lần rút đầu tiên yêu cầu tài khoản đã nạp tối thiểu `50.000đ` và hoàn thành `x1` vòng cược tổng tiền!\n\n"
    "💡 **Cú pháp rút:**\n"
    "`/rutbank [Số_tiền] [Mã_NH] [STK] [Tên_chủ_khoản]`"
)

def tinh_vip(deposited, wagered):
    """Thông số nạp và cược chuẩn để lên cấp từ VIP 1 đến VIP 11"""
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
            "balance": 5000.0,  # Tặng ngay 5k khi vào chơi
            "ref_balance": 0.0, 
            "cashback_fund": 0.0,
            "total_deposited": 0.0,
            "total_wagered": 0.0,
            "has_deposited_50k": False,
            "wager_remaining": 0.0,
            "history_action": [f"[{datetime.now().strftime('%d/%m %H:%M')}] Tặng thưởng tân thủ: +5,000đ"]
        }

        welcome_img_url = "https://images.unsplash.com/photo-1518609878373-06d740f60d8b?q=80&w=1000&auto=format&fit=crop"
        intro_text = (
            "🌟 **CHÀO MỪNG ĐẾN VỚI TKGAME - TẶNG NGAY 5.000Đ KHI VÀO CHƠI** 🌟\n\n"
            "🏰 **THÔNG TIN HỆ THỐNG:**\n"
            "• STK Nhận Tiền Duy Nhất: `6314072009` (MSB)\n"
            "• Khuyến mãi nạp 135% tự chọn (x1 tiền nạp + x1 tiền KM vòng cược).\n\n"
            "💡 Vui lòng nhập **Họ và Tên trùng với Tài Khoản Ngân Hàng** để kích hoạt tài khoản:"
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
        await update.message.reply_text(f"✅ Đăng ký thành công! Nhận `5.000đ` vào ví. Chủ thẻ: **{text}**", parse_mode="Markdown", reply_markup=MAIN_REPLY_KEYBOARD)
        await send_user_dashboard(update, user_id)
        return

    parts = text.split()
    if len(parts) >= 2:
        cmd = parts[0].upper()
        try:
            amt = int(parts[1])
        except ValueError:
            amt = 0

        # Trò chơi chọn mặt xúc xắc X5 (D 4 50000)
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
                    u["wager_remaining"] = max(0.0, u.get("wager_remaining", 0.0) - amt_dice)
                    weekly_wager_stats[user_id] = weekly_wager_stats.get(user_id, 0.0) + amt_dice
                    await xu_ly_chon_mat_xucxac(update, context, user_id, target_face, amt_dice)
                    return
            except:
                pass

        # Tài Xỉu hoặc Chẵn Lẻ
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
                u["wager_remaining"] = max(0.0, u.get("wager_remaining", 0.0) - amt)
                weekly_wager_stats[user_id] = weekly_wager_stats.get(user_id, 0.0) + amt
                u["cashback_fund"] += amt * 0.008
                
                if cmd in ["T", "TAI"]: choice = "tai"
                elif cmd in ["X", "XIU"]: choice = "xiu"
                elif cmd in ["C", "CHAN"]: choice = "chan"
                else: choice = "le"

                await xu_ly_quay_taixiu_tu_dong(update, context, user_id, choice, amt)
                return

        # Bầu Cua
        map_linh_vat = {"BAU": "bau", "CUA": "cua", "TOM": "tom", "CA": "ca", "GA": "ga", "NAI": "nai"}
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
                u["wager_remaining"] = max(0.0, u.get("wager_remaining", 0.0) - total_bet)
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
            f"🌸 **CHƯƠNG TRÌNH GIỚI THIỆU BẠN BÈ**\n\n🔗 Link:\n`{ref_link}`", parse_mode="Markdown"
        )

    elif text == "🏆 BXH":
        await hien_thi_bxh_dep(update)

    elif text == "👑 VIP":
        u = users_data[user_id]
        vip_lvl = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0))
        await update.message.reply_text(f"👑 **CẤP ĐỘ VIP**\nCấp hiện tại: **VIP {vip_lvl}** / Max VIP 11\n*(Yêu cầu nạp & cược tăng gấp đôi mỗi cấp)*", parse_mode="Markdown")

    elif text == "🔎 Lệnh":
        await update.message.reply_text(
            "🔎 **DANH MỤC LỆNH:**\n"
            "• `T [số]` hoặc `X [số]` - Cược Tài/Xỉu (Min 10k)\n"
            "• `C [số]` hoặc `L [số]` - Cược Chẵn/Lẻ (Min 10k)\n"
            "• `D [mặt_1-6] [số]` - Chọn mặt xúc xắc X5\n"
            "• `BAU [số] CUA [số]` - Đánh Bầu Cua\n"
            "• `/nap [số]` - Nạp tiền (STK duy nhất: `6314072009`)\n"
            "• `/check [ID]` - QTV tra cứu thành viên",
            parse_mode="Markdown"
        )

async def send_user_dashboard(update: Update, user_id: int):
    u = users_data[user_id]
    vip_lvl = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0))
    keyboard = [
        [InlineKeyboardButton("🎲 Game Tài Xỉu & Chẵn Lẻ", callback_data="choi_taixiu"), InlineKeyboardButton("🦀 Game Bầu Cua", callback_data="choi_baucua")],
        [InlineKeyboardButton("🎧 CSKH Hỗ Trợ 24/7", url="https://t.me/cskhtelevip")],
        [InlineKeyboardButton("🏆 Bảng Xếp Hạng", callback_data="xem_bxh")]
    ]
    chat_obj = update.message if update.message else update.callback_query.message
    await chat_obj.reply_text(
        f"【**TKGame**】\n\n"
        f"🆔 ID: `{u['custom_id']}` (Tele ID: `{user_id}`)\n"
        f"👑 **VIP {vip_lvl}** | 💰 Ví TK: `{u['balance']:,.0f}` điểm\n"
        f"🏦 STK Duy Nhất: `{SINGLE_BANK_INFO['stk']}` ({SINGLE_BANK_INFO['name']})\n\n"
        f"💡 *Gõ lệnh nạp:* `/nap [số_tiền]` (Hỗ trợ KM 135%) 🔽",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def hien_thi_menu_nap(update: Update):
    keyboard = [
        [InlineKeyboardButton("💳 Nạp Chuyển Khoản BANK", callback_data="nap_bank")],
        [InlineKeyboardButton("🟢 Nạp Qua ZaloPay (QR)", callback_data="nap_zalopay")],
        [InlineKeyboardButton("🔙 Quay lại", callback_data="menu_chinh")]
    ]
    chat_obj = update.message if update.message else update.callback_query.message
    await chat_obj.reply_text(
        f"📥 **CHỌN PHƯƠNG THỨC NẠP TIỀN**\n"
        f"• STK Nhận Tiền Duy Nhất: `{SINGLE_BANK_INFO['stk']}` ({SINGLE_BANK_INFO['name']})\n"
        f"• Có hỗ trợ tùy chọn **Khuyến Mãi 135%** (x1 tiền nạp và x1 tiền KM vào vòng cược yêu cầu).\n\n"
        f"💡 Hoặc gõ lệnh nhanh: `/nap [số_tiền]`",
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
    
    winning_tx = "tai" if tong >= 11 else "xiu"
    winning_cl = "chan" if tong % 2 == 0 else "le"

    is_win = False
    if choice in ["tai", "xiu"]: is_win = (choice == winning_tx)
    else: is_win = (choice == winning_cl)

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
# 5. GIAO DIỆN BẢNG XẾP HẠNG & NẠP RÚT ĐẶC BIỆT
# =========================
async def hien_thi_bxh_dep(update: Update):
    today_str = datetime.now().strftime("%Y-%m-%d")
    bxh_text = (
        f"🔥 **Chuỗi thắng**\n"
        f"🥇 **BXH hôm nay**\n"
        f"📅 **Ngày: {today_str}**\n"
        f"🔥 Trạng thái: cập nhật liên tục · chốt lúc 23:55 mỗi ngày[span_17](start_span)[span_17](end_span)\n\n"
        f"Tính chuỗi thắng/thua dài nhất trong ngày; tất cả nhóm game cộng lại · mỗi lệnh $\\ge$ 5.000 · cần đã nạp mới tính hạng; lệnh nhỏ hơn bỏ qua (không cắt chuỗi)[span_18](start_span)[span_18](end_span).\n\n"
        f"🟤 **Top 10**\n"
        f"🥇 `*****72771` · 11 ván · 🧧 **20.000**[span_19](start_span)[span_19](end_span)\n"
        f"🥈 `*****08433` · 8 ván · 🧧 **10.000**[span_20](start_span)[span_20](end_span)\n"
        f"🥉 `*****59087` · 6 ván · 🧧 **5.000**[span_21](start_span)[span_21](end_span)\n"
        f"4. `*****53249` · 6 ván[span_22](start_span)[span_22](end_span)\n"
        f"5. `*****13100` · 5 ván[span_23](start_span)[span_23](end_span)\n"
        f"6. `*****11187` · 5 ván[span_24](start_span)[span_24](end_span)\n"
        f"7. `*****01421` · 5 ván[span_25](start_span)[span_25](end_span)\n"
        f"8. `*****30888` · 5 ván[span_26](start_span)[span_26](end_span)\n"
        f"9. `*****23724` · 5 ván[span_27](start_span)[span_27](end_span)\n"
        f"10. `*****66779` · 4 ván[span_28](start_span)[span_28](end_span)\n\n"
        f"🆔 **Thành tích của bạn**\n"
        f"• Hôm nay chưa có thành tích tính vào bảng[span_29](start_span)[span_29](end_span)\n\n"
        f"💡 Số liệu cộng dồn đến 23:55, bấm «Làm mới» để xem hạng mới nhất[span_30](start_span)[span_30](end_span)."
    )
    keyboard = [
        [InlineKeyboardButton("🔄 Làm mới", callback_data="refresh_bxh"), InlineKeyboardButton("📅 Hôm qua", callback_data="bxh_yesterday")],
        [InlineKeyboardButton("🏆 BXH cược", callback_data="bxh_cuoc"), InlineKeyboardButton("💲 BXH nạp", callback_data="bxh_nap")],
        [InlineKeyboardButton("🔥 Nhận thưởng chuỗi", callback_data="nhan_thuong_chuoi")]
    ]
    chat_obj = update.message if update.message else update.callback_query.message
    await chat_obj.reply_text(bxh_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

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
    # Sinh mã giao dịch riêng biệt cho từng người nạp
    unique_note_code = f"TK{random.randint(100000, 999999)}"
    order_id = f"NAP{random.randint(10000,99999)}"
    
    pending_orders[order_id] = {
        "user_id": user_id, "amount": amount, "note_code": unique_note_code,
        "name": u["name"], "custom_id": u["custom_id"], "admin_status": "pending"
    }

    nap_text = (
        f"💳 **HƯỚNG DẪN NẠP ĐIỂM (#{order_id})**\n"
        f"🏦 Ngân hàng: *MSB* | STK Duy Nhất: `{SINGLE_BANK_INFO['stk']}`\n"
        f"👤 Chủ TK: *{SINGLE_BANK_INFO['chủ tài khoản']}*\n"
        f"💰 Số tiền: `{amount:,}` VNĐ\n"
        f"📝 **Nội dung chuyển khoản (Bắt buộc):** `{unique_note_code}`\n\n"
        f"🎁 *Lưu ý:* Hệ thống hỗ trợ khuyến mãi **135%** (x1 tiền nạp và x1 tiền khuyến mãi vào vòng cược). Sau khi chuyển khoản, bấm nút dưới để báo duyệt!"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Nhận KM 135%", callback_data=f"km_yes_{order_id}"), InlineKeyboardButton("❌ Không KM", callback_data=f"km_no_{order_id}")]
    ]
    await update.message.reply_text(nap_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

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

    u = users_data[user_id]
    # Kiểm tra điều kiện rút lần đầu: Đã nạp tối thiểu 50k và hoàn thành x1 vòng cược
    if not u.get("has_deposited_50k", False) or u.get("total_deposited", 0) < 50000:
        await update.message.reply_text("❌ Rút tiền lần đầu yêu cầu bạn phải nạp tích lũy tối thiểu **50.000đ**!", parse_mode="Markdown")
        return
    if u.get("wager_remaining", 0.0) > 0:
        await update.message.reply_text(f"❌ Bạn còn thiếu `{u['wager_remaining']:,.0f}` điểm cược để hoàn thành x1 vòng cược yêu cầu trước khi rút!", parse_mode="Markdown")
        return

    if amount < 30000 or u["balance"] < amount:
        await update.message.reply_text("❌ Số dư không đủ hoặc dưới mức tối thiểu 30.000!", parse_mode="Markdown")
        return

    u["balance"] -= amount
    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Rút {amount:,} về {bank_code} ({stk})")
    await update.message.reply_text(f"✅ Gửi yêu cầu rút `{amount:,}` về `{bank_code}` thành công!", parse_mode="Markdown")

async def check_user_by_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await an_lenh_admin(update)
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    if not context.args:
        await update.message.reply_text("⚠️ Cú pháp: `/check [Telegram_ID]`", parse_mode="Markdown")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
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
        f"📤 Tổng cược: `{u.get('total_wagered', 0):,.0f}` điểm\n"
        f"⏳ Vòng cược còn lại: `{u.get('wager_remaining', 0):,.0f}` điểm"
    )
    await update.message.reply_text(info_text, parse_mode="Markdown")

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
    elif data == "xem_bxh":
        await hien_thi_bxh_dep(query)
    elif data == "nap_bank":
        await query.message.reply_text(
            f"💳 **NẠP QUA CHUYỂN KHOẢN BANK**\n"
            f"• STK Duy Nhất: `{SINGLE_BANK_INFO['stk']}` ({SINGLE_BANK_INFO['name']})\n"
            f"• Chủ TK: `{SINGLE_BANK_INFO['chủ tài khoản']}`\n\n"
            f"💡 Vui lòng gõ lệnh: `/nap [số_tiền]` để tạo mã giao dịch.", parse_mode="Markdown"
        )
    elif data == "nap_zalopay":
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=ZALOPAY_QR_URL,
            caption=(
                f"🟢 **QUÉT MÃ QR ZALOPAY NẠP TIỀN**\n"
                f"• STK Nhận: `{SINGLE_BANK_INFO['stk']}` ({SINGLE_BANK_INFO['name']})\n"
                f"• Chủ TK: `{SINGLE_BANK_INFO['chủ tài khoản']}`\n\n"
                f"💡 Gõ lệnh `/nap [số_tiền]` để lấy mã nội dung nạp ghi chú chính xác!"
            ),
            parse_mode="Markdown"
        )
    elif data.startswith("km_yes_") or data.startswith("km_no_"):
        parts = data.split("_")
        action, order_id = parts[1], parts[2]
        if order_id in pending_orders:
            info = pending_orders[order_id]
            use_km = (action == "yes")
            info["use_km"] = use_km
            
            noti_text = (
                f"🔔 **DUYỆT NẠP TIỀN (#{order_id})**\n"
                f"Khách: **{info['name']}** (`{info['custom_id']}`)\n"
                f"Số tiền: `{info['amount']:,}` | KM 135%: `{'Có' if use_km else 'Không'}`\n"
                f"📝 Nội dung CK: `{info['note_code']}`"
            )
            targets = {MASTER_ADMIN_ID} | sub_admins
            for tid in targets:
                try:
                    kb = [[
                        InlineKeyboardButton("✅ Duyệt", callback_data=f"nap_yes_{order_id}"),
                        InlineKeyboardButton("❌ Từ chối", callback_data=f"nap_no_{order_id}")
                    ]]
                    await context.bot.send_message(chat_id=tid, text=noti_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
                except:
                    pass
            await query.edit_message_text(text=f"✅ Đã tạo lệnh nạp! Vui lòng chuyển khoản với nội dung: `{info['note_code']}`", parse_mode="Markdown")
    elif data.startswith("nap_yes_"):
        if not is_admin(user_id): return
        order_id = data.replace("nap_yes_", "")
        if order_id in pending_orders:
            order = pending_orders[order_id]
            order["admin_status"] = "processed"
            target_id = order["user_id"]
            amount = order["amount"]
            use_km = order.get("use_km", False)
            
            final_cred = amount * (2.35 if use_km else 1.0)
            req_wager = final_cred # x1 vòng cược tổng tiền
            
            if target_id in users_data:
                users_data[target_id]["balance"] += final_cred
                users_data[target_id]["total_deposited"] += amount
                users_data[target_id]["has_deposited_50k"] = True
                users_data[target_id]["wager_remaining"] = users_data[target_id].get("wager_remaining", 0.0) + req_wager
            
            try:
                await context.bot.send_message(
                    chat_id=target_id, 
                    text=f"🎉 Nạp thành công `+{final_cred:,.0f}` điểm! (Đã cộng KM 135%: `{'Có' if use_km else 'Không'}`). Yêu cầu x1 vòng cược: `{req_wager:,.0f}` điểm.", 
                    parse_mode="Markdown"
                )
            except:
                pass
            await query.edit_message_text(text=f"✅ **Đã duyệt đơn nạp #{order_id}!**")
    elif data.startswith("nap_no_"):
        if not is_admin(user_id): return
        order_id = data.replace("nap_no_", "")
        if order_id in pending_orders:
            pending_orders[order_id]["admin_status"] = "processed"
            await query.edit_message_text(text=f"❌ Đã từ chối đơn #{order_id}.")


# =========================
# 6. MAIN KHỞI CHẠY
# =========================
def main():
    if not TOKEN:
        raise RuntimeError("Chưa cấu hình BOT_TOKEN.")

    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["sd", "tk"], send_user_dashboard))
    app.add_handler(CommandHandler("nap", menu_nap))
    app.add_handler(CommandHandler("rutbank", menu_rut_bank))
    app.add_handler(CommandHandler("rut", menu_rut_bank))
    app.add_handler(CommandHandler("check", check_user_by_admin))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 TKGame Bot đã cập nhật hoàn tất STK 6314072009, KM 135%, rút 50k x1 vòng cược, BXH đẹp và mã giao dịch riêng...")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
