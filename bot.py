import os
import json
import logging
import asyncio
import random
import threading
from flask import Flask
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =========================
# 1. CẤU HÌNH WEB SERVER (GIỮ BOT 24/7 TRÊN RENDER)
# =========================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "🤖 Bot Tài Xỉu & Nạp Rút đang chạy 24/7 ổn định!"

def run_web():
    port = int(os.getenv("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)


# =========================
# 2. CẤU HÌNH TELEGRAM BOT
# =========================
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = -1003932050774  # ID nhóm game của bạn
ADMIN_ID = 8013947246     # ID Telegram cá nhân của bạn để nhận thông báo duyệt tiền

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

current_session = 84
history = []
is_locked = False

users_data = {}
current_bets = {}
INITIAL_BALANCE = 0

# Danh sách ngân hàng luân phiên ngẫu nhiên
BANK_LIST = [
    {
        "name": "MSB (Ngân hàng Hàng Hải)",
        "stk": "6314072009",
        "chủ tài khoản": "TÔ NGỌC DƯƠNG"
    },
    {
        "name": "MBBank (Quân Đội)",
        "stk": "0776876883",
        "chủ tài khoản": "TÔ NGỌC DƯƠNG"
    }
]


# =========================
# KHÓA / MỞ NHÓM
# =========================
async def lock_chat(app):
    try:
        await app.bot.set_chat_permissions(
            chat_id=CHAT_ID,
            permissions=ChatPermissions(can_send_messages=False)
        )
    except Exception as e:
        logging.error(f"Lỗi khóa nhóm: {e}")

async def unlock_chat(app):
    try:
        await app.bot.set_chat_permissions(
            chat_id=CHAT_ID,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True
            )
        )
    except Exception as e:
        logging.error(f"Lỗi mở nhóm: {e}")


# =========================
# VÒNG LẶP GAME TÀI XỈU
# =========================
async def game_loop(app):
    global current_session, is_locked, current_bets

    try:
        while True:
            current_session += 1
            is_locked = False
            current_bets.clear()

            trend = (
                " ".join("🔴" if x == "TÀI" else "🟢" for x in history[-10:])
                if history
                else "Chưa có"
            )

            await app.bot.send_message(
                chat_id=CHAT_ID,
                text=(
                    f"🎲 *PHIÊN #{current_session}*\n\n"
                    f"📈 Lịch sử: {trend}\n"
                    f"⏰ Chuẩn bị đặt cược trong 40 giây...\n\n"
                    f"👉 Cú pháp đặt cược:\n"
                    f"• `/tai [số_tiền]` hoặc `/xiu [số_tiền]`"
                ),
                parse_mode="Markdown"
            )

            await asyncio.sleep(40)

            is_locked = True
            await lock_chat(app)

            await app.bot.send_message(
                chat_id=CHAT_ID,
                text="🔒 Đã khóa sổ! Chuẩn bị tung xúc xắc..."
            )

            await asyncio.sleep(2)

            dice_msg_1 = await app.bot.send_dice(chat_id=CHAT_ID, emoji="🎲")
            dice_msg_2 = await app.bot.send_dice(chat_id=CHAT_ID, emoji="🎲")
            dice_msg_3 = await app.bot.send_dice(chat_id=CHAT_ID, emoji="🎲")
            
            await asyncio.sleep(4)

            d1 = dice_msg_1.dice.value
            d2 = dice_msg_2.dice.value
            d3 = dice_msg_3.dice.value

            total = d1 + d2 + d3
            result = "TÀI" if total >= 11 else "XỈU"
            result_icon = "🔴" if result == "TÀI" else "🟢"
            history.append(result)

            result_details = []
            for user_id, bet in current_bets.items():
                choice = bet["choice"]
                amount = bet["amount"]
                name = bet["name"]

                if choice == result:
                    win_amount = amount
                    users_data[user_id]["balance"] += win_amount
                    result_details.append(f"✅ {name} thắng +`{win_amount:,}` (Ví: `{users_data[user_id]['balance']:,}`)")
                else:
                    users_data[user_id]["balance"] -= amount
                    result_details.append(f"❌ {name} thua -`{amount:,}` (Ví: `{users_data[user_id]['balance']:,}`)")

            bet_summary_text = "\n".join(result_details) if result_details else "(Không có lượt cược nào phiên này)"
            trend_str = " ".join("🔴" if x == "TÀI" else "🟢" for x in history[-6:])

            await app.bot.send_message(
                chat_id=CHAT_ID,
                text=(
                    f"📊 *KẾT QUẢ PHIÊN: #{current_session}*\n"
                    f"----------------------------------------\n"
                    f"🎲 Xúc xắc: `{d1} - {d2} - {d3}`\n"
                    f"🔢 Tổng điểm: *{total}* ({result_icon} *{result}*)\n"
                    f"📈 Dây cầu: {trend_str}\n"
                    f"----------------------------------------\n"
                    f"📝 *Biến động cược:*\n{bet_summary_text}"
                ),
                parse_mode="Markdown"
            )

            is_locked = False
            await unlock_chat(app)
            await asyncio.sleep(2)
            
    except asyncio.CancelledError:
        logging.info("Vòng lặp game đã dừng an toàn.")


# =========================
# CÁC LỆNH BOT & TÍNH NĂNG NẠP/RÚT
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    name = user.first_name

    if user_id not in users_data:
        users_data[user_id] = {"name": name, "balance": INITIAL_BALANCE}

    await update.message.reply_text(
        f"👋 Chào {name}!\n"
        f"🆔 ID của bạn: `{user_id}`\n\n"
        f"💰 Số dư ví: `{users_data[user_id]['balance']:,}` điểm\n\n"
        f"📋 Menu lệnh:\n"
        f"• `/sd` - Kiểm tra số dư ví\n"
        f"• `/nap` - Hướng dẫn nạp điểm\n"
        f"• `/rut [số_tiền] [STK/Momo]` - Yêu cầu rút điểm\n"
        f"• `/ls` - Xem lịch sử gần đây\n"
        f"• `/tai [số_tiền]` hoặc `/xiu [số_tiền]` - Đặt cược",
        parse_mode="Markdown"
    )

async def check_sd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    if user_id not in users_data:
        users_data[user_id] = {"name": user.first_name, "balance": INITIAL_BALANCE}
    
    balance = users_data[user_id]["balance"]
    await update.message.reply_text(f"🆔 ID: `{user_id}`\n💰 Số dư ví của bạn: `{balance:,}` điểm", parse_mode="Markdown")

async def menu_nap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    name = user.first_name

    if user_id not in users_data:
        users_data[user_id] = {"name": name, "balance": INITIAL_BALANCE}

    # Chọn ngẫu nhiên 1 ngân hàng
    chosen_bank = random.choice(BANK_LIST)
    
    # Cho phép khách nhập số tiền muốn nạp (ví dụ /nap 50000 hoặc mặc định)
    amount = 50000
    if context.args:
        try:
            amount = int(context.args[0])
        except ValueError:
            pass

    nap_text = (
        f"💳 **HƯỚNG DẪN NẠP ĐIỂM**\n\n"
        f"👤 Khách hàng: *{name}*\n"
        f"🆔 ID của bạn: `{user_id}`\n"
        f"🏦 Ngân hàng: *{chosen_bank['name']}*\n"
        f"📌 Số tài khoản: `{chosen_bank['stk']}`\n"
        f"👤 Chủ tài khoản: *{chosen_bank['chủ tài khoản']}*\n"
        f"💰 Nội dung chuyển khoản bắt buộc:\n`NAP {name} {user_id}`\n\n"
        f"⚠️ Sau khi chuyển khoản, bấm nút bên dưới để gửi yêu cầu duyệt nhanh cho Admin!"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Đã Chuyển, Báo Admin Duyệt", callback_data=f"nap_req_{user_id}_{amount}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(nap_text, parse_mode="Markdown", reply_markup=reply_markup)

async def menu_rut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠ Sai cú pháp! Vui lòng dùng: `/rut [số_tiền] [STK hoặc Momo]`", parse_mode="Markdown")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền rút phải là một con số hợp lệ!")
        return

    info = " ".join(context.args[1:])
    user = update.effective_user
    user_id = user.id

    if user_id not in users_data:
        users_data[user_id] = {"name": user.first_name, "balance": INITIAL_BALANCE}

    if users_data[user_id]["balance"] < amount:
        await update.message.reply_text("❌ Số dư ví của bạn không đủ để thực hiện lệnh rút này!")
        return

    keyboard = [
        [
            InlineKeyboardButton("✅ Duyệt Rút", callback_data=f"approve_rut_{user_id}_{amount}"),
            InlineKeyboardButton("❌ Từ chối", callback_data=f"cancel_rut_{user_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"🔔 **YÊU CẦU RÚT TIỀN MỚI**\n\n"
            f"👤 Người chơi: {user.first_name} (`{user_id}`)\n"
            f"💰 Số tiền rút: `{amount:,}` điểm\n"
            f"🏦 Nhận tiền tại: `{info}`"
        ),
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

    await update.message.reply_text("⏳ Yêu cầu rút điểm đã được gửi đến Admin, vui lòng chờ xử lý!")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # Xử lý khi khách bấm báo nạp -> Gửi thông tin kèm nút duyệt nhanh cho Admin
    if data.startswith("nap_req_"):
        parts = data.split("_")
        target_id = int(parts[2])
        amount = int(parts[3])
        target_name = users_data.get(target_id, {}).get("name", f"User {target_id}")

        # Tạo nút duyệt 1 chạm cho Admin
        admin_keyboard = [
            [
                InlineKeyboardButton(f"✅ Duyệt +{amount:,} điểm", callback_data=f"admin_cong_{target_id}_{amount}"),
                InlineKeyboardButton("❌ Hủy", callback_data=f"admin_huy_{target_id}")
            ]
        ]
        admin_markup = InlineKeyboardMarkup(admin_keyboard)

        # Gửi về cho Admin kèm nút bấm trực tiếp
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"🔔 **CÓ YÊU CẦU NẠP TIỀN!**\n\n"
                f"👤 Tên: **{target_name}**\n"
                f"🆔 ID: `{target_id}`\n"
                f"💵 Số tiền dự kiến: `{amount:,}` điểm\n"
                f"📝 Nội dung cần check: `NAP {target_name} {target_id}`\n\n"
                f"👇 Bấm nút bên dưới để cộng điểm ngay lập tức cho khách:"
            ),
            parse_mode="Markdown",
            reply_markup=admin_markup
        )

        await query.answer("Đã gửi yêu cầu nạp cho Admin thành công!", show_alert=True)
        await query.edit_message_text(text=f"{query.message.text}\n\n✅ **ĐÃ GỬI YÊU CẦU CHO ADMIN, VUI LÒNG CHỜ DUYỆT!**", parse_mode="Markdown")

    # Admin bấm duyệt nạp 1 chạm
    elif data.startswith("admin_cong_"):
        parts = data.split("_")
        target_id = int(parts[2])
        amount = int(parts[3])

        if target_id not in users_data:
            users_data[target_id] = {"name": f"User {target_id}", "balance": 0}

        users_data[target_id]["balance"] += amount

        await query.edit_message_text(
            text=f"{query.message.text}\n\n✅ **ĐÃ DUYỆT CỘNG `{amount:,}` ĐIỂM CHO ID `{target_id}` THÀNH CÔNG!**",
            parse_mode="Markdown"
        )
        
        # Báo tin vui cho khách
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎉 Yêu cầu nạp tiền của bạn đã được Admin duyệt! Đã cộng `{amount:,}` điểm vào ví. Kiểm tra bằng lệnh `/sd`.",
                parse_mode="Markdown"
            )
        except:
            pass

    elif data.startswith("admin_huy_"):
        target_id = int(data.split("_")[2])
        await query.edit_message_text(text=f"{query.message.text}\n\n❌ **ĐÃ HỦY YÊU CẦU NẠP NÀY.**", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=target_id, text="❌ Yêu cầu nạp điểm của bạn đã bị từ chối hoặc hủy bỏ bởi Admin.")
        except:
            pass

    elif data.startswith("approve_rut_"):
        parts = data.split("_")
        target_id = int(parts[2])
        amount = int(parts[3])

        if target_id in users_data:
            users_data[target_id]["balance"] -= amount

        await query.edit_message_text(text=f"{query.message.text}\n\n✅ **ĐÃ DUYỆT RÚT TIỀN THÀNH CÔNG!**", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=target_id, text=f"🎉 Yêu cầu rút `{amount:,}` điểm của bạn đã được Admin thanh toán thành công!")
        except:
            pass
            
    elif data.startswith("cancel_rut_"):
        target_id = int(data.split("_")[2])
        await query.edit_message_text(text=f"{query.message.text}\n\n❌ **ĐÃ TỪ CHỐI GIAO DỊCH RÚT!**", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=target_id, text="❌ Yêu cầu rút điểm của bạn đã bị Admin từ chối.")
        except:
            pass

