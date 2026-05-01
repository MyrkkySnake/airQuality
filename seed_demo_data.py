"""
Seed script: inserts demo sensors and measurements for Nukus area.
Run once to populate the database for local testing.

Usage:
    python seed_demo_data.py
"""

import asyncio
import random
from datetime import datetime, timedelta

from db.database import init_db, db_session
from db.models import Sensor, Measurement


# ── Demo sensor grid around Nukus city centre ─────────────────────────────
DEMO_SENSORS = [
    {"device_id": "sensor_001", "lat": 42.4597, "lon": 59.6093},  # Centre
    {"device_id": "sensor_002", "lat": 42.4650, "lon": 59.6150},  # NE
    {"device_id": "sensor_003", "lat": 42.4540, "lon": 59.6030},  # SW
    {"device_id": "sensor_004", "lat": 42.4700, "lon": 59.5950},  # NW
    {"device_id": "sensor_005", "lat": 42.4480, "lon": 59.6200},  # SE
    {"device_id": "sensor_006", "lat": 42.4610, "lon": 59.5880},  # W
    {"device_id": "sensor_007", "lat": 42.4530, "lon": 59.6310},  # E
    {"device_id": "sensor_008", "lat": 42.4750, "lon": 59.6100},  # N
    {"device_id": "sensor_009", "lat": 42.4400, "lon": 59.6050},  # S
    {"device_id": "sensor_010", "lat": 42.4620, "lon": 59.6220},  # NE2
]


async def seed():
    await init_db()

    now = datetime.utcnow()

    async with db_session() as db:
        for s_data in DEMO_SENSORS:
            # Create or skip sensor
            from sqlalchemy import select
            result = await db.execute(
                select(Sensor).where(Sensor.device_id == s_data["device_id"])
            )
            sensor = result.scalars().first()

            if sensor is None:
                sensor = Sensor(**s_data)
                db.add(sensor)
                await db.flush()
                print(f"  + Sensor {s_data['device_id']} created (id={sensor.id})")
            else:
                print(f"  ~ Sensor {s_data['device_id']} already exists (id={sensor.id})")

            # Generate 48 hours of readings (one per hour)
            for hours_ago in range(48, -1, -1):
                ts = now - timedelta(hours=hours_ago)
                # Simulate daily cycle: worse in morning and evening
                hour = ts.hour
                base_pm25 = 60 + 40 * abs(hour - 12) / 12  # peak at midnight/noon edges

                # Add some spatial variation per sensor
                sensor_offset = hash(s_data["device_id"]) % 30

                pm25 = max(5, base_pm25 + sensor_offset + random.gauss(0, 10))
                pm10 = pm25 * random.uniform(1.3, 1.8)

                measurement = Measurement(
                    sensor_id=sensor.id,
                    pm25=round(pm25, 1),
                    pm10=round(pm10, 1),
                    timestamp=ts,
                )
                db.add(measurement)

            print(f"    → 49 measurements added for {s_data['device_id']}")

    print("\n✅ Seed complete! You can now start the API and bot.")


if __name__ == "__main__":
    asyncio.run(seed())
