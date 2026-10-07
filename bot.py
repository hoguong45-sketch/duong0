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
    "✅ TienPhong Bank => `TPB`\n"
    "✅ SHB bank => `SHB`\n"
    "✅ ACB => `ACB`\n"
    "✅ Maritime Bank => `MSB`\n"
    "✅ VIB => `VIB`\n"
    "✅ Sacombank => `STB`\n"
    "✅ VP Bank => `VPB`\n"
    "✅ SeaBank => `SEAB`\n"
    "✅ Shinhan bank Việt Nam => `SHBVN`\n"
    "✅ Eximbank => `EIB`\n"
    "✅ KienLong Bank => `KLB`\n"
    "✅ Dong A Bank => `DAB`\n"
    "✅ HD Bank => `HDB`\n"
    "✅ LienVietPostBank => `LPB`\n"
    "✅ VietBank => `VBB`\n"
    "✅ ABBANK => `ABB`\n"
    "✅ PG Bank => `PGB`\n"
    "✅ PVComBank => `PVC`\n"
    "✅ Bac A Bank => `BAB`\n"
    "✅ Sai Gon Commercial Bank => `SCB`\n"
    "✅ BanVietBank => `VCCB`\n"
    "✅ Saigonbank => `SGB`\n"
    "✅ Bao Viet Bank => `BVB`\n"
    "✅ Orient Commercial Bank => `OCB`\n\n"
    "💡 **Cú pháp rút tiền ngân hàng:**\n"
    "`/rutbank [Số_tiền] [Mã_NH] [STK] [Tên_chủ_khoản]`\n"
    "*(Ví dụ: `/rutbank 50000 VCB 0776876883 NGUYEN VAN A`)*"
)

SYSTEM_BANK_LIST = [
    {"name": "MSB", "stk": "6314072009", "chủ tài khoản": "TKGAME AUTO SYSTEM"},
    {"name": "MBBank", "stk": "0776876883", "chủ tài khoản": "TKGAME AUTO SYSTEM"}
]

def tinh_vip(deposited, wagered):
    """Tính cấp bậc VIP từ VIP 1 đến VIP 11"""
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
            "balance": 50000.0,
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
                            text="🎉 Chúc mừng! Bạn vừa mời thành công 1 bạn mới và nhận thưởng `3.000` điểm!",
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

    # XỬ LÝ CÚ PHÁP ĐẶT CƯỢC TÀI XỈU NHANH (T 10000 / X 20000)
    parts = text.split()
    if len(parts) >= 2:
        cmd = parts[0].upper()
        try:
            amt = int(parts[1])
        except ValueError:
            amt = 0

        if amt >= 10000:
            if user_id not in users_data or users_data[user_id].get("step") != "active":
                await update.message.reply_text("⚠️ Vui lòng gõ `/start` và đăng ký tài khoản trước!")
                return
            
            u = users_data[user_id]
            if cmd in ["T", "TAI", "X", "XIU"]:
                if u["balance"] < amt:
                    await update.message.reply_text("❌ Số dư ví không đủ để đặt cược!", parse_mode="Markdown")
                    return
                u["balance"] -= amt
                u["total_wagered"] = u.get("total_wagered", 0.0) + amt
                weekly_wager_stats[user_id] = weekly_wager_stats.get(user_id, 0.0) + amt
                u["cashback_fund"] += amt * 0.008
                
                choice = "tai" if cmd in ["T", "TAI"] else "xiu"
                await xu_ly_quay_taixiu_tu_dong(update, context, user_id, choice, amt)
                return

        # XỬ LÝ ĐẶT CƯỢC BẦU CUA 1 HOẶC NHIỀU CON (VD: Nai 30000 hoặc Bau 10000 Cua 20000)
        map_linh_vat = {
            "B": "bau", "BAU": "bau", "C": "cua", "CUA": "cua", 
            "T": "tom", "TOM": "tom", "CA": "ca", 
            "G": "ga", "GA": "ga", "N": "nai", "NAI": "nai"
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
            [InlineKeyboardButton("🎲 Game Tài Xỉu (Min 10k)", callback_data="choi_taixiu"), InlineKeyboardButton("🦀 Game Bầu Cua (Min 10k)", callback_data="choi_baucua")],
            [InlineKeyboardButton("🎧 CSKH Hỗ Trợ 24/7", url="https://t.me/cskhtelevip")],
            [InlineKeyboardButton("🎡 Vòng quay", callback_data="vong_quay")]
        ]
        await update.message.reply_text("🎮 **SẢNH TRÒ CHƠI TKGAME (CHƠI TỰ ĐỘNG 1-1)**\nChọn trò chơi bên dưới hoặc gõ lệnh cược nhanh (VD: `T 10000`, `Nai 30000`, `Bau 10000 Cua 20000`):", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    
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
            "• `T [số_tiền]` hoặc `X [số_tiền]` - Cược Tài Xỉu (Min 10k)\n"
            "• `[LinhVật] [số_tiền]` - Đánh Bầu Cua (VD: `Nai 30000` hoặc `Bau 10k Cua 20k`)\n"
            "• `/sd` - Kiểm tra ví & VIP\n"
            "• `/nap [số_tiền]` - Nạp điểm\n"
            "• `/rutbank` - Rút tiền ngân hàng\n"
            "• `/code [MÃ]` - Nhập mã thưởng\n"
            "• `/ht` - Nhận hoàn trả 0.8%",
            parse_mode="Markdown"
        )

