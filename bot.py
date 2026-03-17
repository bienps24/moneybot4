import asyncio
import logging
import os
import random
import time
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
VIDEO_3_ID   = os.environ.get("VIDEO_3_ID", "")
VIDEO_4_ID   = os.environ.get("VIDEO_4_ID", "")

VIDEO_DELETE_DELAY = 10       # videos auto-delete after 10 seconds
CHAT_DELETE_DELAY  = 180      # other messages after 3 minutes
HEART_EFFECT_ID    = "5159385139981059251"
BASE_VIDEO_COUNT   = 30000

# Security limits
USER_COOLDOWN_SEC     = 60    # min seconds between join requests per user
MAX_REQUESTS_PER_HOUR = 5     # max triggers per user per hour
BAN_THRESHOLD         = 15    # auto-ignore abusers

# Per-user state
channel_users = {}
channel_name_cache = ""

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

def get_user(uid):
    return channel_users.get(uid)

def upsert_user(uid):
    now = time.time()
    if uid not in channel_users:
        channel_users[uid] = {
            "messages": [], "video_count": BASE_VIDEO_COUNT,
            "last_join": 0.0, "hourly_hits": 0, "hour_start": now, "banned": False,
        }
    else:
        channel_users[uid]["video_count"] += random.randint(50, 200)
        channel_users[uid]["messages"] = []
    return channel_users[uid]

def is_rate_limited(uid):
    u = channel_users.get(uid)
    if u is None:
        return False
    now = time.time()
    if u.get("banned"):
        return True
    if now - u.get("last_join", 0) < USER_COOLDOWN_SEC:
        logger.warning("Cooldown block: " + str(uid))
        return True
    if now - u.get("hour_start", 0) > 3600:
        u["hourly_hits"] = 0
        u["hour_start"] = now
    u["hourly_hits"] = u.get("hourly_hits", 0) + 1
    if u["hourly_hits"] > BAN_THRESHOLD:
        u["banned"] = True
        logger.warning("Auto-banned abuser: " + str(uid))
        return True
    if u["hourly_hits"] > MAX_REQUESTS_PER_HOUR:
        logger.warning("Hourly limit hit: " + str(uid))
        return True
    u["last_join"] = now
    return False

def share_url():
    return "https://t.me/share/url?url=" + quote(CHANNEL_LINK) + "&text=" + quote("join our exclusive group")

def make_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001f4e4  SHARE FOR MORE", url=share_url())],
        [InlineKeyboardButton("\U0001f4b3  PAY FOR ACCESS \u2014 \u20b1205", url=PAYMENT_LINK)],
    ])

async def schedule_delete(bot, chat_id, message_ids, delay):
    await asyncio.sleep(delay)
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass

def get_video_list():
    videos = [
        ("VIDEO_1_ID", VIDEO_1_ID),
        ("VIDEO_2_ID", VIDEO_2_ID),
        ("VIDEO_3_ID", VIDEO_3_ID),
        ("VIDEO_4_ID", VIDEO_4_ID),
    ]
    available = [(lbl, fid) for lbl, fid in videos if fid]
    random.shuffle(available)
    return available

async def send_content(bot, chat_id, state):
    channel_name = await get_channel_name(bot)
    vid_count = f"{state['video_count']:,}"

    # Heart with effect
    heart_msg_id = None
    try:
        heart_msg = await bot.send_message(
            chat_id=chat_id,
            text="\u2764\ufe0f",
            message_effect_id=HEART_EFFECT_ID,
        )
        heart_msg_id = heart_msg.message_id
    except Exception as e:
        logger.warning("Heart effect error: " + str(e))

    # Send ALL 4 videos (protected — no save, no forward, no screenshot)
    video_msgs = []
    for label, vid_id in get_video_list():
        if not vid_id:
            logger.warning(label + " is empty!")
            continue
        try:
            msg = await bot.send_video(chat_id=chat_id, video=vid_id, protect_content=True, supports_streaming=True)
            video_msgs.append(msg.message_id)
            logger.info(label + " sent to " + str(chat_id))
        except Exception as e:
            logger.error(label + " error: " + str(e))

    # Promo text
    text = (
        "\u26a0\ufe0f *" + channel_name.upper() + " \u2014 CHANNEL IS PRIVATE*\n"
        "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
        "\U0001f34c\U0001f4a6 *SHARE = FREE CONTENT*\n\n"
        "\U0001f4ca *0 / 2 SHARES COMPLETED*\n\n"
        "\U0001f4e2 Share this channel to *2 groups* to unlock\n"
        "access to *" + vid_count + " exclusive videos*\n\n"
        "\u2705 Verification is *automatic*\n"
        "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        "\U0001f512 *Or unlock full access instantly below*"
    )

    info = await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=make_buttons())

    # Videos = 10 second delete
    if video_msgs:
        asyncio.create_task(schedule_delete(bot, chat_id, video_msgs, VIDEO_DELETE_DELAY))

    # Heart + Promo = 3 minutes delete
    other_msgs = []
    if heart_msg_id:
        other_msgs.append(heart_msg_id)
    other_msgs.append(info.message_id)
    asyncio.create_task(schedule_delete(bot, chat_id, other_msgs, CHAT_DELETE_DELAY))

