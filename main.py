import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from telegram.request import HTTPXRequest
import logging

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TOKEN")
proxy_url = os.getenv("PROXY_URL")

# مراحل مکالمه
ADDING_USERS = 1
TASK_NAME = 2
TASK_SHARE = 3
TASK_PAID = 4
EDIT_VALUE = 5

data = {}

# ───────────────────────────────
# دکمه‌ها
# ───────────────────────────────

def start_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("➕ افزودن کاربر", callback_data="begin_adding_users")]])

def adding_users_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ اتمام افزودن کاربران", callback_data="done_users")]])

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ فعالیت جدید", callback_data="new_task"), InlineKeyboardButton("📋 جزئیات", callback_data="show_details")],
        [InlineKeyboardButton("💰 تسویه حساب", callback_data="settle")],
        [InlineKeyboardButton("🔄 شروع مجدد", callback_data="restart_confirm")],
    ])

def task_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 شروع مجدد فعالیت", callback_data="restart_task")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")],
    ])

def details_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ ایجاد تغییرات", callback_data="edit_mode")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")],
    ])

def edit_tasks_keyboard(tasks):
    buttons = []
    for i, task in enumerate(tasks):
        buttons.append([InlineKeyboardButton(f"📝 {task['name']}", callback_data=f"edit_task_{i}")])
    buttons.append([InlineKeyboardButton("🔙 بازگشت", callback_data="show_details")])
    return InlineKeyboardMarkup(buttons)

def edit_task_users_keyboard(task, users, task_index, temp_data):
    buttons = []
    for user in users:
        share = temp_data["shares"].get(user, task['shares'][user])
        paid = temp_data["paids"].get(user, task['paids'][user])
        buttons.append([
            InlineKeyboardButton(f"👤 {user}", callback_data="noop"),
            InlineKeyboardButton(f"سهم: {share:,}", callback_data=f"edit_field_{task_index}_{user}_share"),
            InlineKeyboardButton(f"پرداخت: {paid:,}", callback_data=f"edit_field_{task_index}_{user}_paid"),
        ])
    buttons.append([
        InlineKeyboardButton("✅ تایید", callback_data=f"confirm_edit_{task_index}"),
        InlineKeyboardButton("🔙 بازگشت", callback_data="edit_mode"),
    ])
    return InlineKeyboardMarkup(buttons)

def restart_confirm_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ بله، مطمئنم", callback_data="restart_confirmed")],
        [InlineKeyboardButton("❌ خیر، برگشت", callback_data="back_to_main")],
    ])

# ───────────────────────────────
# شروع
# ───────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data[chat_id] = {"users": [], "tasks": []}
    await update.message.reply_text(
        "سلام! 👋\nبرای شروع کاربران رو اضافه کن:",
        reply_markup=start_keyboard()
    )
    return ADDING_USERS

async def begin_adding_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "اسم اول رو وارد کن:",
        reply_markup=adding_users_keyboard()
    )
    return ADDING_USERS

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    name = update.message.text.strip()
    data[chat_id]["users"].append(name)
    await update.message.reply_text(
        f"✅ {name} اضافه شد!\nاسم بعدی رو وارد کن یا دکمه اتمام رو بزن:",
        reply_markup=adding_users_keyboard()
    )
    return ADDING_USERS

async def done_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    users = data[chat_id]["users"]

    if len(users) < 2:
        await query.edit_message_text(
            "⚠️ حداقل ۲ نفر باید وارد کنی!",
            reply_markup=adding_users_keyboard()
        )
        return ADDING_USERS

    user_list = "\n".join([f"👤 {u}" for u in users])
    await query.edit_message_text(
        f"✅ یوزرها ثبت شدن:\n{user_list}\n\nاز دکمه‌های زیر استفاده کن:",
        reply_markup=main_keyboard()
    )
    return ConversationHandler.END

# ───────────────────────────────
# منوی اصلی
# ───────────────────────────────

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "از دکمه‌های زیر استفاده کن:",
        reply_markup=main_keyboard()
    )
    return ConversationHandler.END

# ───────────────────────────────
# اضافه کردن فعالیت
# ───────────────────────────────

