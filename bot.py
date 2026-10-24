"""
Telegram bot: Google Calendar event planner with Google Meet.

Commands:
  /plan   → create event (title → date → start → end → emails)
  /list   → list upcoming events
  /delete → pick and delete an event
  /edit   → pick event and edit (time / add attendees)
  /cancel → cancel current operation
"""

import logging
import os
import re
from datetime import datetime

import dateparser

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from calendar_service import (
    create_event_with_meet,
    list_upcoming_events,
    delete_event,
    update_event,
)

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# /plan states
TITLE, DATE, START_TIME, END_TIME, EMAILS = range(5)

# /edit states (offset to avoid collision)
EDIT_PICK_FIELD, EDIT_START, EDIT_END, EDIT_ADD_EMAILS = range(10, 14)

TIME_RE = re.compile(r"^\d{2}:\d{2}$")
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


# ── helpers ──────────────────────────────────────────────────────────────────

def _event_summary(event: dict) -> str:
    title = event.get("summary", "(isimsiz)")
    start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))
    try:
        dt = datetime.fromisoformat(start)
        date_str = dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        date_str = start
    return f"{title} — {date_str}"


def _events_keyboard(events: list[dict], prefix: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(_event_summary(e), callback_data=f"{prefix}:{e['id']}")]
        for e in events
    ]
    return InlineKeyboardMarkup(buttons)


def _parse_time(text: str) -> str | None:
    text = text.strip()
    if TIME_RE.match(text):
        return text
    return None


# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Merhaba! 👋 Google Takvim planlayıcısına hoş geldiniz.\n\n"
        "/plan — yeni etkinlik oluştur\n"
        "/list — yaklaşan etkinlikleri listele\n"
        "/delete — etkinlik sil\n"
        "/edit — etkinlik düzenle"
    )


# ── /list ─────────────────────────────────────────────────────────────────────

async def list_events_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Etkinlikler yükleniyor...")
    try:
        events = list_upcoming_events(15)
        if not events:
            await update.message.reply_text("📭 Yaklaşan etkinlik bulunamadı.")
            return
        lines = [f"{i+1}. {_event_summary(e)}" for i, e in enumerate(events)]
        await update.message.reply_text("📅 Yaklaşan etkinlikler:\n\n" + "\n".join(lines))
    except Exception as e:
        logger.error("list error: %s", e)
        await update.message.reply_text(f"❌ Hata: {e}")


# ── /delete ───────────────────────────────────────────────────────────────────