async def send_user_dashboard(update: Update, user_id: int):
    u = users_data[user_id]
    vip_lvl = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0))
    keyboard = [
        [InlineKeyboardButton("🎲 Game Tài Xỉu (Min 10k)", callback_data="choi_taixiu"), InlineKeyboardButton("🦀 Game Bầu Cua (Min 10k)", callback_data="choi_baucua")],
        [InlineKeyboardButton("🎧 CSKH Hỗ Trợ 24/7", url="https://t.me/cskhtelevip")],
        [InlineKeyboardButton("🎡 Vòng quay", callback_data="vong_quay")]
    ]
    chat_obj = update.message if update.message else update.callback_query.message
    await chat_obj.reply_text(
        f"【**TKGame**】\n\n"
        f"🆔 ID: `{u['custom_id']}` | 👑 **VIP {vip_lvl}**\n"
        f"💰 Ví TK: `{u['balance']:,.0f}` điểm\n\n"
        f"💡 *Gõ lệnh cược nhanh: `T 10000`, `Nai 30000`, `Bau 10000 Cua 20000`* 🔽",
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
# 4. HỆ THỐNG KẾT QUẢ ĐÚNG CHUẨN KHUNG MẪU & XÚC XẮC TELEGRAM
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
    is_win = (choice == winning_tx)
    
    total_thang = 0.0
    u = users_data[user_id]
    if is_win:
        total_thang = amt * 1.97
        u["balance"] += total_thang
        ket_qua_str = f"Chiến thắng - +{total_thang:,.0f}đ"
        u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thắng TX: +{total_thang:,.0f}đ")
    else:
        ket_qua_str = f"Thua cuộc - -{amt:,}đ"
        u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thua TX: -{amt:,}đ")

    msg = (
        f"┏━━━━━━━━━━━━━┓\n"
        f"┣➤ Trò chơi: Tài Xỉu\n"
        f"┣➤ Kết quả: {d1} + {d2} + {d3} = {tong}\n"
        f"┣➤ Cửa đặt : {choice.upper()}\n"
        f"┣➤ Mã giao dịch: {ma_gd}\n"
        f"┣➤ Tiền cược: {amt:,.0f}đ\n"
        f"┣➤ Nội dung: {choice.lower()}\n"
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
        await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        await asyncio.sleep(1.2)
    except:
        pass

    linh_vat_map = {
        "bau": ("Bầu", "🎃"), "cua": ("Cua", "🦀"), "tom": ("Tôm", "🦐"),
        "ca": ("Cá", "🐟"), "ga": ("Gà", "🐓"), "nai": ("Nai", "🦌")
    }
    keys = list(linh_vat_map.keys())
    r1, r2, r3 = random.choices(keys, k=3)
    drawn = [r1, r2, r3]

    tong_thuong = 0.0
    chi_tiet_cua = []
    for c_key, c_amt in bets:
        count = drawn.count(c_key)
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
        f"┣➤ Kết quả: {linh_vat_map[r1][1]} {linh_vat_map[r2][1]} {linh_vat_map[r3][1]}\n"
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
# 5. RÚT NGÂN HÀNG, NẠP, CODE & ADMIN
# =========================
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
        await update.message.reply_text("⚠️ Sai cú pháp! Xem lại danh sách bằng lệnh `/rutbank`", parse_mode="Markdown")
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
    await update.message.reply_text(
        f"✅ **Gửi yêu cầu rút tiền thành công, vui lòng chờ vài phút!**\n\n"
        f"🏦 Ngân hàng: `{bank_code}`\n"
        f"💳 STK: `{stk}`\n"
        f"👤 Chủ TK: `{chủ_tk}`\n"
        f"💰 Số tiền: `{amount:,}` điểm",
        parse_mode="Markdown"
    )

async def xem_lich_su(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data:
        return
    u = users_data[user_id]
    hist = u.get("history_action", [])
    text = "📜 **LỊCH SỬ GIAO DỊCH & CƯỢC**\n\n"
    text += "\n".join(hist[-10:]) if hist else "Chưa có giao dịch."
    await update.message.reply_text(text, parse_mode="Markdown")

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

async def lenh_nhận_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        await update.message.reply_text(f"✅ Đã cấp quyền Quản Trị Viên cho ID: `{mod_id}`")
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
        await update.message.reply_text(f"✅ Đã cấp quyền Nhân Viên CSKH cho ID: `{staff_id}`")
    except ValueError:
        pass

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
        await update.message.reply_text(f"🏷 Chức vụ của bạn: **{role_title}**\n⚠ Chưa đăng ký tài khoản! Gõ `/start`.")
        return
        
    u = users_data[user_id]
    vip_lvl = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0))
    await update.message.reply_text(
        f"🏷 Chức vụ: **{role_title}** | 👑 **VIP {vip_lvl}**\n"
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

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data in ["menu_chinh", "tai_khoan"]:
        await send_user_dashboard(query, user_id)
    elif data == "choi_taixiu":
        await query.message.reply_text("🎲 Gõ nhanh: `T [số_tiền]` hoặc `X [số_tiền]` (Min 10k)", parse_mode="Markdown")
    elif data == "choi_baucua":
        await query.message.reply_text("🦀 Gõ nhanh: `Nai 30000` hoặc `Bau 10000 Cua 20000` (Min 10k)", parse_mode="Markdown")
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
                    kb = [[InlineKeyboardButton("✅ Duyệt", callback_data=f"nap_yes_{order_id}"), InlineKeyboardButton("❌ Từ chối", callback_data=f"nap_no_{order_id}")]
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
    app.add_handler(CommandHandler("ht", nhan_hoantra))
    app.add_handler(CommandHandler("ls", xem_lich_su))
    app.add_handler(CommandHandler("top", top_cuoc_tuan))

    app.add_handler(CommandHandler("admin", lenh_nhận_admin))
    app.add_handler(CommandHandler("taocode", tao_code))
    app.add_handler(CommandHandler("themmod", them_mod))
    app.add_handler(CommandHandler("themcskh", them_cskh))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 TKGame Bot đã cập nhật hoàn toàn giữ nguyên mọi tính năng cũ và bổ sung kết quả chuẩn khung mẫu, bầu cua nhiều con, hệ thống VIP 1-11...")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