async def new_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id

    if chat_id not in data or not data[chat_id]["users"]:
        await query.edit_message_text("⚠️ اول /start بزن و یوزرها رو وارد کن!")
        return ConversationHandler.END

    context.user_data["current_task"] = {
        "name": "",
        "shares": {},
        "paids": {},
        "current_index": 0
    }

    await query.edit_message_text(
        "اسم فعالیت رو وارد کن:",
        reply_markup=task_keyboard()
    )
    return TASK_NAME

async def task_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    name = update.message.text.strip()
    context.user_data["current_task"]["name"] = name

    first_user = data[chat_id]["users"][0]
    await update.message.reply_text(
        f"👤 {first_user}\n"
        f"سهمش از این فعالیت چقدره؟\n"
        f"(اگه سهمی نداره عدد 0 وارد کن)",
        reply_markup=task_keyboard()
    )
    return TASK_SHARE

async def task_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users = data[chat_id]["users"]
    current_task = context.user_data["current_task"]
    index = current_task["current_index"]
    current_user = users[index]

    try:
        share = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "⚠️ لطفاً یه عدد وارد کن!",
            reply_markup=task_keyboard()
        )
        return TASK_SHARE

    current_task["shares"][current_user] = share
    await update.message.reply_text(
        f"👤 {current_user}\n"
        f"چقدر پول خرج کرده؟\n"
        f"(اگه خرجی نداشته عدد 0 وارد کن)",
        reply_markup=task_keyboard()
    )
    return TASK_PAID

async def task_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    users = data[chat_id]["users"]
    current_task = context.user_data["current_task"]
    index = current_task["current_index"]
    current_user = users[index]

    try:
        paid = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text(
            "⚠️ لطفاً یه عدد وارد کن!",
            reply_markup=task_keyboard()
        )
        return TASK_PAID

    current_task["paids"][current_user] = paid
    current_task["current_index"] += 1
    next_index = current_task["current_index"]

    if next_index < len(users):
        next_user = users[next_index]
        await update.message.reply_text(
            f"👤 {next_user}\n"
            f"سهمش از این فعالیت چقدره؟\n"
            f"(اگه سهمی نداره عدد 0 وارد کن)",
            reply_markup=task_keyboard()
        )
        return TASK_SHARE

    task = {
        "name": current_task["name"],
        "shares": current_task["shares"].copy(),
        "paids": current_task["paids"].copy(),
    }
    data[chat_id]["tasks"].append(task)

    summary = f"✅ فعالیت «{task['name']}» ثبت شد!\n\n"
    for user in users:
        summary += f"👤 {user} | سهم: {task['shares'][user]:,} | پرداخت: {task['paids'][user]:,}\n"
    summary += "\nاز دکمه‌های زیر ادامه بده:"

    await update.message.reply_text(summary, reply_markup=main_keyboard())
    return ConversationHandler.END

async def restart_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    task_name_str = context.user_data.get("current_task", {}).get("name", "")

    context.user_data["current_task"] = {
        "name": task_name_str,
        "shares": {},
        "paids": {},
        "current_index": 0
    }

    first_user = data[chat_id]["users"][0]

    if task_name_str:
        await query.edit_message_text(
            f"🔁 فعالیت «{task_name_str}» از اول شروع شد!\n\n"
            f"👤 {first_user}\n"
            f"سهمش از این فعالیت چقدره؟\n"
            f"(اگه سهمی نداره عدد 0 وارد کن)",
            reply_markup=task_keyboard()
        )
        return TASK_SHARE
    else:
        await query.edit_message_text(
            "اسم فعالیت رو وارد کن:",
            reply_markup=task_keyboard()
        )
        return TASK_NAME

# ───────────────────────────────
# نمایش جزئیات
# ───────────────────────────────

async def show_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id

    if chat_id not in data or not data[chat_id]["tasks"]:
        await query.edit_message_text(
            "⚠️ هنوز هیچ فعالیتی ثبت نشده!",
            reply_markup=main_keyboard()
        )
        return

    users = data[chat_id]["users"]
    tasks = data[chat_id]["tasks"]

    message = "📋 جزئیات فعالیت‌ها:\n"
    message += "─" * 20 + "\n"

    for i, task in enumerate(tasks, 1):
        message += f"\n🔹 فعالیت {i}: {task['name']}\n"
        for user in users:
            share = task['shares'][user]
            paid = task['paids'][user]
            message += f"  👤 {user} | سهم: {share:,} | پرداخت: {paid:,}\n"
        message += "─" * 20 + "\n"

    await query.edit_message_text(message, reply_markup=details_keyboard())

