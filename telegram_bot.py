"""
Telegram bot for the Air Quality Monitoring System.

Commands:
  /start      — Project description
  /map        — Send interactive city map (HTML)
  /trend      — Show PM2.5 city trend

Location message → nearest sensor + AI advice
"""

import logging
import os
import tempfile

from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import settings
from db.database import init_db, db_session
from services.air_quality import (
    get_all_sensors_with_latest,
    get_nearest_sensor_reading,
    classify_pm25,
)
from services.map_generator import generate_city_map
from services.trend_analyzer import get_city_trend
from services.ai_advisor import get_air_quality_advice

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Persistent keyboard ────────────────────────────────────────────────────
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🗺 Карта"), KeyboardButton("📈 Тренд")],
        [KeyboardButton("📍 Моё местоположение", request_location=True)],
    ],
    resize_keyboard=True,
)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message with project overview."""
    text = (
        "🌬️ *Мониторинг качества воздуха — Нукус*\n\n"
        "Эта система в режиме реального времени собирает данные "
        "с сети датчиков PM2.5 / PM10, расположенных по всему городу.\n\n"
        "📡 *Что умеет бот:*\n"
        "• 🗺 */map* — интерактивная карта с датчиками\n"
        "• 📈 */trend* — динамика загрязнения за последние часы\n"
        "• 📍 *Геолокация* — ближайший датчик + AI-рекомендация\n\n"
        "Шкала загрязнения:\n"
        "🟢 0–50 — Хорошо\n"
        "🟡 51–100 — Умеренно\n"
        "🔴 101–200 — Плохо\n"
        "🚨 200+ — Опасно\n\n"
        "Нажмите кнопку ниже или введите команду."
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


async def cmd_map(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send the city map as an HTML document."""
    await update.message.reply_text("🗺 Генерирую карту… подождите немного.")

    try:
        async with db_session() as db:
            sensor_data = await get_all_sensors_with_latest(db)

        if not sensor_data:
            await update.message.reply_text(
                "⚠️ Нет данных от датчиков. Проверьте соединение с сетью датчиков."
            )
            return

        # Generate map to a temp file
        fd, map_path = tempfile.mkstemp(suffix=".html", prefix="airmap_")
        os.close(fd)
        generate_city_map(sensor_data, output_path=map_path)

        with open(map_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename="nukus_air_quality.html",
                caption=(
                    f"🗺 Карта качества воздуха — Нукус\n"
                    f"📡 Датчиков: {len(sensor_data)}\n"
                    f"Откройте файл в браузере для интерактивного просмотра."
                ),
            )

        os.unlink(map_path)
        logger.info("Map sent to user %s", update.effective_user.id)

    except Exception as exc:
        logger.exception("Map generation error: %s", exc)
        await update.message.reply_text("❌ Ошибка при генерации карты. Попробуйте позже.")


async def cmd_trend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show city-wide PM2.5 trend."""
    try:
        async with db_session() as db:
            trend = await get_city_trend(db)

        text = (
            f"📊 *Тренд качества воздуха — Нукус*\n\n"
            f"{trend['emoji']} {trend['message']}\n"
        )

        if trend.get("recent_avg") and trend.get("old_avg"):
            text += (
                f"\n📅 Период анализа: {settings.TREND_HOURS}ч\n"
                f"• Предыдущий период: {trend['old_avg']:.1f} μg/m³\n"
                f"• Текущий период: {trend['recent_avg']:.1f} μg/m³\n"
                f"• Изменение: {trend['change_pct']:+.1f}%"
            )

        await update.message.reply_text(text, parse_mode="Markdown")

    except Exception as exc:
        logger.exception("Trend error: %s", exc)
        await update.message.reply_text("❌ Ошибка при получении тренда.")


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process user's geolocation and return nearest sensor + AI advice."""
    loc = update.message.location
    user_lat, user_lon = loc.latitude, loc.longitude

    await update.message.reply_text("📍 Ищу ближайший датчик…")

    try:
        async with db_session() as db:
            reading = await get_nearest_sensor_reading(db, user_lat, user_lon)

        if reading is None:
            await update.message.reply_text(
                "⚠️ Рядом нет датчиков с актуальными данными."
            )
            return

        level = classify_pm25(reading["pm25"])

        # Distance calculation for display
        from utils.geo import haversine_km
        dist_km = haversine_km(user_lat, user_lon, reading["lat"], reading["lon"])

        ts_str = reading["timestamp"].strftime("%d.%m.%Y %H:%M") if reading.get("timestamp") else "—"

        status_text = (
            f"📡 *Ближайший датчик:* `{reading['device_id']}`\n"
            f"📏 Расстояние: {dist_km:.2f} км\n\n"
            f"🌫 PM2.5: *{reading['pm25']:.1f}* μg/m³\n"
            f"💨 PM10:  *{reading['pm10']:.1f}* μg/m³\n"
            f"🏷 Статус: {level.emoji} *{level.label}*\n"
            f"🕐 Обновлено: {ts_str}\n\n"
            f"🤖 *AI-рекомендация:*"
        )

        await update.message.reply_text(status_text, parse_mode="Markdown")

        # Get AI recommendation
        advice = await get_air_quality_advice(
            reading["pm25"], reading["pm10"], location_name="вашем районе"
        )
        await update.message.reply_text(advice)

    except Exception as exc:
        logger.exception("Location handler error: %s", exc)
        await update.message.reply_text("❌ Произошла ошибка. Попробуйте позже.")


async def handle_keyboard_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route text-button presses from the reply keyboard."""
    text = update.message.text

    if text == "🗺 Карта":
        await cmd_map(update, context)
    elif text == "📈 Тренд":
        await cmd_trend(update, context)
    else:
        await update.message.reply_text(
            "Используйте кнопки ниже или команды /map и /trend.",
            reply_markup=MAIN_KEYBOARD,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def post_init(application: Application) -> None:
    """Initialise DB before the bot starts polling."""
    await init_db()
    logger.info("Bot database initialised.")


def main() -> None:
    application = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Register handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("map", cmd_map))
    application.add_handler(CommandHandler("trend", cmd_trend))
    application.add_handler(MessageHandler(filters.LOCATION, handle_location))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_keyboard_text)
    )

    logger.info("Bot polling started …")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