async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    join_req = update.chat_join_request
    user = join_req.from_user
    if join_req.chat.id != CHANNEL_ID:
        return
    logger.info("Join request: " + str(user.id) + " (" + str(user.full_name) + ")")

    # Rate-limit check BEFORE sending content
    if is_rate_limited(user.id):
        logger.info("Rate-limited, ignoring: " + str(user.id))
        return

    state = upsert_user(user.id)
    await send_content(context.bot, user.id, state)

async def auto_reply_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    uid = update.effective_user.id
    if uid == ADMIN_ID:
        return
    state = get_user(uid)
    if state is None:
        # Unknown user — delete silently
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
        except Exception:
            pass
        return
    state["video_count"] += random.randint(10, 50)
    msg = await update.message.reply_text("SHARE!")

    messages_to_delete = [update.message.message_id, msg.message_id]
    asyncio.create_task(schedule_delete(context.bot, update.effective_chat.id, messages_to_delete, CHAT_DELETE_DELAY))

async def block_forwarded(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    uid = update.effective_user.id
    if uid == ADMIN_ID:
        return
    if update.message.forward_date or update.message.forward_origin:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.message_id)
        except Exception:
            pass
        logger.warning("Deleted forwarded msg from " + str(uid))

async def get_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if update.message and update.message.video:
        fid = update.message.video.file_id
        await update.message.reply_text(
            "\u2705 *file\\_id for this bot:*\n\n`" + fid + "`",
            parse_mode="Markdown"
        )

async def test_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("Testing all 4 videos...")
    for label, vid_id in [("VIDEO_1_ID", VIDEO_1_ID), ("VIDEO_2_ID", VIDEO_2_ID), ("VIDEO_3_ID", VIDEO_3_ID), ("VIDEO_4_ID", VIDEO_4_ID)]:
        if not vid_id:
            await update.message.reply_text(label + " EMPTY!")
            continue
        try:
            await context.bot.send_video(chat_id=update.effective_chat.id, video=vid_id, protect_content=True, supports_streaming=True)
            await update.message.reply_text(label + " OK!")
        except Exception as e:
            await update.message.reply_text(label + " FAILED: " + str(e))

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    total = len(channel_users)
    banned = sum(1 for u in channel_users.values() if u.get("banned"))
    await update.message.reply_text(
        "\U0001f4ca *Bot Stats*\nTotal users: `" + str(total) + "`\nBanned: `" + str(banned) + "`",
        parse_mode="Markdown"
    )

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        target = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    u = channel_users.get(target)
    if u:
        u["banned"] = False
        u["hourly_hits"] = 0
        await update.message.reply_text("\u2705 Unbanned " + str(target))
    else:
        await update.message.reply_text("User not found.")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("testvideo", test_video))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(MessageHandler(filters.VIDEO & filters.User(ADMIN_ID), get_file_id))
    app.add_handler(ChatJoinRequestHandler(handle_join_request))
    app.add_handler(MessageHandler(filters.FORWARDED & ~filters.User(ADMIN_ID), block_forwarded))
    app.add_handler(MessageHandler(filters.ALL, auto_reply_share))
    logger.info("Bot running - 4 videos, 10s/3min delete, protected.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
