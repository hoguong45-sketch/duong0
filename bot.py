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
            <option value="con">CON (PLAYER)</option>
            <option value="cai">CÁI (BANKER)</option>
            <option value="hoa">HOÀ (TIE)</option>
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
    
    vip_lvl = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0))
    cashback_rate = 0.008 + (vip_lvl * 0.002)
    u["cashback_fund"] += amount * cashback_rate
    
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
referral_counts = {} 
gift_codes = {"VIP2026": 50000, "TET2026": 100000, "TANTHU": 5000}
gift_code_limits = {"TANTHU": 99999} 
used_code_users = set() # Quản lý người dùng đã dùng giftcode nào

phien_id = 31180
jackpot_pool = 294016.0  
phien_baccarat_id = 46120

weekly_wager_stats = {} 
pending_orders = {}

SINGLE_BANK_INFO = {
    "name": "MSB", 
    "stk": "6314072009", 
    "chủ tài khoản": "TKGAME AUTO SYSTEM"
}

BANK_QR_URL = "https://images.unsplash.com/photo-1559526324-4b87b5e36e44?q=80&w=800&auto=format&fit=crop"

WITHDRAW_GUIDE_TEXT = (
    "⚠️ **Lưu ý:** Không hỗ trợ hoàn tiền nếu bạn nhập sai thông tin Tài khoản.\n\n"
    "🎀 **MOMO**\n"
    "`/rutmomo [số Momo] [số tiền cần rút]`\n"
    "💡 VD: `/rutmomo 0987654321 100000`\n\n"
    "🏦 **BANK**\n"
    "`/rutbank [số tiền cần rút] [mã ngân hàng] [số TK] [Tên TK không dấu]`\n"
    "💡 VD: `/rutbank 100000 VCB 0123456789 Tran Van B`\n\n"
    "📌 Số tiền rút tối thiểu là **50.000đ** đối với Momo và **50.000đ** đối với Bank.\n\n"
    "📋 **TÊN NGÂN HÀNG - MÃ NGÂN HÀNG:**\n"
    "✅ Vietcombank => `VCB` | ✅ BIDV => `BIDV`\n"
    "✅ Vietinbank => `VTB` | ✅ Techcombank => `TCB`\n"
    "✅ MB Bank => `MB` | ✅ Agribank => `AGR`\n"
    "✅ TienPhong Bank => `TPB` | ✅ SHB bank => `SHB`\n"
    "✅ ACB => `ACB` | ✅ Maritime Bank => `MSB`\n"
    "✅ VIB => `VIB` | ✅ Sacombank => `STB`\n"
    "✅ VP Bank => `VPB` | ✅ SeaBank => `SEAB`\n"
    "✅ Shinhan bank => `SHBVN` | ✅ Eximbank => `EIB`\n"
    "✅ KienLong Bank => `KLB` | ✅ Dong A Bank => `DAB`\n"
    "✅ HD Bank => `HDB` | ✅ LienVietPostBank => `LPB`\n"
    "✅ VietBank => `VBB` | ✅ ABBANK => `ABB`\n"
    "✅ PG Bank => `PGB` | ✅ PVComBank => `PVC`\n"
    "✅ Bac A Bank => `BAB` | ✅ SCB => `SCB`\n"
    "✅ BanVietBank => `VCCB` | ✅ Saigonbank => `SGB`\n"
    "✅ Bao Viet Bank => `BVB` | ✅ Orient Commercial Bank => `OCB`"
)

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

def get_vip_requirements(level):
    base_dep = 500.0
    base_wag = 2000000.0
    if level >= 11:
        return 0, 0
    req_dep = base_dep * (2 ** level)
    req_wag = base_wag * (2 ** level)
    return req_dep, req_wag

def is_master_admin(user_id):
    return user_id == MASTER_ADMIN_ID or user_id in sub_admins

def is_admin(user_id):
    return user_id == MASTER_ADMIN_ID or user_id in sub_admins

def is_cskh(user_id):
    return user_id == MASTER_ADMIN_ID or user_id in sub_admins or user_id in cskh_staffs

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
        [KeyboardButton("🎧 CSKH"), KeyboardButton("🏆 BXH")],
        [KeyboardButton("👑 VIP"), KeyboardButton("🔎 Lệnh")]
    ],
    resize_keyboard=True
)


