import asyncio
import logging
import os
import random
from urllib.parse import quote
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ChatJoinRequestHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN    = os.environ["BOT_TOKEN"]
ADMIN_ID     = int(os.environ.get("ADMIN_ID", "0"))
CHANNEL_ID   = int(os.environ["CHANNEL_ID"])
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "")
PAYMENT_LINK = os.environ.get("PAYMENT_LINK", "")
VIDEO_1_ID   = os.environ.get("VIDEO_1_ID", "")
VIDEO_2_ID   = os.environ.get("VIDEO_2_ID", "")

VIDEO_DELETE_DELAY = 10       # 10 seconds for videos
CHAT_DELETE_DELAY  = 180      # 3 minutes for all other messages
HEART_EFFECT_ID    = "5159385139981059251"
BASE_VIDEO_COUNT   = 16568

# Per-user state
channel_users = {}
channel_name_cache = ""

# ── Security: block list ─────────────────────────────────────
blocked_users = set()

def is_blocked(uid):
    return uid in blocked_users

# ── Channel name cache ───────────────────────────────────────
async def get_channel_name(bot):
    global channel_name_cache
    if channel_name_cache:
        return channel_name_cache
    try:
        chat = await bot.get_chat(CHANNEL_ID)
        channel_name_cache = chat.title or "OUR"
    except Exception:
        channel_name_cache = "OUR"
    return channel_name_cache

# ── User state management ────────────────────────────────────
def get_user(uid):
    return channel_users.get(uid)

def upsert_user(uid):
    if uid not in channel_users:
        channel_users[uid] = {"messages": [], "video_count": BASE_VIDEO_COUNT}
    else:
        channel_users[uid]["video_count"] += random.randint(50, 200)
        channel_users[uid]["messages"] = []
    return channel_users[uid]

# ── URL & button helpers ─────────────────────────────────────
def share_url():
    return "https://t.me/share/url?url=" + quote(CHANNEL_LINK) + "&text=" + quote("Check this out! \U0001f525 Join now!")

def make_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001f4e4  SHARE NOW \u2014 IT'S FREE", url=share_url())],
        [InlineKeyboardButton("\u26a1  INSTANT ACCESS", url=PAYMENT_LINK)],
    ])

# ── Auto-delete scheduler ───────────────────────────────────
async def schedule_delete(bot, chat_id, message_ids, delay):
    await asyncio.sleep(delay)
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass

# ── Main content sender ─────────────────────────────────────
async def send_content(bot, chat_id, state):
    channel_name = await get_channel_name(bot)
    vid_count = f"{state['video_count']:,}"

    all_msgs = []

    # Heart with effect
    try:
        heart_msg = await bot.send_message(
            chat_id=chat_id,
            text="\u2764\ufe0f",
            message_effect_id=HEART_EFFECT_ID,
        )
        all_msgs.append(heart_msg.message_id)
    except Exception as e:
        logger.warning("Heart effect error: " + str(e))

    # Videos (protected content + spoiler)
    video_msgs = []
    for label, vid_id in [
        ("VIDEO_1_ID", VIDEO_1_ID),
        ("VIDEO_2_ID", VIDEO_2_ID),
    ]:
        if not vid_id:
            logger.warning(label + " is empty!")
            continue
        try:
            msg = await bot.send_video(
                chat_id=chat_id,
                video=vid_id,
                protect_content=True,
                supports_streaming=True,
                has_spoiler=True,
            )
            video_msgs.append(msg.message_id)
            logger.info(label + " sent to " + str(chat_id))
        except Exception as e:
            logger.error(label + " error: " + str(e))

    # Promo text
    text = (
        "\U0001f512 *" + channel_name.upper() + " \u2014 EXCLUSIVE PRIVATE CHANNEL*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n\n"
        "\U0001f381 *SHARE = FREE ACCESS*\n\n"
        "\U0001f4ca *0 / 2 SHARES COMPLETED*\n\n"
        "\U0001f4e2 Share this channel to *2 groups* to unlock\n"
        "*" + vid_count + " exclusive videos* for FREE!\n\n"
        "\u2705 Verification is *instant & automatic*\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u26a1 *Or get FULL ACCESS now for only \u20b1205!*"
    )
    info = await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=make_buttons())
    all_msgs.append(info.message_id)

    # Videos = 10 sec delete
    if video_msgs:
        asyncio.create_task(schedule_delete(bot, chat_id, video_msgs, VIDEO_DELETE_DELAY))
    # Heart + promo = 3 min delete
    if all_msgs:
        asyncio.create_task(schedule_delete(bot, chat_id, all_msgs, CHAT_DELETE_DELAY))

# ── Handlers ─────────────────────────────────────────────────
async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    join_req = update.chat_join_request
    user = join_req.from_user
    if join_req.chat.id != CHANNEL_ID:
        return
    if is_blocked(user.id):
        return
    logger.info("Join request: " + str(user.id) + " (" + str(user.full_name) + ")")
    state = upsert_user(user.id)
    await send_content(context.bot, user.id, state)

async def auto_reply_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    uid = update.effective_user.id
    if uid == ADMIN_ID:
        return
    if is_blocked(uid):
        return
    state = get_user(uid)
    if state is None:
        return
    state["video_count"] += random.randint(10, 50)
    msg = await update.message.reply_text("SHARE!")

    messages_to_delete = [update.message.message_id, msg.message_id]
    asyncio.create_task(schedule_delete(context.bot, update.effective_chat.id, messages_to_delete, CHAT_DELETE_DELAY))

# ── Admin commands ───────────────────────────────────────────
async def get_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if update.message and update.message.video:
        fid = update.message.video.file_id
        await update.message.reply_text(
            "\u2705 *file_id for this bot:*\n\n`" + fid + "`",
            parse_mode="Markdown"
        )

async def test_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Testing videos...")
    for label, vid_id in [("VIDEO_1_ID", VIDEO_1_ID), ("VIDEO_2_ID", VIDEO_2_ID)]:
        if not vid_id:
            await update.message.reply_text(label + " EMPTY!")
            continue
        try:
            await context.bot.send_video(chat_id=update.effective_chat.id, video=vid_id, protect_content=True, supports_streaming=True)
            await update.message.reply_text(label + " OK!")
        except Exception as e:
            await update.message.reply_text(label + " FAILED: " + str(e))

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /block <user_id>")
        return
    try:
        target = int(context.args[0])
        blocked_users.add(target)
        channel_users.pop(target, None)
        await update.message.reply_text("\u2705 Blocked user " + str(target))
    except ValueError:
        await update.message.reply_text("\u274c Invalid user ID")

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /unblock <user_id>")
        return
    try:
        target = int(context.args[0])
        blocked_users.discard(target)
        await update.message.reply_text("\u2705 Unblocked user " + str(target))
    except ValueError:
        await update.message.reply_text("\u274c Invalid user ID")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = (
        "\U0001f4ca *Bot Stats*\n\n"
        "Users tracked: *" + str(len(channel_users)) + "*\n"
        "Blocked users: *" + str(len(blocked_users)) + "*\n"
        "Video delete: *" + str(VIDEO_DELETE_DELAY) + "s*\n"
        "Chat delete: *" + str(CHAT_DELETE_DELAY) + "s*"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ── Main ─────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Admin commands
    app.add_handler(CommandHandler("testvideo", test_video))
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("unblock", unblock_user))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.VIDEO & filters.User(ADMIN_ID), get_file_id))

    # User handlers
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    app.add_handler(MessageHandler(filters.ALL, auto_reply_share))

    logger.info("Bot running.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
