"""
Telegram bot: Google Calendar event planner with Google Meet.

Conversation flow:
  1. /plan  →  ask event title
  2. title  →  ask date (DD.MM.YYYY)
  3. date   →  ask start time (HH:MM)
  4. time   →  ask end time (HH:MM)
  5. time   →  ask attendee emails (comma separated)
  6. emails →  create event, send confirmation
"""

import logging
import os
import re
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from calendar_service import create_event_with_meet

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TITLE, DATE, START_TIME, END_TIME, EMAILS = range(5)

DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Merhaba! 👋 Google Takvim planlayıcısına hoş geldiniz.\n"
        "Etkinlik oluşturmak için /plan komutunu kullanın."
    )


async def plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("📝 Etkinlik adını girin:")
    return TITLE


async def receive_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["title"] = update.message.text.strip()
    await update.message.reply_text("📅 Tarihi girin (GG.AA.YYYY formatında, örn: 25.10.2024):")
    return DATE


async def receive_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not DATE_RE.match(text):
        await update.message.reply_text("❌ Geçersiz format. Lütfen GG.AA.YYYY formatında girin (örn: 25.10.2024):")
        return DATE
    try:
        datetime.strptime(text, "%d.%m.%Y")
    except ValueError:
        await update.message.reply_text("❌ Geçersiz tarih. Tekrar deneyin:")
        return DATE
    ctx.user_data["date"] = text
    await update.message.reply_text("⏰ Başlangıç saatini girin (SS:DD formatında, örn: 14:00):")
    return START_TIME


async def receive_start_time(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not TIME_RE.match(text):
        await update.message.reply_text("❌ Geçersiz format. Lütfen SS:DD formatında girin (örn: 14:00):")
        return START_TIME
    ctx.user_data["start_time"] = text
    await update.message.reply_text("⏰ Bitiş saatini girin (SS:DD formatında, örn: 15:00):")
    return END_TIME


async def receive_end_time(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not TIME_RE.match(text):
        await update.message.reply_text("❌ Geçersiz format. Lütfen SS:DD formatında girin (örn: 15:00):")
        return END_TIME

    date = ctx.user_data["date"]
    start = ctx.user_data["start_time"]
    start_dt = datetime.strptime(f"{date} {start}", "%d.%m.%Y %H:%M")
    end_dt = datetime.strptime(f"{date} {text}", "%d.%m.%Y %H:%M")

    if end_dt <= start_dt:
        await update.message.reply_text("❌ Bitiş saati başlangıç saatinden sonra olmalı. Tekrar girin:")
        return END_TIME

    ctx.user_data["end_time"] = text
    await update.message.reply_text(
        "📧 Davet göndermek istediğiniz e-posta adreslerini girin.\n"
        "Birden fazla adres için virgülle ayırın:\n"
        "örn: ali@gmail.com, veli@gmail.com"
    )
    return EMAILS


async def receive_emails(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    emails = [e.strip() for e in raw.split(",")]
    valid = [e for e in emails if EMAIL_RE.match(e)]

    if not valid:
        await update.message.reply_text("❌ Geçerli e-posta adresi bulunamadı. Tekrar girin:")
        return EMAILS

    invalid = [e for e in emails if not EMAIL_RE.match(e)]
    if invalid:
        await update.message.reply_text(
            f"⚠️ Şu adresler geçersiz sayıldı ve atlandı: {', '.join(invalid)}\n"
            "Devam ediliyor..."
        )

    title = ctx.user_data["title"]
    date = ctx.user_data["date"]
    start_time = ctx.user_data["start_time"]
    end_time = ctx.user_data["end_time"]

    start_iso = datetime.strptime(f"{date} {start_time}", "%d.%m.%Y %H:%M").isoformat()
    end_iso = datetime.strptime(f"{date} {end_time}", "%d.%m.%Y %H:%M").isoformat()

    await update.message.reply_text("⏳ Etkinlik oluşturuluyor, lütfen bekleyin...")

    try:
        event = create_event_with_meet(title, start_iso, end_iso, valid)
        meet_link = (
            event.get("conferenceData", {})
            .get("entryPoints", [{}])[0]
            .get("uri", "Link oluşturulamadı")
        )
        event_link = event.get("htmlLink", "")

        attendees_str = "\n".join(f"  • {e}" for e in valid)
        msg = (
            f"✅ Etkinlik başarıyla oluşturuldu!\n\n"
            f"📌 *{title}*\n"
            f"📅 {date} | {start_time} – {end_time}\n\n"
            f"🔗 Google Meet:\n{meet_link}\n\n"
            f"📋 Takvim linki:\n{event_link}\n\n"
            f"📧 Davet gönderildi:\n{attendees_str}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        logger.error("Event creation failed: %s", e)
        await update.message.reply_text(
            f"❌ Etkinlik oluşturulurken hata oluştu:\n`{e}`\n\n"
            "Lütfen Google kimlik bilgilerinizi (credentials.json / token.pickle) kontrol edin.",
            parse_mode="Markdown",
        )

    ctx.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data.clear()
    await update.message.reply_text("🚫 İşlem iptal edildi. Yeni etkinlik için /plan kullanın.")
    return ConversationHandler.END


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set.")

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("plan", plan)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)],
            START_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_start_time)],
            END_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_end_time)],
            EMAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_emails)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)

    logger.info("Bot başlatılıyor...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