# =========================
# 3. LỆNH START & GIAO DIỆN CHÍNH
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if context.args and context.args[0].startswith("ref_"):
        try:
            ref_id = int(context.args[0].replace("ref_", ""))
            if ref_id != user_id and ref_id in users_data:
                referral_counts[ref_id] = referral_counts.get(ref_id, 0) + 1
        except:
            pass

    if user_id not in users_data or users_data[user_id].get("step") != "active":
        users_data[user_id] = {
            "step": "waiting_name",
            "custom_id": f"{random.randint(10000000,99999999)}",
            "balance": 5000.0,  
            "ref_balance": 0.0, 
            "cashback_fund": 0.0,
            "total_deposited": 0.0,
            "total_wagered": 0.0,
            "has_deposited_50k": False,
            "wager_remaining": 0.0,
            "history_action": [f"[{datetime.now().strftime('%d/%m %H:%M')}] Tặng thưởng tân thủ: +5,000đ"]
        }

        welcome_img_url = "https://images.unsplash.com/photo-1596838132731-3301c3fd4317?q=80&w=1000&auto=format&fit=crop"
        intro_text = (
            "✨ **CHÀO MỪNG ĐẾN VỚI TKGAME - TẶNG NGAY 5.000Đ KHI VÀO CHƠI** ✨\n\n"
            "🏰 **VỀ CHÚNG TÔI & CAM KẾT VÀNG:**\n"
            "• 💯 **Uy tín tuyệt đối:** Hệ thống tự động 100%, nạp rút siêu tốc trong 30 giây.\n"
            "• 🛡️ **Minh bạch công khai:** Kết quả xúc xắc hoàn toàn ngẫu nhiên bằng công nghệ chuẩn Telegram (Dice API).\n\n"
            "💡 Vui lòng nhập **Họ và Tên trùng với Tài Khoản Ngân Hàng** bên dưới để kích hoạt tài khoản:"
        )
        await update.message.reply_photo(photo=welcome_img_url, caption=intro_text, parse_mode="Markdown")
        return

    await send_user_dashboard(update, user_id)

async def set_master_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    sub_admins.add(user_id)
    await update.message.reply_text("👑 Bạn đã được cấp quyền **Admin Tối Cao** thành công!", parse_mode="Markdown")

async def add_qtv_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Bạn không có quyền sử dụng lệnh này!")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Cú pháp: `/themqtv [Telegram_ID]`", parse_mode="Markdown")
        return
    try:
        new_qtv = int(context.args[0])
        sub_admins.add(new_qtv)
        name_str = users_data.get(new_qtv, {}).get("name", "QTV")
        await update.message.reply_text(f"✅ Đã thêm QTV **{name_str}** (ID: `{new_qtv}`) thành công!", parse_mode="Markdown")
    except:
        await update.message.reply_text("⚠️ ID không hợp lệ!")

async def add_cskh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Bạn không có quyền sử dụng lệnh này!")
        return
    if not context.args:
        await update.message.reply_text("⚠️ Cú pháp: `/themcskh [Telegram_ID]`", parse_mode="Markdown")
        return
    try:
        new_cskh = int(context.args[0])
        cskh_staffs.add(new_cskh)
        name_str = users_data.get(new_cskh, {}).get("name", "CSKH")
        await update.message.reply_text(f"✅ Đã thêm CSKH **{name_str}** (ID: `{new_cskh}`) thành công!", parse_mode="Markdown")
    except:
        await update.message.reply_text("⚠️ ID không hợp lệ!")

# =========================
# TÍNH NĂNG TẠO GIFTCODE RIÊNG CHO ADMIN & NHẬP CODE
# =========================
async def admin_tao_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await an_lenh_admin(update)
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    
    if len(context.args) < 3:
        await update.message.reply_text("⚠️ Cú pháp Admin: `/taocode [MÃ] [số_tiền] [số_lượt]`", parse_mode="Markdown")
        return
    
    code_name = context.args[0].upper()
    try:
        amount = float(context.args[1])
        limit_uses = int(context.args[2])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền hoặc số lượt không hợp lệ!")
        return

    gift_codes[code_name] = amount
    gift_code_limits[code_name] = limit_uses
    
    await update.message.reply_text(
        f"🎁 **TẠO GIFTCODE THÀNH CÔNG**\n\n"
        f"• Mã: `{code_name}`\n"
        f"• Giá trị: `{amount:,.0f}` điểm\n"
        f"• Số lượt dùng: `{limit_uses}` lượt",
        parse_mode="Markdown"
    )

