"""
Run this script ONCE to get the Telegram file_id of your 4 videos.
Send videos to your bot one by one while this is running.
It will label them VIDEO_1_ID through VIDEO_4_ID automatically.
Copy each file_id into Railway env vars.
"""
import os
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.environ["BOT_TOKEN"]
logging.basicConfig(level=logging.INFO)

video_count = 0
TOTAL_VIDEOS = 4


async def get_file_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global video_count
    if update.message.video:
        video_count += 1
        fid = update.message.video.file_id
        label = "VIDEO_" + str(video_count) + "_ID"

        print("\n========================================")
        print("\u2705 " + label + ":")
        print(fid)
        print("========================================\n")

        await update.message.reply_text(
            "\u2705 *" + label + "*\n\n`" + fid + "`\n\n"
            + ("(" + str(video_count) + "/" + str(TOTAL_VIDEOS) + " done)" if video_count < TOTAL_VIDEOS
               else "\U0001f389 All " + str(TOTAL_VIDEOS) + " videos captured! You can stop the script now."),
            parse_mode="Markdown"
        )

        if video_count >= TOTAL_VIDEOS:
            print("\U0001f389 All " + str(TOTAL_VIDEOS) + " video IDs captured! Paste them in Railway env vars.")


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.VIDEO, get_file_id))
    print("Send " + str(TOTAL_VIDEOS) + " videos to your bot one by one...")
    print("Each will be labeled VIDEO_1_ID through VIDEO_" + str(TOTAL_VIDEOS) + "_ID\n")
    app.run_polling()


if __name__ == "__main__":
    main()
