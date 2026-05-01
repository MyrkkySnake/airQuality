"""
FastAPI backend: receives sensor data, validates, stores in DB.
Endpoints:
  POST /sensor-data     — ingest a reading
  GET  /sensors         — list all sensors
  GET  /sensors/{id}    — latest reading for one sensor
  GET  /health          — health check
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.database import init_db, get_db
from db.models import Sensor, Measurement
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class SensorDataIn(BaseModel):
    """Payload sent by a physical sensor device."""

    device_id: str = Field(..., min_length=1, max_length=64, description="Unique sensor ID")
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    pm25: float = Field(..., ge=0, le=2000, description="PM2.5 μg/m³")
    pm10: float = Field(..., ge=0, le=2000, description="PM10 μg/m³")
    timestamp: datetime

    @field_validator("pm25", "pm10")
    @classmethod
    def sanity_check(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Particulate matter cannot be negative")
        return round(v, 2)


class SensorDataOut(BaseModel):
    """Response after successful ingestion."""
    status: str
    device_id: str
    measurement_id: int


class SensorInfo(BaseModel):
    device_id: str
    lat: float
    lon: float
    pm25: Optional[float]
    pm10: Optional[float]
    timestamp: Optional[datetime]

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up — initialising database …")
    await init_db()
    logger.info("Database ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Air Quality Monitoring API",
    description="Receives and serves air quality data from IoT sensor network in Nukus, Uzbekistan.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "service": "air-quality-api"}


@app.post(
    "/sensor-data",
    response_model=SensorDataOut,
    status_code=status.HTTP_201_CREATED,
    tags=["ingestion"],
    summary="Ingest a sensor reading",
)
async def ingest_sensor_data(payload: SensorDataIn, db: AsyncSession = Depends(get_db)):
    """
    Accept a reading from a sensor device.
    • Creates or updates the sensor record.
    • Saves the measurement.
    """
    # ── Upsert sensor ──────────────────────────────────────────────────────
    result = await db.execute(
        select(Sensor).where(Sensor.device_id == payload.device_id)
    )
    sensor = result.scalars().first()

    if sensor is None:
        sensor = Sensor(
            device_id=payload.device_id,
            lat=payload.lat,
            lon=payload.lon,
        )
        db.add(sensor)
        await db.flush()   # get sensor.id before creating measurement
        logger.info("New sensor registered: %s", payload.device_id)
    else:
        # Update location in case sensor was moved
        sensor.lat = payload.lat
        sensor.lon = payload.lon

    # ── Save measurement ───────────────────────────────────────────────────
    measurement = Measurement(
        sensor_id=sensor.id,
        pm25=payload.pm25,
        pm10=payload.pm10,
        timestamp=payload.timestamp,
    )
    db.add(measurement)
    await db.flush()

    logger.info(
        "Measurement saved | device=%s pm25=%.1f pm10=%.1f ts=%s",
        payload.device_id,
        payload.pm25,
        payload.pm10,
        payload.timestamp.isoformat(),
    )

    return SensorDataOut(
        status="ok",
        device_id=payload.device_id,
        measurement_id=measurement.id,
    )


@app.get("/sensors", response_model=list[SensorInfo], tags=["query"])
async def list_sensors(db: AsyncSession = Depends(get_db)):
    """Return all sensors with their most recent readings."""
    from services.air_quality import get_all_sensors_with_latest
    data = await get_all_sensors_with_latest(db)
    return data


@app.get("/sensors/{device_id}", response_model=SensorInfo, tags=["query"])
async def get_sensor(device_id: str, db: AsyncSession = Depends(get_db)):
    """Return the latest reading for a specific sensor."""
    from services.air_quality import get_sensor_latest
    data = await get_sensor_latest(db, device_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Sensor '{device_id}' not found.")
    return data


@app.get("/trend", tags=["analytics"])
async def city_trend(db: AsyncSession = Depends(get_db)):
    """Return the city-wide PM2.5 trend."""
    from services.trend_analyzer import get_city_trend
    return await get_city_trend(db)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
        log_level="info",
    )
