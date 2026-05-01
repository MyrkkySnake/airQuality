"""
Air quality business logic:
  • AQI level classification
  • Latest readings per sensor
  • Nearest-sensor lookup for Telegram geolocation
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Sensor, Measurement

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

@dataclass
class AQILevel:
    label: str
    emoji: str
    color: str          # Folium-compatible colour name


def classify_pm25(pm25: float) -> AQILevel:
    """Classify PM2.5 value into a named air quality level."""
    if pm25 <= 50:
        return AQILevel("Хорошо", "🟢", "green")
    elif pm25 <= 100:
        return AQILevel("Умеренно", "🟡", "orange")
    elif pm25 <= 200:
        return AQILevel("Плохо", "🔴", "red")
    else:
        return AQILevel("Опасно", "🚨", "darkred")


def classify_pm10(pm10: float) -> AQILevel:
    """Classify PM10 value using the same breakpoints."""
    return classify_pm25(pm10)   # Same thresholds as PM2.5 for simplicity


# ---------------------------------------------------------------------------
# Data access helpers
# ---------------------------------------------------------------------------

async def get_all_sensors_with_latest(db: AsyncSession) -> list[dict]:
    """
    Return every sensor with its most recent PM2.5 / PM10 reading.
    Sensors with no measurements are included with pm25/pm10 = None.
    """
    sensors_result = await db.execute(select(Sensor))
    sensors = sensors_result.scalars().all()

    output = []
    for sensor in sensors:
        # Subquery: latest timestamp for this sensor
        latest_stmt = (
            select(Measurement)
            .where(Measurement.sensor_id == sensor.id)
            .order_by(Measurement.timestamp.desc())
            .limit(1)
        )
        m_result = await db.execute(latest_stmt)
        measurement = m_result.scalars().first()

        output.append({
            "device_id": sensor.device_id,
            "lat": sensor.lat,
            "lon": sensor.lon,
            "pm25": measurement.pm25 if measurement else None,
            "pm10": measurement.pm10 if measurement else None,
            "timestamp": measurement.timestamp if measurement else None,
        })

    return output


async def get_sensor_latest(db: AsyncSession, device_id: str) -> Optional[dict]:
    """
    Return the latest measurement for a specific device_id, or None.
    """
    sensor_result = await db.execute(
        select(Sensor).where(Sensor.device_id == device_id)
    )
    sensor = sensor_result.scalars().first()
    if not sensor:
        return None

    m_result = await db.execute(
        select(Measurement)
        .where(Measurement.sensor_id == sensor.id)
        .order_by(Measurement.timestamp.desc())
        .limit(1)
    )
    measurement = m_result.scalars().first()
    if not measurement:
        return None

    level = classify_pm25(measurement.pm25)
    return {
        "device_id": sensor.device_id,
        "lat": sensor.lat,
        "lon": sensor.lon,
        "pm25": measurement.pm25,
        "pm10": measurement.pm10,
        "timestamp": measurement.timestamp,
        "level": level,
    }


async def get_nearest_sensor_reading(
    db: AsyncSession, user_lat: float, user_lon: float
) -> Optional[dict]:
    """
    Find the sensor closest to (user_lat, user_lon) and return its latest reading.
    Uses in-Python distance — acceptable for ≤ 200 sensors.
    """
    from utils.geo import find_nearest_sensor

    all_sensors = await get_all_sensors_with_latest(db)
    if not all_sensors:
        return None

    # Only consider sensors that have data
    active = [s for s in all_sensors if s["pm25"] is not None]
    if not active:
        return None

    nearest = find_nearest_sensor(user_lat, user_lon, active)
    if not nearest:
        return None

    level = classify_pm25(nearest["pm25"])
    nearest["level"] = level
    return nearest