async def menu_ls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not history:
        await update.message.reply_text("📈 Chưa có lịch sử kết quả phiên nào.")
        return
    trend = " ".join("🔴" if x == "TÀI" else "🟢" for x in history[-20:])
    await update.message.reply_text(f"📈 **Lịch sử các phiên gần nhất:**\n{trend}", parse_mode="Markdown")

async def admin_cong_tien(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("⚠ Cú pháp: `/cong [user_id] [số_tiền]`", parse_mode="Markdown")
        return
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ Sai định dạng!")
        return

    if target_id not in users_data:
        users_data[target_id] = {"name": f"User {target_id}", "balance": 0}

    users_data[target_id]["balance"] += amount
    await update.message.reply_text(f"👑 Đã cộng `{amount:,}` điểm cho user `{target_id}`.", parse_mode="Markdown")
    
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"🎉 Tài khoản của bạn đã được Admin cộng thành công `{amount:,}` điểm! Kiểm tra số dư bằng lệnh `/sd`.",
            parse_mode="Markdown"
        )
    except:
        pass

async def place_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global is_locked, current_bets

    if is_locked:
        await update.message.reply_text("⏳ Đang quay thưởng, không thể cược!")
        return

    if not context.args:
        await update.message.reply_text("⚠️️ Vui lòng nhập số tiền cược! Ví dụ: `/tai 10000`", parse_mode="Markdown")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền cược không hợp lệ!")
        return

    if amount <= 0:
        await update.message.reply_text("⚠️ Số tiền cược phải lớn hơn 0!")
        return

    user = update.effective_user
    user_id = user.id
    name = user.first_name

    if user_id not in users_data:
        users_data[user_id] = {"name": name, "balance": INITIAL_BALANCE}

    if users_data[user_id]["balance"] < amount:
        await update.message.reply_text(f"❌ Số dư không đủ (`{users_data[user_id]['balance']:,}` điểm).", parse_mode="Markdown")
        return

    command = update.message.text.split()[0].lower()
    choice = "TÀI" if "tai" in command else "XỈU"

    current_bets[user_id] = {"choice": choice, "amount": amount, "name": name}
    await update.message.reply_text(f"✅ {name} đã cược **{amount:,}** điểm vào cửa **{choice}** thành công!", parse_mode="Markdown")

async def post_init(app):
    app.create_task(game_loop(app))


# =========================
# KHỞI CHẠY CHÍNH
# =========================
def main():
    if not TOKEN:
        raise RuntimeError("Chưa đặt BOT_TOKEN.")

    threading.Thread(target=run_web, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sd", check_sd))
    app.add_handler(CommandHandler("nap", menu_nap))
    app.add_handler(CommandHandler("rut", menu_rut))
    app.add_handler(CommandHandler("ls", menu_ls))
    app.add_handler(CommandHandler("cong", admin_cong_tien))
    app.add_handler(CommandHandler("tai", place_bet))
    app.add_handler(CommandHandler("xiu", place_bet))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot Tài Xỉu & Nạp/Rút cùng Web Server đang chạy ổn định 24/7...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