# ───────────────────────────────
# ویرایش
# ───────────────────────────────

async def edit_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    tasks = data[chat_id]["tasks"]

    if not tasks:
        await query.edit_message_text(
            "⚠️ هنوز هیچ فعالیتی ثبت نشده!",
            reply_markup=main_keyboard()
        )
        return

    context.user_data["temp_edit"] = {"shares": {}, "paids": {}}

    await query.edit_message_text(
        "کدوم فعالیت رو میخوای ویرایش کنی؟",
        reply_markup=edit_tasks_keyboard(tasks)
    )

async def edit_task_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    task_index = int(query.data.split("_")[-1])
    task = data[chat_id]["tasks"][task_index]
    users = data[chat_id]["users"]

    context.user_data["edit_task_index"] = task_index
    context.user_data["temp_edit"] = {"shares": {}, "paids": {}}

    await query.edit_message_text(
        f"📝 فعالیت: {task['name']}\nرو کدوم مقدار میخوای تغییر بدی؟",
        reply_markup=edit_task_users_keyboard(task, users, task_index, context.user_data["temp_edit"])
    )

async def edit_field_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    field = parts[-1]
    task_index = int(parts[2])
    user = "_".join(parts[3:-1])

    context.user_data["edit_task_index"] = task_index
    context.user_data["edit_user"] = user
    context.user_data["edit_field"] = field

    field_fa = "سهم" if field == "share" else "پرداخت"
    await query.edit_message_text(
        f"👤 {user}\nمقدار جدید {field_fa} رو وارد کن:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 بازگشت", callback_data=f"edit_task_{task_index}")
        ]])
    )
    return EDIT_VALUE

async def edit_value_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    try:
        value = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً یه عدد وارد کن!")
        return EDIT_VALUE

    task_index = context.user_data["edit_task_index"]
    user = context.user_data["edit_user"]
    field = context.user_data["edit_field"]
    task = data[chat_id]["tasks"][task_index]
    users = data[chat_id]["users"]

    if field == "share":
        context.user_data["temp_edit"]["shares"][user] = value
    else:
        context.user_data["temp_edit"]["paids"][user] = value

    await update.message.reply_text(
        f"✅ مقدار موقتاً ذخیره شد!\n📝 فعالیت: {task['name']}\nبرای تایید نهایی دکمه تایید رو بزن:",
        reply_markup=edit_task_users_keyboard(task, users, task_index, context.user_data["temp_edit"])
    )
    return EDIT_VALUE

async def confirm_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    task_index = int(query.data.split("_")[-1])
    task = data[chat_id]["tasks"][task_index]
    temp = context.user_data.get("temp_edit", {"shares": {}, "paids": {}})

    for user, val in temp["shares"].items():
        task["shares"][user] = val
    for user, val in temp["paids"].items():
        task["paids"][user] = val

    context.user_data["temp_edit"] = {"shares": {}, "paids": {}}

    await query.edit_message_text(
        "✅ تغییرات با موفقیت ذخیره شد!\nکدوم فعالیت رو میخوای ویرایش کنی؟",
        reply_markup=edit_tasks_keyboard(data[chat_id]["tasks"])
    )

# ───────────────────────────────
# تسویه حساب
# ───────────────────────────────

