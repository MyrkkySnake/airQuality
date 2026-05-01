"""
AI Advisor: generates health recommendations via OpenAI API
based on PM2.5 and PM10 readings.
"""

import logging
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "Ты эксперт по качеству воздуха и здоровью. "
    "Давай короткие (3–5 предложений), понятные советы на русском языке "
    "на основе измерений PM2.5 и PM10. "
    "Советы должны быть практичными: нужна ли маска, безопасно ли выходить на улицу, "
    "стоит ли открывать окна. "
    "НЕ делай долгосрочных прогнозов. Отвечай только по текущей ситуации."
)


async def get_air_quality_advice(pm25: float, pm10: float, location_name: str = "вашем районе") -> str:
    """
    Ask OpenAI for a short health recommendation based on current readings.

    Args:
        pm25: current PM2.5 μg/m³
        pm10: current PM10 μg/m³
        location_name: human-readable name of the location (for context)

    Returns:
        AI-generated recommendation string (Russian).
    """
    user_message = (
        f"Текущие показатели в {location_name}:\n"
        f"• PM2.5 = {pm25:.1f} μg/m³\n"
        f"• PM10  = {pm10:.1f} μg/m³\n\n"
        "Дай конкретные рекомендации по здоровью."
    )

    try:
        response = await _client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=300,
            temperature=0.5,
        )
        advice = response.choices[0].message.content.strip()
        logger.info("AI advice generated for PM2.5=%.1f PM10=%.1f", pm25, pm10)
        return advice

    except Exception as exc:
        logger.error("OpenAI API error: %s", exc)
        # Fallback: rule-based advice
        return _fallback_advice(pm25)


def _fallback_advice(pm25: float) -> str:
    """Rule-based fallback if OpenAI is unavailable."""
    if pm25 <= 50:
        return (
            "🟢 Воздух чистый. Можно находиться на улице без ограничений, "
            "заниматься спортом и держать окна открытыми."
        )
    elif pm25 <= 100:
        return (
            "🟡 Умеренное загрязнение. Чувствительным группам (дети, пожилые, "
            "астматики) рекомендуется сократить время на улице. "
            "Окна лучше прикрыть в часы пик."
        )
    elif pm25 <= 200:
        return (
            "🔴 Высокий уровень PM2.5. Рекомендуем надеть маску (FFP2/N95) на улице, "
            "ограничить физические нагрузки, закрыть окна и использовать воздухоочиститель."
        )
    else:
        return (
            "🚨 ОПАСНЫЙ уровень загрязнения! Оставайтесь дома, плотно закройте окна и двери. "
            "На улице обязательна маска FFP3. Уязвимым группам выходить категорически не рекомендуется."
        )
