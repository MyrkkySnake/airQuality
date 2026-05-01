"""
Trend analysis: compare recent vs older measurements to detect
whether air quality is improving, worsening, or stable.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Sensor, Measurement
from config import settings

logger = logging.getLogger(__name__)

# How many % change is considered "significant"
CHANGE_THRESHOLD_PCT = 10.0


async def _average_pm25_in_window(
    db: AsyncSession,
    start: datetime,
    end: datetime,
) -> Optional[float]:
    """Return city-wide average PM2.5 across all sensors in [start, end]."""
    result = await db.execute(
        select(func.avg(Measurement.pm25)).where(
            Measurement.timestamp >= start,
            Measurement.timestamp <= end,
        )
    )
    return result.scalar()


async def get_city_trend(db: AsyncSession) -> dict:
    """
    Compare the last N hours vs the previous N hours.
    Returns a dict with trend label and numeric values.
    """
    now = datetime.utcnow()
    hours = settings.TREND_HOURS

    recent_end = now
    recent_start = now - timedelta(hours=hours)
    old_end = recent_start
    old_start = old_end - timedelta(hours=hours)

    recent_avg = await _average_pm25_in_window(db, recent_start, recent_end)
    old_avg = await _average_pm25_in_window(db, old_start, old_end)

    if recent_avg is None:
        return {
            "trend": "unknown",
            "emoji": "❓",
            "message": "Недостаточно данных для анализа тренда.",
            "recent_avg": None,
            "old_avg": None,
            "change_pct": None,
        }

    if old_avg is None or old_avg == 0:
        # No historical data — just report current value
        return {
            "trend": "unknown",
            "emoji": "📊",
            "message": f"Текущий средний PM2.5: {recent_avg:.1f} μg/m³ (история недоступна).",
            "recent_avg": recent_avg,
            "old_avg": None,
            "change_pct": None,
        }

    change_pct = ((recent_avg - old_avg) / old_avg) * 100

    if change_pct > CHANGE_THRESHOLD_PCT:
        trend, emoji = "worsening", "📈"
        message = (
            f"Ситуация ухудшается ↑ на {change_pct:.1f}%.\n"
            f"Средний PM2.5 вырос с {old_avg:.1f} до {recent_avg:.1f} μg/m³ "
            f"за последние {hours * 2} ч."
        )
    elif change_pct < -CHANGE_THRESHOLD_PCT:
        trend, emoji = "improving", "📉"
        message = (
            f"Ситуация улучшается ↓ на {abs(change_pct):.1f}%.\n"
            f"Средний PM2.5 снизился с {old_avg:.1f} до {recent_avg:.1f} μg/m³ "
            f"за последние {hours * 2} ч."
        )
    else:
        trend, emoji = "stable", "➡️"
        message = (
            f"Ситуация стабильна (изменение {change_pct:+.1f}%).\n"
            f"Средний PM2.5: {recent_avg:.1f} μg/m³."
        )

    return {
        "trend": trend,
        "emoji": emoji,
        "message": message,
        "recent_avg": round(recent_avg, 2),
        "old_avg": round(old_avg, 2),
        "change_pct": round(change_pct, 2),
    }


async def get_sensor_trend(db: AsyncSession, device_id: str) -> dict:
    """
    Per-sensor trend for the given device_id.
    Same window logic as city-wide but filtered to one sensor.
    """
    from db.models import Sensor

    sensor_result = await db.execute(
        select(Sensor).where(Sensor.device_id == device_id)
    )
    sensor = sensor_result.scalars().first()

    if not sensor:
        return {"trend": "unknown", "emoji": "❓", "message": "Датчик не найден."}

    now = datetime.utcnow()
    hours = settings.TREND_HOURS

    async def avg_for_sensor(start: datetime, end: datetime) -> Optional[float]:
        r = await db.execute(
            select(func.avg(Measurement.pm25)).where(
                Measurement.sensor_id == sensor.id,
                Measurement.timestamp >= start,
                Measurement.timestamp <= end,
            )
        )
        return r.scalar()

    recent_avg = await avg_for_sensor(now - timedelta(hours=hours), now)
    old_avg = await avg_for_sensor(
        now - timedelta(hours=hours * 2), now - timedelta(hours=hours)
    )

    # Reuse city logic — just call with dummy db wrapper
    if recent_avg is None:
        return {"trend": "unknown", "emoji": "❓", "message": "Нет данных за последние часы."}

    if old_avg is None or old_avg == 0:
        return {
            "trend": "unknown",
            "emoji": "📊",
            "message": f"PM2.5 сейчас: {recent_avg:.1f} μg/m³ (история недоступна).",
        }

    change_pct = ((recent_avg - old_avg) / old_avg) * 100

    if change_pct > CHANGE_THRESHOLD_PCT:
        return {"trend": "worsening", "emoji": "📈",
                "message": f"PM2.5 растёт (+{change_pct:.1f}%): {recent_avg:.1f} μg/m³"}
    elif change_pct < -CHANGE_THRESHOLD_PCT:
        return {"trend": "improving", "emoji": "📉",
                "message": f"PM2.5 снижается ({change_pct:.1f}%): {recent_avg:.1f} μg/m³"}
    else:
        return {"trend": "stable", "emoji": "➡️",
                "message": f"PM2.5 стабилен ({change_pct:+.1f}%): {recent_avg:.1f} μg/m³"}
