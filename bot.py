import sqlite3
import asyncio
from config import MAIN_ADMIN_ID, TOKEN
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters, ContextTypes
)
from telegram.error import Forbidden, BadRequest

# TOKEN = "YOUR_BOT_TOKEN"
# MAIN_ADMIN_ID = 123456789
DB = "movies.db"

# === DB INIT ===
conn = sqlite3.connect(DB, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    join_date TEXT
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS movies(
    code TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    file_id TEXT,
    downloads INTEGER DEFAULT 0
)
""")
cursor.execute("""CREATE TABLE IF NOT EXISTS admins(
    user_id INTEGER PRIMARY KEY,
    is_main INTEGER DEFAULT 0
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS downloads(
    user_id INTEGER,
    movie_code TEXT,
    date TEXT
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS channels(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE
)
""")

# 🔹 MAIN_ADMIN_ID ni avtomatik qo'shish
cursor.execute("INSERT OR IGNORE INTO admins(user_id, is_main) VALUES (?, 1)", (MAIN_ADMIN_ID,))
conn.commit()

# == is subscribe ==
async def is_subscribed(bot, user_id):
    cursor.execute("SELECT username FROM channels")
    channels = cursor.fetchall()
    if not channels:
        return True  # Agar majburiy kanal yo'q bo'lsa → srazu o'tkazamiz

    for (channel,) in channels:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status not in ["member", "creator", "administrator"]:
                return False
        except:
            return False
    return True

async def show_main_menu(update_or_query):
    keyboard = [
        [InlineKeyboardButton("🔥 Top kinolar", callback_data="top")],
        [InlineKeyboardButton("🎞 Kino kodlari", callback_data="codes")]
    ]
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(
            "Kino kodini yuboring yoki tugmani tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update_or_query.message.reply_text(
            "Kino kodini yuboring yoki tugmani tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )



# === Commands Dynamic ===
async def set_user_commands(app, user_id):
    cursor.execute("SELECT is_main FROM admins WHERE user_id=?", (user_id,))
    admin = cursor.fetchone()

    if admin:
        # ✅ Agar admin bo‘lsa → barcha komandalar
        commands = [
            BotCommand("start", "Botni ishga tushirish"),
            BotCommand("admin", "Admin panel"),
            BotCommand("addmovie", "Kino qo‘shish"),
            BotCommand("delmovie", "Kino o‘chirish"),
            BotCommand("stats", "Statistika"),
            BotCommand("broadcast", "Xabar yuborish"),
            BotCommand("addchannel", "Majburiy kanal qo‘shish"),
            BotCommand("listchannels", "Kanallar ro‘yxati"),
            BotCommand("delchannel", "Kanal o‘chirish"),
        ]
        if admin[0] == 1:
            commands += [
                BotCommand("addadmin", "Admin qo‘shish"),
                BotCommand("deladmin", "Admin o‘chirish"),
            ]
    else:
        # ✅ Agar admin bo‘lmasa → faqat /start
        commands = [BotCommand("start", "Botni ishga tushirish")]

    # ✅ Faqat bitta user uchun commandlarni sozlaymiz
    await app.bot.set_my_commands(
        commands,
        scope={"type": "chat", "chat_id": user_id}
    )


# === START ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # ✅ Admin yoki user ekanligini aniqlab, komandalar ro‘yxatini sozlaymiz
    await set_user_commands(context.application, user_id)

    # ✅ Majburiy obuna tekshirish
    if not await is_subscribed(context.bot, user_id):
        cursor.execute("SELECT username FROM channels")
        channels = cursor.fetchall()

        keyboard = []
        for idx, (channel,) in enumerate(channels, 1):
            keyboard.append([
                InlineKeyboardButton(
                    f"{idx}-kanal",
                    url=f"https://t.me/{channel.replace('@', '')}"
                )
            ])
        keyboard.append([InlineKeyboardButton("✅ Obuna bo‘ldim", callback_data="check_subs")])

        await update.message.reply_text(
            "❗ Botdan foydalanish uchun quyidagi kanallarga obuna bo‘ling:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # ✅ Agar obuna bo‘lgan bo‘lsa → Main Menu
    await show_main_menu(update)

# === Kino kodi orqali olish ===
async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()

    cursor.execute("SELECT description, file_id FROM movies WHERE code=?", (code,))
    movie = cursor.fetchone()
    if movie:
        desc, fid = movie
        cursor.execute("UPDATE movies SET downloads=downloads+1 WHERE code=?", (code,))
        cursor.execute("INSERT INTO downloads(user_id, movie_code, date) VALUES (?, ?, date('now'))",
                       (update.effective_user.id, code))
        conn.commit()
        await update.message.reply_video(fid, caption=desc)
    else:
        await update.message.reply_text("❌ Bunday kino kodi topilmadi.")


# === Inline buttons ===
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data

    if data == "check_subs":
        if await is_subscribed(context.bot, q.from_user.id):
            await q.message.delete()
            await show_main_menu(q)
        else:
            await q.answer("❌ Hali hammasiga obuna bo‘lmadingiz!", show_alert=True)
            return

    # ✅ Eski xabarni o'chiramiz
    try:
        await q.message.delete()
    except:
        pass

    if data == "top":
        cursor.execute("SELECT code, name, downloads FROM movies ORDER BY downloads DESC LIMIT 10")
        rows = cursor.fetchall()
        text = "🔥 Eng ko‘p yuklangan kinolar:\n\n"
        for c, n, d in rows:
            text += f"{c} - {n} ({d} marta)\n"

        # ✅ Back tugmasi qo‘shamiz
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back")]]
        await q.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "codes":
        cursor.execute("SELECT code, name FROM movies")
        rows = cursor.fetchall()
        text = "🎞 Kino kodlarini ushbu kanaldan olishingiz mumkin:\n\n"

        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back")]]
        await q.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "back":
        # ✅ Eski xabarni o‘chirib, Main Menu ni qaytaramiz
        keyboard = [
            [InlineKeyboardButton("🔥 Top kinolar", callback_data="top")],
            [InlineKeyboardButton("🎞 Kino kodlari", callback_data="codes")]
        ]
        await q.message.reply_text(
            "Kino kodini yuboring yoki tugmani tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# === Admin panel ===
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cursor.execute("SELECT is_main FROM admins WHERE user_id=?", (uid,))
    row = cursor.fetchone()
    if row:
        msg = "/addmovie – Kino qo‘shish\n/delmovie – Kino o‘chirish\n/stats – Statistika\n/broadcast – Xabar yuborish"
        if row[0] == 1:
            msg += "\n/addadmin – Admin qo‘shish\n/deladmin – Admin o‘chirish"
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text("❌ Siz admin emassiz.")

# === Add Movie ===
ADD_CODE, ADD_DESC, ADD_NAME, ADD_VIDEO = range(4)

async def addmovie_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cursor.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,))
    if cursor.fetchone():
        await update.message.reply_text("Kino kodi?")
        return ADD_CODE
    await update.message.reply_text("❌ Siz admin emassiz.")
    return ConversationHandler.END

async def addmovie_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["code"] = update.message.text.strip()
    await update.message.reply_text("Kino tavsifi (description)?")
    return ADD_DESC

async def addmovie_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["description"] = update.message.text.strip()
    await update.message.reply_text("Kino nomi?")
    return ADD_NAME

async def addmovie_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Kino videosini yuboring:")
    return ADD_VIDEO

async def addmovie_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.video:
        await update.message.reply_text("❌ Faqat video yuboring.")
        return ADD_VIDEO

    fid = update.message.video.file_id
    code = context.user_data["code"]
    name = context.user_data["name"]
    desc = context.user_data["description"]

    cursor.execute(
        "INSERT OR REPLACE INTO movies(code, name, description, file_id) VALUES (?, ?, ?, ?)",
        (code, name, desc, fid)
    )
    conn.commit()
    await update.message.reply_text(f"✅ Kino qo‘shildi: {code} – {name}")
    return ConversationHandler.END

async def addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cursor.execute("SELECT is_main FROM admins WHERE user_id=?", (uid,))
    admin = cursor.fetchone()
    if not admin:
        await update.message.reply_text("❌ Siz admin emassiz.")
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /addchannel @username")
        return
    username = context.args[0]
    cursor.execute("INSERT OR IGNORE INTO channels(username) VALUES (?)", (username,))
    conn.commit()
    await update.message.reply_text(f"✅ {username} qo‘shildi.")


async def listchannels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT id, username FROM channels")
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("📭 Kanal qo‘shilmagan.")
        return
    text = "📌 Majburiy kanallar:\n"
    for i, (cid, uname) in enumerate(rows, 1):
        text += f"{i}. {uname}  (/delchannel {cid})\n"
    await update.message.reply_text(text)

async def delchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Foydalanish: /delchannel ID")
        return
    cid = int(context.args[0])
    cursor.execute("DELETE FROM channels WHERE id=?", (cid,))
    conn.commit()
    await update.message.reply_text("✅ Kanal o‘chirildi.")



# === Del Movie ===
async def delmovie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cursor.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,))
    if cursor.fetchone():
        if context.args:
            code = context.args[0]
            cursor.execute("DELETE FROM movies WHERE code=?", (code,))
            conn.commit()
            await update.message.reply_text(f"✅ {code} o‘chirildi.")
        else:
            await update.message.reply_text("Foydalanish: /delmovie KINO_KODI")
    else:
        await update.message.reply_text("❌ Siz admin emassiz.")

# === Stats ===
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cursor.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,))
    if not cursor.fetchone():
        await update.message.reply_text("❌ Siz admin emassiz.")
        return

    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM movies")
    movies_count = cursor.fetchone()[0]

    text = f"📊 Statistika:\n👥 Foydalanuvchilar: {users_count}\n🎞 Kinolar: {movies_count}\n\n"

    cursor.execute("SELECT code, name, downloads FROM movies ORDER BY downloads DESC")
    rows = cursor.fetchall()
    for code, name, d in rows:
        text += f"• {name} ({code}) – {d} marta yuklangan\n"

    await update.message.reply_text(text)


# === Broadcast (photo+text) ===
BROADCAST_PHOTO, BROADCAST_TEXT = range(2)

BROADCAST_WAITING = range(1)

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    cursor.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,))
    if not cursor.fetchone():
        await update.message.reply_text("❌ Siz admin emassiz.")
        return ConversationHandler.END

    await update.message.reply_text("✅ Xabarni yuboring (rasm, video yoki matn bo‘lishi mumkin):")
    return BROADCAST_WAITING


async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    sent = 0

    for (user_id,) in users:
        try:
            if update.message.photo:
                await context.bot.send_photo(
                    user_id, update.message.photo[-1].file_id,
                    caption=update.message.caption or ""
                )
            elif update.message.video:
                await context.bot.send_video(
                    user_id, update.message.video.file_id,
                    caption=update.message.caption or ""
                )
            elif update.message.text:
                await context.bot.send_message(user_id, update.message.text)

            sent += 1
            await asyncio.sleep(0.05)
        except (Forbidden, BadRequest):
            continue

    await update.message.reply_text(f"✅ {sent} foydalanuvchiga yuborildi.")
    return ConversationHandler.END



# === Admin boshqaruvi ===
async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MAIN_ADMIN_ID:
        await update.message.reply_text("❌ Faqat main admin.")
        return
    if context.args:
        new_id = int(context.args[0])
        cursor.execute("INSERT OR IGNORE INTO admins(user_id, is_main) VALUES (?, 0)", (new_id,))
        conn.commit()
        await update.message.reply_text("✅ Admin qo‘shildi.")
    else:
        await update.message.reply_text("Foydalanish: /addadmin USER_ID")

async def deladmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MAIN_ADMIN_ID:
        await update.message.reply_text("❌ Faqat main admin.")
        return
    if context.args:
        rm_id = int(context.args[0])
        cursor.execute("DELETE FROM admins WHERE user_id=?", (rm_id,))
        conn.commit()
        await update.message.reply_text("✅ Admin o‘chirildi.")
    else:
        await update.message.reply_text("Foydalanish: /deladmin USER_ID")

# === App ===
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(CommandHandler("admin", admin))
app.add_handler(CommandHandler("delmovie", delmovie))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("addadmin", addadmin))
app.add_handler(CommandHandler("deladmin", deladmin))

# ✅ ConversationHandler lar
conv_addmovie = ConversationHandler(
    entry_points=[CommandHandler("addmovie", addmovie_start)],
    states={
        ADD_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, addmovie_code)],
        ADD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, addmovie_desc)],
        ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, addmovie_name)],
        ADD_VIDEO: [MessageHandler(filters.VIDEO, addmovie_video)]
    },
    fallbacks=[]
)
app.add_handler(conv_addmovie)

conv_broadcast = ConversationHandler(
    entry_points=[CommandHandler("broadcast", broadcast_start)],
    states={
        BROADCAST_WAITING: [
            MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_send)
        ]
    },
    fallbacks=[]
)
app.add_handler(conv_broadcast)

# ✅ Majburiy obuna uchun admin komandalar
app.add_handler(CommandHandler("addchannel", addchannel))
app.add_handler(CommandHandler("listchannels", listchannels))
app.add_handler(CommandHandler("delchannel", delchannel))

# ✅ Asosiy komandalar
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))
app.add_handler(CommandHandler("delmovie", delmovie))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CommandHandler("addadmin", addadmin))
app.add_handler(CommandHandler("deladmin", deladmin))

# ✅ Inline tugmalar uchun handler (majburiy obuna check_subs, top/codes/back)
app.add_handler(CallbackQueryHandler(button_handler))

# ✅ Eng oxirida: foydalanuvchi kod yuborishini ishlovchi handler
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))

# ✅ Botni ishga tushirish
app.run_polling()

