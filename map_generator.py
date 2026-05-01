"""
Map generator: builds an interactive Folium map showing all sensors,
their PM2.5 readings, and a smooth IDW-interpolated heatmap layer.
"""

import logging
import os
import tempfile
from typing import Optional

import folium
from folium.plugins import HeatMap

from config import settings
from services.air_quality import classify_pm25
from utils.geo import idw_interpolate

logger = logging.getLogger(__name__)

# Grid resolution for IDW interpolation (lower = more detail, more CPU)
IDW_GRID_STEPS = 30


def _pm25_to_heat_weight(pm25: float) -> float:
    """Normalise PM2.5 to a 0–1 weight for the HeatMap plugin."""
    return min(pm25 / 200.0, 1.0)


def _build_idw_grid(sensor_data: list[dict]) -> list[list[float]]:
    """
    Build a lat/lon grid with IDW-interpolated PM2.5 values.
    Returns a list of [lat, lon, weight] for Folium HeatMap.
    """
    if not sensor_data:
        return []

    lats = [s["lat"] for s in sensor_data]
    lons = [s["lon"] for s in sensor_data]

    lat_min, lat_max = min(lats) - 0.02, max(lats) + 0.02
    lon_min, lon_max = min(lons) - 0.02, max(lons) + 0.02

    lat_step = (lat_max - lat_min) / IDW_GRID_STEPS
    lon_step = (lon_max - lon_min) / IDW_GRID_STEPS

    points = [{"lat": s["lat"], "lon": s["lon"], "value": s["pm25"]} for s in sensor_data]
    heat_data = []

    for i in range(IDW_GRID_STEPS + 1):
        for j in range(IDW_GRID_STEPS + 1):
            glat = lat_min + i * lat_step
            glon = lon_min + j * lon_step
            interpolated = idw_interpolate(glat, glon, points, max_distance_km=8.0)
            if interpolated is not None:
                heat_data.append([glat, glon, _pm25_to_heat_weight(interpolated)])

    return heat_data


def generate_city_map(sensor_data: list[dict], output_path: Optional[str] = None) -> str:
    """
    Generate an interactive Folium HTML map.

    Args:
        sensor_data: list of dicts with lat, lon, pm25, pm10, device_id, timestamp
        output_path: where to save the HTML file (defaults to a temp file)

    Returns:
        Absolute path to the saved HTML file.
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".html", prefix="airmap_")
        os.close(fd)

    # ── Base map ──────────────────────────────────────────────────────────
    m = folium.Map(
        location=[settings.MAP_CENTER_LAT, settings.MAP_CENTER_LON],
        zoom_start=settings.MAP_ZOOM,
        tiles="CartoDB Positron",
        control_scale=True,
    )

    # ── Title overlay ─────────────────────────────────────────────────────
    title_html = """
    <div style="position:fixed;top:10px;left:50%;transform:translateX(-50%);
                background:white;padding:8px 16px;border-radius:8px;
                box-shadow:0 2px 6px rgba(0,0,0,.3);font-family:sans-serif;
                font-size:15px;font-weight:600;z-index:9999;">
        🌬️ Мониторинг качества воздуха — Нукус
    </div>
    """
    m.get_root().html.add_child(folium.Element(title_html))

    # ── Legend ────────────────────────────────────────────────────────────
    legend_html = """
    <div style="position:fixed;bottom:30px;right:10px;background:white;
                padding:10px 14px;border-radius:8px;font-family:sans-serif;
                font-size:13px;box-shadow:0 2px 6px rgba(0,0,0,.3);z-index:9999;">
        <b>PM2.5 (μg/m³)</b><br>
        🟢 0–50 — Хорошо<br>
        🟡 51–100 — Умеренно<br>
        🔴 101–200 — Плохо<br>
        🚨 200+ — Опасно
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # ── IDW Heatmap layer (smooth gradient) ───────────────────────────────
    active = [s for s in sensor_data if s.get("pm25") is not None]

    if active:
        heat_data = _build_idw_grid(active)
        if heat_data:
            HeatMap(
                heat_data,
                name="Уровень PM2.5 (интерполяция)",
                min_opacity=0.2,
                max_zoom=18,
                radius=35,
                blur=25,
                gradient={
                    "0.0": "blue",
                    "0.25": "green",
                    "0.5": "yellow",
                    "0.75": "orange",
                    "1.0": "red",
                },
            ).add_to(m)

    # ── Sensor markers ────────────────────────────────────────────────────
    sensor_group = folium.FeatureGroup(name="Датчики", show=True)

    for s in sensor_data:
        if s.get("pm25") is None:
            color = "gray"
            popup_text = f"<b>{s['device_id']}</b><br>Нет данных"
        else:
            level = classify_pm25(s["pm25"])
            color = level.color
            ts_str = s["timestamp"].strftime("%d.%m %H:%M") if s.get("timestamp") else "—"
            popup_text = (
                f"<b>{s['device_id']}</b><br>"
                f"PM2.5: <b>{s['pm25']:.1f}</b> μg/m³<br>"
                f"PM10: <b>{s['pm10']:.1f}</b> μg/m³<br>"
                f"Статус: {level.emoji} {level.label}<br>"
                f"Обновлено: {ts_str}"
            )

        folium.CircleMarker(
            location=[s["lat"], s["lon"]],
            radius=10,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            popup=folium.Popup(popup_text, max_width=220),
            tooltip=s["device_id"],
        ).add_to(sensor_group)

    sensor_group.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    # ── Save ──────────────────────────────────────────────────────────────
    m.save(output_path)
    logger.info("Map saved to %s (%d sensors)", output_path, len(sensor_data))
    return output_path
