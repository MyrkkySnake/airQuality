"""
SQLAlchemy ORM models for Air Quality Monitoring System.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from db.database import Base


class Sensor(Base):
    """Represents a physical air quality sensor device."""

    __tablename__ = "sensors"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(64), unique=True, nullable=False, index=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to measurements
    measurements = relationship(
        "Measurement", back_populates="sensor", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Sensor(device_id={self.device_id}, lat={self.lat}, lon={self.lon})>"


class Measurement(Base):
    """Stores individual air quality readings from sensors."""

    __tablename__ = "measurements"

    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(Integer, ForeignKey("sensors.id"), nullable=False)
    pm25 = Column(Float, nullable=False)   # PM2.5 μg/m³
    pm10 = Column(Float, nullable=False)   # PM10 μg/m³
    timestamp = Column(DateTime, nullable=False, index=True)
    received_at = Column(DateTime, default=datetime.utcnow)

    # Relationship back to sensor
    sensor = relationship("Sensor", back_populates="measurements")

    # Composite index for fast recent-data queries
    __table_args__ = (
        Index("ix_measurements_sensor_time", "sensor_id", "timestamp"),
    )

    def __repr__(self):
        return (
            f"<Measurement(sensor_id={self.sensor_id}, "
            f"pm25={self.pm25}, pm10={self.pm10}, ts={self.timestamp})>"
        )