async def user_nhap_code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` và đăng ký tài khoản trước!")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Cú pháp: `/nhapcode [MÃ_CODE]`", parse_mode="Markdown")
        return

    code_name = context.args[0].upper()
    if code_name not in gift_codes:
        await update.message.reply_text("❌ Mã quà tặng không tồn tại hoặc đã hết hạn!", parse_mode="Markdown")
        return

    user_code_key = f"{user_id}_{code_name}"
    if user_code_key in used_code_users:
        await update.message.reply_text("❌ Bạn đã sử dụng mã quà tặng này rồi!", parse_mode="Markdown")
        return

    current_uses = gift_code_limits.get(code_name, 0)
    if current_uses <= 0:
        await update.message.reply_text("❌ Mã quà tặng này đã hết lượt sử dụng!", parse_mode="Markdown")
        return

    reward_amt = gift_codes[code_name]
    gift_code_limits[code_name] = current_uses - 1
    used_code_users.add(user_code_key)

    u = users_data[user_id]
    u["balance"] += reward_amt
    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Nhập giftcode {code_name}: +{reward_amt:,.0f}đ")

    await update.message.reply_text(f"🎉 Chúc mừng! Bạn đã nhận thành công `+{reward_amt:,.0f}` điểm từ mã `{code_name}`!", parse_mode="Markdown")


async def admin_panel_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    if not users_data:
        await update.message.reply_text("⚠️ Chưa có người chơi nào trong hệ thống.")
        return
    
    keyboard = []
    for uid, u in users_data.items():
        btn_text = f"{u.get('name', 'User')} | ID: {u['custom_id']} | {u['balance']:,.0f}đ"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"adm_detail_{uid}")])
    
    await update.message.reply_text("👑 **QUẢN LÝ TÀI KHOẢN NGƯỜI CHƠI**\nBấm vào tài khoản bất kỳ để tuỳ chỉnh:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

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

        if cmd in ["CON", "CAI", "HOA"] and amt >= 10000:
            if user_id not in users_data or users_data[user_id].get("step") != "active":
                await update.message.reply_text("⚠️ Vui lòng gõ `/start` và đăng ký tài khoản trước!")
                return
            u = users_data[user_id]
            if u["balance"] < amt:
                await update.message.reply_text("❌ Số dư ví không đủ để đặt cược Baccarat!", parse_mode="Markdown")
                return
            u["balance"] -= amt
            u["total_wagered"] = u.get("total_wagered", 0.0) + amt
            u["wager_remaining"] = max(0.0, u.get("wager_remaining", 0.0) - amt)
            weekly_wager_stats[user_id] = weekly_wager_stats.get(user_id, 0.0) + amt
            
            old_vip = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0) - amt)
            new_vip = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0))
            if new_vip > old_vip:
                try:
                    await context.bot.send_message(chat_id=user_id, text=f"🎉 **CHÚC MỪNG!** Bạn đã thăng hạng thành công lên **VIP {new_vip}**!", parse_mode="Markdown")
                except:
                    pass

            vip_lvl = new_vip
            cashback_rate = 0.008 + (vip_lvl * 0.002)
            u["cashback_fund"] += amt * cashback_rate

            choice_map = {"CON": "con", "CAI": "cai", "HOA": "hoa"}
            await xu_ly_quay_baccarat(update, context, user_id, choice_map[cmd], amt)
            return

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
                
                old_vip = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0) - amt)
                new_vip = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0))
                if new_vip > old_vip:
                    try:
                        await context.bot.send_message(chat_id=user_id, text=f"🎉 **CHÚC MỪNG!** Bạn đã thăng hạng thành công lên **VIP {new_vip}**!", parse_mode="Markdown")
                    except:
                        pass

                vip_lvl = new_vip
                cashback_rate = 0.008 + (vip_lvl * 0.002)
                u["cashback_fund"] += amt * cashback_rate
                
                if cmd in ["T", "TAI"]: choice = "tai"
                elif cmd in ["X", "XIU"]: choice = "xiu"
                elif cmd in ["C", "CHAN"]: choice = "chan"
                else: choice = "le"

                await xu_ly_quay_taixiu_tu_dong(update, context, user_id, choice, amt)
                return

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
                
                old_vip = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0) - total_bet)
                new_vip = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0))
                if new_vip > old_vip:
                    try:
                        await context.bot.send_message(chat_id=user_id, text=f"🎉 **CHÚC MỪNG!** Bạn đã thăng hạng thành công lên **VIP {new_vip}**!", parse_mode="Markdown")
                    except:
                        pass

                vip_lvl = new_vip
                cashback_rate = 0.008 + (vip_lvl * 0.002)
                u["cashback_fund"] += total_bet * cashback_rate
                
                await xu_ly_quay_baucua_nhieu_con(update, context, user_id, bets, total_bet)
                return

    if text == "🎮 Game":
        keyboard = [
            [InlineKeyboardButton("🎲 Tài Xỉu & Chẵn Lẻ", callback_data="choi_taixiu"), InlineKeyboardButton("🃏 Baccarat Xúc Xắc", callback_data="choi_baccarat")],
            [InlineKeyboardButton("🦀 Game Bầu Cua", callback_data="choi_baucua"), InlineKeyboardButton("👑 Tra Cứu VIP", callback_data="xem_vip")],
            [InlineKeyboardButton("🎧 Liên hệ CSKH", url="https://t.me/cskhtelevip")]
        ]
        await update.message.reply_text("🎮 **SẢNH TRÒ CHƠI TKGAME**\nChọn trò chơi bên dưới hoặc gõ lệnh cược nhanh:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif text == "👤 Tài khoản":
        await send_user_dashboard(update, user_id)

    elif text == "💰 Nạp":
        await hien_thi_menu_nap(update)

    elif text == "💳 Rút":
        await update.message.reply_text(WITHDRAW_GUIDE_TEXT, parse_mode="Markdown")

    elif text == "🎧 CSKH":
        await update.message.reply_text("🎧 Hỗ trợ khách hàng 24/7: https://t.me/cskhtelevip", parse_mode="Markdown")

    elif text == "🌸 Giới thiệu bạn bè":
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        await update.message.reply_text(
            f"🌸 **CHƯƠNG TRÌNH GIỚI THIỆU BẠN BÈ**\n\n🔗 Link:\n`{ref_link}`", parse_mode="Markdown"
        )

    elif text == "🏆 BXH":
        await hien_thi_bxh_dep(update)

    elif text == "👑 VIP":
        await hien_thi_thong_tin_vip(update, user_id)

    elif text == "🔎 Lệnh":
        if is_admin(user_id):
            admin_commands_text = (
                "🔎 **DANH MỤC LỆNH ADMIN & QTV:**\n"
                "• `/taocode [MÃ] [tiền] [lượt]` - Tạo Giftcode riêng Admin\n"
                "• `/themqtv [ID]` - Thêm QTV hệ thống\n"
                "• `/themcskh [ID]` - Thêm nhân viên CSKH\n"
                "• `/danhsachacc` - Quản lý toàn bộ acc (Thay đổi tên, tiền)\n"
                "• `/check [ID]` - Tra cứu chi tiết tài khoản\n"
                "• `/nap [số]` - Nạp tiền\n"
                "• `/rutbank` & `/rutmomo` - Hướng dẫn rút"
            )
            await update.message.reply_text(admin_commands_text, parse_mode="Markdown")
        else:
            await update.message.reply_text(
                "🔎 **DANH MỤC LỆNH:**\n"
                "• `/nhapcode [MÃ]` - Nhận quà từ Giftcode\n"
                "• `T [số]` hoặc `X [số]` - Cược Tài/Xỉu (Min 10k)\n"
                "• `C [số]` hoặc `L [số]` - Cược Chẵn/Lẻ (Min 10k)\n"
                "• `Con [số]` hoặc `Cai [số]` hoặc `Hoa [số]` - Cược Baccarat (Min 10k)\n"
                "• `BAU [số] CUA [số]` - Đánh Bầu Cua\n"
                "• `/nap [số]` - Nạp tiền\n"
                "• `/rutbank` hoặc `/rutmomo` - Rút tiền",
                parse_mode="Markdown"
            )

async def send_user_dashboard(update: Update, user_id: int):
    u = users_data[user_id]
    vip_lvl = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0))
    cashback_rate = 0.8 + (vip_lvl * 0.2)
    
    admin_tag = ""
    if is_master_admin(user_id):
        admin_tag = "\n👑 **Quản trị viên tối cao / Admin hệ thống**"
    elif user_id in sub_admins:
        admin_tag = "\n🛡️ **Quản trị viên (QTV)**"
    elif user_id in cskh_staffs:
        admin_tag = "\n🎧 **Nhân viên CSKH hệ thống**"

    keyboard = [
        [InlineKeyboardButton("🎲 Tài Xỉu & Chẵn Lẻ", callback_data="choi_taixiu"), InlineKeyboardButton("🃏 Baccarat Xúc Xắc", callback_data="choi_baccarat")],
        [InlineKeyboardButton("🦀 Game Bầu Cua", callback_data="choi_baucua"), InlineKeyboardButton("👑 Thông Tin VIP", callback_data="xem_vip")],
        [InlineKeyboardButton("🏆 Bảng Xếp Hạng", callback_data="xem_bxh")]
    ]
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("👑 Quản Lý Acc Người Chơi (QTV/Admin)", callback_data="admin_view_all_acc")])

    chat_obj = update.message if update.message else update.callback_query.message
    await chat_obj.reply_text(
        f"【**TKGame**】\n\n"
        f"🆔 ID: `{u['custom_id']}` (Tele ID: `{user_id}`){admin_tag}\n"
        f"👑 **VIP {vip_lvl}** | 💰 Ví TK: `{u['balance']:,.0f}` điểm\n"
        f"🔄 Hoàn trả cược: `{cashback_rate:.1f}%` | 🏦 STK: `{SINGLE_BANK_INFO['stk']}` ({SINGLE_BANK_INFO['name']})\n\n"
        f"💡 *Gõ lệnh nạp:* `/nap [số_tiền]` (Hỗ trợ KM 135%) 🔽",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def hien_thi_menu_nap(update: Update):
    chat_obj = update.message if update.message else update.callback_query.message
    await chat_obj.reply_text(
        f"📥 **HƯỚNG DẪN NẠP TIỀN QUA NGÂN HÀNG**\n"
        f"• Ngân hàng: **MSB**\n"
        f"• STK Duy Nhất: `{SINGLE_BANK_INFO['stk']}`\n"
        f"• Chủ TK: `{SINGLE_BANK_INFO['chủ tài khoản']}`\n"
        f"• Khuyến Mãi **135%** (Nạp 400k + KM 140k = 540k, x1 vòng cược).\n\n"
        f"💡 Gõ lệnh: `/nap [số_tiền]` để nhận mã QR và nội dung chuyển khoản riêng!",
        parse_mode="Markdown"
    )

async def hien_thi_thong_tin_vip(update: Update, user_id: int):
    u = users_data[user_id]
    dep = u.get("total_deposited", 0.0)
    wag = u.get("total_wagered", 0.0)
    vip_lvl = tinh_vip(dep, wag)
    
    req_dep, req_wag = get_vip_requirements(vip_lvl)
    if vip_lvl >= 11:
        dep_status = f"{dep:,.0f} [ĐỦ]"
        wag_status = f"{wag:,.0f} [ĐỦ]"
        missing_dep_str = "0 [ĐỦ]"
        missing_wag_str = "0 [ĐỦ]"
    else:
        dep_status = f"{dep:,.0f} / {req_dep:,.0f}"
        wag_status = f"{wag:,.0f} / {req_wag:,.0f}"
        missing_dep = max(0.0, req_dep - dep)
        missing_wag = max(0.0, req_wag - wag)
        missing_dep_str = f"còn thiếu {missing_dep:,.0f}" if missing_dep > 0 else "[ĐỦ]"
        missing_wag_str = f"còn thiếu {missing_wag:,.0f}" if missing_wag > 0 else "[ĐỦ]"

    cashback_rate = 0.8 + (vip_lvl * 0.2)
    vip_text = (
        f"👑 **HỆ THỐNG CẤP ĐỘ VIP** 👑\n\n"
        f"• Cấp VIP hiện tại: **VIP {vip_lvl}**\n"
        f"• Tổng số tiền đã nạp: `{dep_status}`\n"
        f"• Tổng số tiền đã cược: `{wag_status}`\n"
        f"• Tỷ lệ hoàn trả hiện tại: `{cashback_rate:.1f}%`\n"
        f"• Lương VIP định kỳ: **Tuần 10.000đ** | **Tháng 30.000đ**\n\n"
        f"🎯 **Tiến độ lên VIP tiếp theo:**\n"
        f"• Cần nạp thêm: `{missing_dep_str}`\n"
        f"• Cần cược thêm: `{missing_wag_str}`"
    )
    chat_obj = update.message if update.message else update.callback_query.message
    await chat_obj.reply_text(vip_text, parse_mode="Markdown")


# =========================
# 4. HỆ THỐNG TRÒ CHƠI & XÚC XẮC (BACCARAT)
# =========================
async def xu_ly_quay_baccarat(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, choice: str, amt: int):
    chat_id = update.effective_chat.id
    global phien_baccarat_id
    phien_baccarat_id += 1
    ma_gd = random.randint(100000, 999999)

    dice_emojis = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}

    await context.bot.send_message(chat_id=chat_id, text=f"🎲 Phiên #{phien_baccarat_id} — Đang đổ 🔵 Con......", parse_mode="Markdown")
    try:
        m1 = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        con_d1 = m1.dice.value
        await asyncio.sleep(0.3)
        m2 = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        con_d2 = m2.dice.value
        await asyncio.sleep(0.3)
        m3 = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        con_d3 = m3.dice.value
    except:
        con_d1, con_d2, con_d3 = random.randint(1,6), random.randint(1,6), random.randint(1,6)

    await context.bot.send_message(chat_id=chat_id, text=f"🎲 Phiên #{phien_baccarat_id} — Đang đổ 🔴 Cái......", parse_mode="Markdown")
    try:
        m4 = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        cai_d1 = m4.dice.value
        await asyncio.sleep(0.3)
        m5 = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        cai_d2 = m5.dice.value
        await asyncio.sleep(0.3)
        m6 = await context.bot.send_dice(chat_id=chat_id, emoji="🎲")
        cai_d3 = m6.dice.value
    except:
        cai_d1, cai_d2, cai_d3 = random.randint(1,6), random.randint(1,6), random.randint(1,6)

    con_sum = con_d1 + con_d2 + con_d3
    cai_sum = cai_d1 + cai_d2 + cai_d3
    con_score = con_sum % 10
    cai_score = cai_sum % 10

    if con_score > cai_score:
        winning_side = "con"
    elif cai_score > con_score:
        winning_side = "cai"
    else:
        winning_side = "hoa"

    is_win = (choice == winning_side)
    total_thang = 0.0
    u = users_data[user_id]

    if is_win:
        if choice == "hoa":
            total_thang = amt * 8.0
        elif choice == "con":
            total_thang = amt * 2.0
        elif choice == "cai":
            total_thang = amt * 1.95
        u["balance"] += total_thang
        ket_qua_str = f"Chiến thắng - +{total_thang:,.0f}đ"
        u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thắng Baccarat {choice.upper()}: +{total_thang:,.0f}đ")
    else:
        if winning_side == "hoa" and choice in ["con", "cai"]:
            total_thang = amt
            u["balance"] += total_thang
            ket_qua_str = f"Hoà (Tie) - Hoàn tiền {amt:,}đ"
            u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Baccarat Hoà, hoàn tiền: +{amt:,}đ")
        else:
            ket_qua_str = f"Thua cuộc - -{amt:,}đ"
            u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Thua Baccarat {choice.upper()}: -{amt:,}đ")

    con_icons_str = f"{dice_emojis[con_d1]} {dice_emojis[con_d2]} {dice_emojis[con_d3]}"
    cai_icons_str = f"{dice_emojis[cai_d1]} {dice_emojis[cai_d2]} {dice_emojis[cai_d3]}"

    msg = (
        f"🎉 **Kết quả phiên #{phien_baccarat_id}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"🔵 Con {con_icons_str} ➔ `{con_score}`\n"
        f"🔴 Cái {cai_icons_str} ➔ `{cai_score}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📌 Cửa đặt: **{choice.upper()}** ({amt:,}đ)\n"
        f"🔢 Mã GD: `{ma_gd}`\n"
        f"🏆 Kết quả: {winning_side.upper()}\n"
        f"💰 {ket_qua_str}\n"
        f"💳 Số dư ví: **{u['balance']:,.0f}đ**"
    )
    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

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
    
    sorted_refs = sorted(referral_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    ref_rewards = [40000, 30000, 20000, 10000, 10000]
    
    ref_bxh_str = ""
    for idx, (uid, count) in enumerate(sorted_refs):
        uname = users_data.get(uid, {}).get("name", "User")
        masked_name = uname[:2] + "***" if len(uname) > 2 else "***"
        reward = ref_rewards[idx]
        medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][idx]
        ref_bxh_str += f"{medal} `{masked_name}` · {count} bạn · 🧧 **{reward:,}đ**\n"
    if not ref_bxh_str:
        ref_bxh_str = "• Chưa có dữ liệu mời bạn bè.\n"

    bxh_text = (
        f"🔥 **CHƯƠNG TRÌNH MỜI BẠN BÈ (TOP 5)**\n"
        f"🎁 Thưởng nóng từ 10.000đ đến 40.000đ cho top giới thiệu!\n\n"
        f"{ref_bxh_str}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🥇 **BXH Chuỗi Thắng hôm nay**\n"
        f"📅 **Ngày: {today_str}**\n"
        f"🔥 Trạng thái: cập nhật liên tục · chốt lúc 23:55 mỗi ngày\n\n"
        f"🟤 **Top 10**\n"
        f"🥇 `*****72771` · 11 ván · 🧧 **20.000đ**\n"
        f"🥈 `*****08433` · 8 ván · 🧧 **10.000đ**\n"
        f"🥉 `*****59087` · 6 ván · 🧧 **5.000đ**\n\n"
        f"💡 Số liệu cộng dồn đến 23:55, bấm «Làm mới» để xem hạng mới nhất."
    )
    keyboard = [
        [InlineKeyboardButton("🔄 Làm mới", callback_data="refresh_bxh"), InlineKeyboardButton("📅 Hôm qua", callback_data="bxh_yesterday")],
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

    status_msg = await update.message.reply_text("⏳ Đang tạo mã QR nạp ngân hàng...")
    await asyncio.sleep(2.0)
    try:
        await status_msg.delete()
    except:
        pass

    u = users_data[user_id]
    unique_note_code = f"TK{random.randint(100000, 999999)}"
    order_id = f"NAP{random.randint(10000,99999)}"
    
    pending_orders[order_id] = {
        "user_id": user_id, "amount": amount, "note_code": unique_note_code,
        "name": u["name"], "custom_id": u["custom_id"], "admin_status": "pending"
    }

    caption_text = (
        f"💳 **HƯỚNG DẪN NẠP ĐIỂM (#{order_id})**\n"
        f"🏦 Ngân hàng: **MSB**\n"
        f"📌 STK Duy Nhất: `{SINGLE_BANK_INFO['stk']}`\n"
        f"👤 Chủ TK: `{SINGLE_BANK_INFO['chủ tài khoản']}`\n"
        f"💰 Số tiền: `{amount:,}` VNĐ\n"
        f"📝 **Nội dung chuyển khoản (Bắt buộc):** `{unique_note_code}`\n\n"
        f"🎁 *Lưu ý:* Hỗ trợ khuyến mãi **135%** (Nạp 400k + KM 140k = 540k, x1 vòng cược). Chuyển khoản xong bấm nút bên dưới!"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Nhận KM 135%", callback_data=f"km_yes_{order_id}"), InlineKeyboardButton("❌ Không KM", callback_data=f"km_no_{order_id}")]
    ]
    
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=BANK_QR_URL,
        caption=caption_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def menu_rut_bank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` trước!")
        return
    if not context.args or len(context.args) < 4:
        await update.message.reply_text(WITHDRAW_GUIDE_TEXT, parse_mode="Markdown")
        return
    try:
        amount = int(context.args[0])
        bank_code = context.args[1].upper()
        stk = context.args[2]
        chủ_tk = " ".join(context.args[3:])
    except ValueError:
        await update.message.reply_text("⚠️ Sai cú pháp! Vui lòng kiểm tra lại hướng dẫn.", parse_mode="Markdown")
        return

    u = users_data[user_id]
    if not u.get("has_deposited_50k", False) or u.get("total_deposited", 0) < 50000:
        await update.message.reply_text("❌ Rút tiền lần đầu yêu cầu bạn phải nạp tích lũy tối thiểu **50.000đ**!", parse_mode="Markdown")
        return
    if u.get("wager_remaining", 0.0) > 0:
        await update.message.reply_text(f"❌ Bạn còn thiếu `{u['wager_remaining']:,.0f}` điểm cược để hoàn thành x1 vòng cược yêu cầu trước khi rút!", parse_mode="Markdown")
        return

    if amount < 50000 or u["balance"] < amount:
        await update.message.reply_text("❌ Số tiền rút tối thiểu là 50,000đ hoặc số dư ví không đủ!", parse_mode="Markdown")
        return

    u["balance"] -= amount
    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Rút BANK {amount:,} về {bank_code} ({stk})")
    await update.message.reply_text(f"✅ Gửi yêu cầu rút BANK `{amount:,}` về `{bank_code}` thành công!", parse_mode="Markdown")

async def menu_rut_momo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or users_data[user_id].get("step") != "active":
        await update.message.reply_text("⚠️ Vui lòng gõ `/start` trước!")
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(WITHDRAW_GUIDE_TEXT, parse_mode="Markdown")
        return
    try:
        momo_number = context.args[0]
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ Sai cú pháp! VD: `/rutmomo 0987654321 50000`", parse_mode="Markdown")
        return

    u = users_data[user_id]
    if not u.get("has_deposited_50k", False) or u.get("total_deposited", 0) < 50000:
        await update.message.reply_text("❌ Rút tiền lần đầu yêu cầu bạn phải nạp tích lũy tối thiểu **50.000đ**!", parse_mode="Markdown")
        return
    if u.get("wager_remaining", 0.0) > 0:
        await update.message.reply_text(f"❌ Bạn còn thiếu `{u['wager_remaining']:,.0f}` điểm cược để hoàn thành x1 vòng cược!", parse_mode="Markdown")
        return

    if amount < 50000 or u["balance"] < amount:
        await update.message.reply_text("❌ Số tiền rút tối thiểu là 50,000đ đối với Momo hoặc số dư không đủ!", parse_mode="Markdown")
        return

    u["balance"] -= amount
    u["history_action"].append(f"[{datetime.now().strftime('%d/%m %H:%M')}] Rút MOMO {amount:,} về {momo_number}")
    await update.message.reply_text(f"✅ Gửi yêu cầu rút MOMO `{amount:,}` về số `{momo_number}` thành công!", parse_mode="Markdown")

async def check_user_by_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await an_lenh_admin(update)
    user_id = update.effective_user.id
    if not is_cskh(user_id):
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
    elif data == "choi_baccarat":
        bc_rule = (
            "🃏 **HƯỚNG DẪN BACCARAT XÚC XẮC**\n"
            "• Tung 3 xúc xắc cho Con (Player) và 3 cho Cái (Banker).\n"
            "• Tính điểm chuẩn Baccarat: Lấy hàng đơn vị của tổng 3 viên (Tổng 15 tính 5 điểm).\n"
            "• Tỷ lệ trả thưởng: **Con x2** | **Cái x1.95** | **Hoà x8** (Trường hợp Hoà mà cược Con/Cái sẽ được hoàn tiền).\n\n"
            "💡 **Gõ lệnh cược nhanh:**\n"
            "`Con 50000` hoặc `Cai 50000` hoặc `Hoa 20000`"
        )
        await query.message.reply_text(bc_rule, parse_mode="Markdown")
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
    elif data == "xem_vip":
        await hien_thi_thong_tin_vip(query, user_id)
    elif data == "admin_view_all_acc":
        if not is_admin(user_id): return
        if not users_data:
            await query.message.reply_text("⚠️ Chưa có tài khoản nào.")
            return
        keyboard = []
        for uid, u in users_data.items():
            btn_text = f"{u.get('name', 'User')} | ID: {u['custom_id']} | {u['balance']:,.0f}đ"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"adm_detail_{uid}")])
        await query.message.reply_text("👑 **DANH SÁCH TẤT CẢ TÀI KHOẢN (QTV/ADMIN)**\nBấm vào để tuỳ chỉnh:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("adm_detail_"):
        if not is_admin(user_id): return
        target_uid = int(data.replace("adm_detail_", ""))
        if target_uid in users_data:
            u = users_data[target_uid]
            vip_lvl = tinh_vip(u.get("total_deposited", 0.0), u.get("total_wagered", 0.0))
            detail_txt = (
                f"👑 **QUẢN LÝ TÀI KHOẢN**\n\n"
                f"• Telegram ID: `{target_uid}`\n"
                f"• Mã ID Game: `{u['custom_id']}`\n"
                f"• Họ và tên: **{u.get('name', 'N/A')}**\n"
                f"• Số dư ví: `{u['balance']:,.0f}` điểm\n"
                f"• Cấp VIP: **VIP {vip_lvl}**\n"
                f"• Tổng nạp: `{u.get('total_deposited', 0):,.0f}` điểm\n"
                f"• Tổng cược: `{u.get('total_wagered', 0):,.0f}` điểm"
            )
            kb = [
                [
                    InlineKeyboardButton("✏️ Đổi Tên", callback_data=f"adm_editname_{target_uid}"),
                    InlineKeyboardButton("💰 Cộng/Trừ Tiền", callback_data=f"adm_editbal_{target_uid}")
                ]
            ]
            await query.message.reply_text(detail_txt, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("adm_editname_"):
        if not is_admin(user_id): return
        target_uid = int(data.replace("adm_editname_", ""))
        context.user_data["editing_user_id"] = target_uid
        context.user_data["edit_type"] = "name"
        await query.message.reply_text(f"✏️ Vui lòng gửi tên mới cho tài khoản ID `{target_uid}`:", parse_mode="Markdown")
    elif data.startswith("adm_editbal_"):
        if not is_admin(user_id): return
        target_uid = int(data.replace("adm_editbal_", ""))
        context.user_data["editing_user_id"] = target_uid
        context.user_data["edit_type"] = "balance"
        await query.message.reply_text(f"💰 Vui lòng gửi số tiền mới (hoặc số cộng thêm) cho tài khoản ID `{target_uid}`:", parse_mode="Markdown")
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
            targets = {MASTER_ADMIN_ID} | sub_admins | cskh_staffs
            for tid in targets:
                try:
                    kb = [[
                        InlineKeyboardButton("✅ Duyệt", callback_data=f"nap_yes_{order_id}"),
                        InlineKeyboardButton("❌ Từ chối", callback_data=f"nap_no_{order_id}")
                    ]]
                    await context.bot.send_message(chat_id=tid, text=noti_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
                except:
                    pass
            
            try:
                await query.message.delete()
            except:
                pass
            await context.bot.send_message(
                chat_id=query.message.chat.id,
                text=f"✅ Đã chuyển khoản, báo Admin QTV xử lý\n(Đã gửi đơn đi, mã đơn: #{order_id})",
                parse_mode="Markdown"
            )
    elif data.startswith("nap_yes_"):
        if not is_cskh(user_id): return
        order_id = data.replace("nap_yes_", "")
        if order_id in pending_orders:
            order = pending_orders[order_id]
            if order.get("admin_status") == "processed":
                await query.answer("⚠️ Đơn này đã được xử lý trước đó!", show_alert=True)
                return
            order["admin_status"] = "processed"
            target_id = order["user_id"]
            amount = order["amount"]
            use_km = order.get("use_km", False)
            
            final_cred = amount + (amount * 0.35) if use_km else amount
            req_wager = final_cred 
            
            if target_id in users_data:
                old_vip = tinh_vip(users_data[target_id].get("total_deposited", 0.0), users_data[target_id].get("total_wagered", 0.0))
                users_data[target_id]["balance"] += final_cred
                users_data[target_id]["total_deposited"] += amount
                users_data[target_id]["has_deposited_50k"] = True
                users_data[target_id]["wager_remaining"] = users_data[target_id].get("wager_remaining", 0.0) + req_wager
                new_vip = tinh_vip(users_data[target_id].get("total_deposited", 0.0), users_data[target_id].get("total_wagered", 0.0))
                if new_vip > old_vip:
                    try:
                        await context.bot.send_message(chat_id=target_id, text=f"🎉 **CHÚC MỪNG!** Bạn đã thăng hạng thành công lên **VIP {new_vip}**!", parse_mode="Markdown")
                    except:
                        pass
            
            try:
                await context.bot.send_message(
                    chat_id=target_id, 
                    text=f"🎉 Nạp thành công `+{final_cred:,.0f}` điểm! (Đã cộng KM 135%: `{'Có' if use_km else 'Không'}`). Yêu cầu x1 vòng cược: `{req_wager:,.0f}` điểm.", 
                    parse_mode="Markdown"
                )
            except:
                pass
            await query.edit_message_text(text=f"✅ **Đã xử lý (Duyệt nạp #{order_id})**", reply_markup=None)
    elif data.startswith("nap_no_"):
        if not is_cskh(user_id): return
        order_id = data.replace("nap_no_", "")
        if order_id in pending_orders:
            order = pending_orders[order_id]
            if order.get("admin_status") == "processed":
                await query.answer("⚠️ Đơn này đã được xử lý trước đó!", show_alert=True)
                return
            order["admin_status"] = "processed"
            await query.edit_message_text(text=f"❌ **Đã xử lý (Từ chối đơn #{order_id})**", reply_markup=None)

async def handle_admin_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return False
    
    if "editing_user_id" in context.user_data and "edit_type" in context.user_data:
        target_uid = context.user_data["editing_user_id"]
        edit_type = context.user_data["edit_type"]
        val = update.message.text.strip()
        
        if target_uid in users_data:
            if edit_type == "name":
                users_data[target_uid]["name"] = val
                await update.message.reply_text(f"✅ Đã đổi tên tài khoản ID `{target_uid}` thành: **{val}**", parse_mode="Markdown")
            elif edit_type == "balance":
                try:
                    new_bal = float(val)
                    users_data[target_uid]["balance"] = new_bal
                    await update.message.reply_text(f"✅ Đã cập nhật số dư tài khoản ID `{target_uid}` thành: `{new_bal:,.0f}` điểm", parse_mode="Markdown")
                except ValueError:
                    await update.message.reply_text("⚠️ Số tiền không hợp lệ!")
        
        context.user_data.pop("editing_user_id", None)
        context.user_data.pop("edit_type", None)
        return True
    return False


# =========================
# 6. MAIN KHỞI CHẠY
# =========================
def main():
    if not TOKEN:
        raise RuntimeError("Chưa cấu hình BOT_TOKEN.")

    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", set_master_admin))
    app.add_handler(CommandHandler("themqtv", add_qtv_command))
    app.add_handler(CommandHandler("themcskh", add_cskh_command))
    app.add_handler(CommandHandler("danhsachacc", admin_panel_users))
    app.add_handler(CommandHandler("taocode", admin_tao_code_command))
    app.add_handler(CommandHandler("nhapcode", user_nhap_code_command))
    app.add_handler(CommandHandler(["sd", "tk"], send_user_dashboard))
    app.add_handler(CommandHandler("nap", menu_nap))
    app.add_handler(CommandHandler("rutbank", menu_rut_bank))
    app.add_handler(CommandHandler("rutmomo", menu_rut_momo))
    app.add_handler(CommandHandler("rut", menu_rut_bank))
    app.add_handler(CommandHandler("check", check_user_by_admin))

    async def combined_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await handle_admin_edit_input(update, context):
            return
        await handle_message(update, context)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, combined_message_handler))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 TKGame Bot đã cập nhật hoàn tất: Thêm tính năng tạo giftcode độc quyền cho Admin...")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