async def delete_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        events = list_upcoming_events(10)
        if not events:
            await update.message.reply_text("📭 Silinecek etkinlik bulunamadı.")
            return
        ctx.user_data["delete_events"] = {e["id"]: e for e in events}
        await update.message.reply_text(
            "🗑 Hangi etkinliği silmek istiyorsunuz?",
            reply_markup=_events_keyboard(events, "del"),
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Hata: {e}")


async def delete_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    event_id = query.data.split(":", 1)[1]
    events = ctx.user_data.get("delete_events", {})
    event = events.get(event_id)
    title = event.get("summary", event_id) if event else event_id
    try:
        delete_event(event_id)
        await query.edit_message_text(f"✅ *{title}* silindi.", parse_mode="Markdown")
    except Exception as e:
        logger.error("delete error: %s", e)
        await query.edit_message_text(f"❌ Silinemedi: {e}")
    ctx.user_data.pop("delete_events", None)


# ── /edit ─────────────────────────────────────────────────────────────────────

async def edit_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        events = list_upcoming_events(10)
        if not events:
            await update.message.reply_text("📭 Düzenlenecek etkinlik bulunamadı.")
            return ConversationHandler.END
        ctx.user_data["edit_events"] = {e["id"]: e for e in events}
        await update.message.reply_text(
            "✏️ Hangi etkinliği düzenlemek istiyorsunuz?",
            reply_markup=_events_keyboard(events, "editpick"),
        )
        return EDIT_PICK_FIELD
    except Exception as e:
        await update.message.reply_text(f"❌ Hata: {e}")
        return ConversationHandler.END


async def edit_pick_event_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_id = query.data.split(":", 1)[1]
    ctx.user_data["edit_event_id"] = event_id
    event = ctx.user_data.get("edit_events", {}).get(event_id, {})
    ctx.user_data["edit_event"] = event

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏰ Başlangıç saatini değiştir", callback_data="editfield:start")],
        [InlineKeyboardButton("⏰ Bitiş saatini değiştir", callback_data="editfield:end")],
        [InlineKeyboardButton("📧 Katılımcı ekle", callback_data="editfield:emails")],
    ])
    await query.edit_message_text(
        f"*{event.get('summary', 'Etkinlik')}* için ne düzenlemek istiyorsunuz?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    return EDIT_PICK_FIELD


async def edit_pick_field_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    field = query.data.split(":", 1)[1]
    ctx.user_data["edit_field"] = field

    if field == "start":
        await query.edit_message_text("⏰ Yeni başlangıç saatini girin (SS:DD, örn: 14:00):")
        return EDIT_START
    elif field == "end":
        await query.edit_message_text("⏰ Yeni bitiş saatini girin (SS:DD, örn: 15:00):")
        return EDIT_END
    elif field == "emails":
        await query.edit_message_text(
            "📧 Eklenecek e-posta adreslerini girin (virgülle ayırın):\n"
            "örn: ali@gmail.com, veli@gmail.com"
        )
        return EDIT_ADD_EMAILS
    return ConversationHandler.END


async def edit_start_time(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    new_time = _parse_time(update.message.text)
    if not new_time:
        await update.message.reply_text("❌ Geçersiz format. SS:DD olarak girin (örn: 14:00):")
        return EDIT_START

    event = ctx.user_data.get("edit_event", {})
    old_start = event.get("start", {}).get("dateTime", "")
    old_end = event.get("end", {}).get("dateTime", "")

    try:
        old_start_dt = datetime.fromisoformat(old_start)
        old_end_dt = datetime.fromisoformat(old_end)
        duration = old_end_dt - old_start_dt

        h, m = map(int, new_time.split(":"))
        new_start_dt = old_start_dt.replace(hour=h, minute=m, second=0, microsecond=0)
        new_end_dt = new_start_dt + duration

        patch = {
            "start": {"dateTime": new_start_dt.isoformat(), "timeZone": "Europe/Istanbul"},
            "end": {"dateTime": new_end_dt.isoformat(), "timeZone": "Europe/Istanbul"},
        }
        update_event(ctx.user_data["edit_event_id"], patch)
        await update.message.reply_text(
            f"✅ Başlangıç saati *{new_time}* olarak güncellendi.\n"
            f"Bitiş saati de *{new_end_dt.strftime('%H:%M')}* olarak ayarlandı.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("edit start error: %s", e)
        await update.message.reply_text(f"❌ Güncellenemedi: {e}")

    ctx.user_data.clear()
    return ConversationHandler.END


async def edit_end_time(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    new_time = _parse_time(update.message.text)
    if not new_time:
        await update.message.reply_text("❌ Geçersiz format. SS:DD olarak girin (örn: 15:00):")
        return EDIT_END

    event = ctx.user_data.get("edit_event", {})
    old_start = event.get("start", {}).get("dateTime", "")

    try:
        old_start_dt = datetime.fromisoformat(old_start)
        h, m = map(int, new_time.split(":"))
        new_end_dt = old_start_dt.replace(hour=h, minute=m, second=0, microsecond=0)

        if new_end_dt <= old_start_dt:
            await update.message.reply_text("❌ Bitiş saati başlangıçtan sonra olmalı. Tekrar girin:")
            return EDIT_END

        patch = {
            "end": {"dateTime": new_end_dt.isoformat(), "timeZone": "Europe/Istanbul"},
        }
        update_event(ctx.user_data["edit_event_id"], patch)
        await update.message.reply_text(
            f"✅ Bitiş saati *{new_time}* olarak güncellendi.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("edit end error: %s", e)
        await update.message.reply_text(f"❌ Güncellenemedi: {e}")

    ctx.user_data.clear()
    return ConversationHandler.END


async def edit_add_emails(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    new_emails = [e.strip() for e in raw.split(",")]
    valid = [e for e in new_emails if EMAIL_RE.match(e)]

    if not valid:
        await update.message.reply_text("❌ Geçerli e-posta adresi bulunamadı. Tekrar girin:")
        return EDIT_ADD_EMAILS

    event = ctx.user_data.get("edit_event", {})
    existing = [a["email"] for a in event.get("attendees", [])]
    combined = list({*existing, *valid})

    try:
        patch = {"attendees": [{"email": e} for e in combined]}
        update_event(ctx.user_data["edit_event_id"], patch)
        added_str = ", ".join(valid)
        await update.message.reply_text(
            f"✅ Katılımcılar eklendi: *{added_str}*",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("edit emails error: %s", e)
        await update.message.reply_text(f"❌ Güncellenemedi: {e}")

    ctx.user_data.clear()
    return ConversationHandler.END


# ── /plan ─────────────────────────────────────────────────────────────────────

async def plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("📝 Etkinlik adını girin:")
    return TITLE


async def receive_title(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data["title"] = update.message.text.strip()
    await update.message.reply_text(
        "📅 Tarihi girin:\n"
        "Örn: yarın · Pazartesi · 25 Ekim · 25.10.2024"
    )
    return DATE


async def receive_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    parsed = dateparser.parse(
        text,
        languages=["tr", "en"],
        settings={"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": False},
    )
    if parsed is None:
        await update.message.reply_text(
            "❌ Tarihi anlayamadım. Tekrar deneyin:\n"
            "Örn: yarın · Pazartesi · 25 Ekim · 25.10.2024"
        )
        return DATE
    ctx.user_data["date"] = parsed.strftime("%d.%m.%Y")
    await update.message.reply_text(
        f"✅ {parsed.strftime('%d %B %Y')} olarak anladım.\n"
        "⏰ Başlangıç saatini girin (SS:DD, örn: 14:00):"
    )
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
            f"❌ Etkinlik oluşturulurken hata oluştu:\n`{e}`",
            parse_mode="Markdown",
        )

    ctx.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data.clear()
    await update.message.reply_text("🚫 İşlem iptal edildi.")
    return ConversationHandler.END


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set.")

    app = (
        Application.builder()
        .token(token)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .build()
    )

    plan_conv = ConversationHandler(
        entry_points=[CommandHandler("plan", plan)],
        states={
            TITLE:      [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title)],
            DATE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)],
            START_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_start_time)],
            END_TIME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_end_time)],
            EMAILS:     [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_emails)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    edit_conv = ConversationHandler(
        entry_points=[CommandHandler("edit", edit_cmd)],
        states={
            EDIT_PICK_FIELD: [
                CallbackQueryHandler(edit_pick_event_callback, pattern=r"^editpick:"),
                CallbackQueryHandler(edit_pick_field_callback, pattern=r"^editfield:"),
            ],
            EDIT_START:      [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_start_time)],
            EDIT_END:        [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_end_time)],
            EDIT_ADD_EMAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_add_emails)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_events_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CallbackQueryHandler(delete_callback, pattern=r"^del:"))
    app.add_handler(plan_conv)
    app.add_handler(edit_conv)

    logger.info("Bot başlatılıyor...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