async def settle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id

    if chat_id not in data or not data[chat_id]["tasks"]:
        await query.edit_message_text(
            "⚠️ هنوز هیچ فعالیتی ثبت نشده!",
            reply_markup=main_keyboard()
        )
        return

    users = data[chat_id]["users"]
    tasks = data[chat_id]["tasks"]

    balances = {user: 0 for user in users}
    for task in tasks:
        for user in users:
            balances[user] += task["paids"][user] - task["shares"][user]

    message = "💰 بالانس هر نفر:\n"
    message += "─" * 20 + "\n"
    for user, balance in balances.items():
        if balance > 0:
            message += f"👤 {user}: +{balance:,} طلبکار ✅\n"
        elif balance < 0:
            message += f"👤 {user}: {balance:,} بدهکار ❌\n"
        else:
            message += f"👤 {user}: حساب صفره 👌\n"

    message += "\n💸 تسویه حساب:\n"
    message += "─" * 20 + "\n"

    c_list = sorted([(u, b) for u, b in balances.items() if b > 0], key=lambda x: x[1], reverse=True)
    d_list = sorted([(u, -b) for u, b in balances.items() if b < 0], key=lambda x: x[1], reverse=True)

    ci, di = 0, 0
    while ci < len(c_list) and di < len(d_list):
        creditor, credit = c_list[ci]
        debtor, debt = d_list[di]
        amount = min(credit, debt)
        message += f"👤 {debtor} ➡️ {creditor}: {amount:,}\n"
        c_list[ci] = (creditor, credit - amount)
        d_list[di] = (debtor, debt - amount)
        if c_list[ci][1] == 0:
            ci += 1
        if d_list[di][1] == 0:
            di += 1

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]])
    )

# ───────────────────────────────
# شروع مجدد
# ───────────────────────────────

async def restart_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "⚠️ مطمئنی؟ همه داده‌ها پاک میشن!",
        reply_markup=restart_confirm_keyboard()
    )

async def restart_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    data[chat_id] = {"users": [], "tasks": []}
    await query.edit_message_text(
        "🔄 همه چیز پاک شد!\nبرای شروع کاربران رو اضافه کن:",
        reply_markup=start_keyboard()
    )
    return ADDING_USERS

# ───────────────────────────────
# اجرای بات
# ───────────────────────────────

if proxy_url:
    req = HTTPXRequest(proxy=proxy_url)
    app = ApplicationBuilder().token(TOKEN).request(req).build()
else:
    app = ApplicationBuilder().token(TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        CallbackQueryHandler(restart_confirmed, pattern="^restart_confirmed$"),
        CallbackQueryHandler(new_task, pattern="^new_task$"),
        CallbackQueryHandler(edit_field_select, pattern="^edit_field_.*$"),
    ],
    states={
        ADDING_USERS: [
            CallbackQueryHandler(begin_adding_users, pattern="^begin_adding_users$"),
            CallbackQueryHandler(done_users, pattern="^done_users$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, add_user),
        ],
        TASK_NAME: [
            CallbackQueryHandler(restart_task, pattern="^restart_task$"),
            CallbackQueryHandler(back_to_main, pattern="^back_to_main$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, task_name),
        ],
        TASK_SHARE: [
            CallbackQueryHandler(restart_task, pattern="^restart_task$"),
            CallbackQueryHandler(back_to_main, pattern="^back_to_main$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, task_share),
        ],
        TASK_PAID: [
            CallbackQueryHandler(restart_task, pattern="^restart_task$"),
            CallbackQueryHandler(back_to_main, pattern="^back_to_main$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, task_paid),
        ],
        EDIT_VALUE: [
            CallbackQueryHandler(edit_task_select, pattern="^edit_task_\\d+$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, edit_value_input),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(back_to_main, pattern="^back_to_main$"),
        CommandHandler("start", start),
    ],
)

app.add_handler(conv_handler)
app.add_handler(CallbackQueryHandler(show_details, pattern="^show_details$"))
app.add_handler(CallbackQueryHandler(settle, pattern="^settle$"))
app.add_handler(CallbackQueryHandler(restart_confirm, pattern="^restart_confirm$"))
app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
app.add_handler(CallbackQueryHandler(edit_mode, pattern="^edit_mode$"))
app.add_handler(CallbackQueryHandler(edit_task_select, pattern="^edit_task_\\d+$"))
app.add_handler(CallbackQueryHandler(edit_field_select, pattern="^edit_field_.*$"))
app.add_handler(CallbackQueryHandler(confirm_edit, pattern="^confirm_edit_\\d+$"))
app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern="^noop$"))

print("🤖 بات شروع به کار کرد...")
app.run_polling()