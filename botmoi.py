import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# Token và Admin ID
TOKEN_NAP_RUT = "8980298303:AAEnfjr43Nr6USFYAwWLbLV4IoXBc9aIYAk"
ADMIN_ID = 8013947246

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

DB_FILE = "database.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

async def nap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"💳 **HƯỚNG DẪN NẠP ĐIỂM**\n\n"
        f"Bạn vui lòng chuyển khoản qua ngân hàng hoặc Momo với nội dung chuyển khoản:\n"
        f"`NAP {user.id}`\n\n"
        f"Sau khi chuyển khoản thành công, hãy chụp lại biên lai và gửi cho Admin để được cộng điểm.",
        parse_mode="Markdown"
    )

async def rut_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⚠ Sai cú pháp! Vui lòng dùng: `/rut [số_tiền] [Số_tài_khoản / Ngân_hàng]`", parse_mode="Markdown")
        return

    try:
        amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("⚠️ Số tiền rút phải là một con số hợp lệ!")
        return

    info = " ".join(context.args[1:])
    user = update.effective_user
    user_id_str = str(user.id)

    db = load_db()
    if user_id_str not in db or db[user_id_str]["balance"] < amount:
        await update.message.reply_text("❌ Số dư ví của bạn không đủ để thực hiện lệnh rút này!")
        return

    keyboard = [
        [
            InlineKeyboardButton("✅ Duyệt Rút", callback_data=f"approve_{user.id}_{amount}"),
            InlineKeyboardButton("❌ Từ chối", callback_data=f"cancel_{user.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            f"🔔 **YÊU CẦU RÚT TIỀN MỚI**\n\n"
            f"👤 Người chơi: {user.first_name} (`{user.id}`)\n"
            f"💰 Số tiền rút: `{amount:,}` điểm\n"
            f"🏦 Nhận tiền tại: `{info}`"
        ),
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

    await update.message.reply_text("⏳ Yêu cầu rút điểm của bạn đã được gửi tới Admin, vui lòng chờ xử lý trong giây lát!")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith("approve_"):
        parts = data.split("_")
        target_id = parts[1]
        amount = int(parts[2])

        db = load_db()
        if target_id in db:
            db[target_id]["balance"] -= amount
            save_db(db)

        await query.edit_message_text(text=f"{query.message.text}\n\n✅ **ĐÃ DUYỆT GIAO DỊCH THÀNH CÔNG!**", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=int(target_id), text=f"🎉 Yêu cầu rút `{amount:,}` điểm của bạn đã được Admin phê duyệt thành công!")
        except:
            pass
            
    elif data.startswith("cancel_"):
        target_id = data.split("_")[1]
        await query.edit_message_text(text=f"{query.message.text}\n\n❌ **ĐÃ TỪ CHỐI GIAO DỊCH!**", parse_mode="Markdown")
        try:
            await context.bot.send_message(chat_id=int(target_id), text="❌ Yêu cầu rút điểm của bạn đã bị Admin từ chối.")
        except:
            pass

def main():
    app = ApplicationBuilder().token(TOKEN_NAP_RUT).build()
    app.add_handler(CommandHandler("nap", nap_cmd))
    app.add_handler(CommandHandler("rut", rut_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot Nạp/Rút đang chạy...")
    app.run_polling()

if __name__ == "__main__":
    main()
