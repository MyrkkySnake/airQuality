# 🌬️ Air Quality Monitoring System — Нукус

Production-ready система мониторинга качества воздуха с Telegram-ботом,
REST API для IoT датчиков, интерактивной картой и AI-рекомендациями.

---

## 📐 Архитектура

```
┌─────────────────────┐     POST /sensor-data      ┌──────────────────────┐
│  IoT Sensors         │ ─────────────────────────► │  FastAPI Backend      │
│  ESP32 + LoRa        │                            │  api/main.py          │
└─────────────────────┘                            └──────────┬───────────┘
                                                              │ SQLAlchemy
                                                              ▼
                                                    ┌──────────────────────┐
                                                    │  SQLite / PostgreSQL  │
                                                    │  sensors + measurements│
                                                    └──────────┬───────────┘
                                                              │
                              ┌───────────────────────────────┤
                              │                               │
                    ┌─────────▼──────────┐        ┌──────────▼──────────┐
                    │  Telegram Bot       │        │  Services Layer      │
                    │  bot/telegram_bot.py│        │  air_quality.py      │
                    │                    │        │  ai_advisor.py        │
                    │  /start /map /trend│        │  map_generator.py     │
                    │  📍 Геолокация     │        │  trend_analyzer.py    │
                    └────────────────────┘        └─────────────────────┘
```

---

## 🗂 Структура проекта

```
airquality/
├── api/
│   └── main.py              FastAPI: приём и отдача данных
├── bot/
│   └── telegram_bot.py      Telegram-бот (async)
├── db/
│   ├── database.py          Движок SQLAlchemy, сессии
│   └── models.py            ORM: Sensor, Measurement
├── services/
│   ├── air_quality.py       Классификация AQI, запросы к БД
│   ├── ai_advisor.py        Советы через OpenAI GPT
│   ├── map_generator.py     Folium карта + IDW интерполяция
│   └── trend_analyzer.py    Анализ тренда PM2.5
├── utils/
│   └── geo.py               Haversine, IDW, nearest-sensor
├── config.py                Pydantic settings (.env)
├── seed_demo_data.py        Скрипт: тестовые данные
├── requirements.txt
└── .env.example
```

---

## ⚡ Быстрый старт

### 1. Клонировать / распаковать проект

```bash
cd airquality
```

### 2. Создать виртуальное окружение

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows
```

### 3. Установить зависимости

```bash
pip install -r requirements.txt
```

### 4. Настроить переменные окружения

```bash
cp .env.example .env
# Откройте .env и заполните:
#   TELEGRAM_BOT_TOKEN=...
#   OPENAI_API_KEY=...
```

### 5. Загрузить тестовые данные (опционально)

```bash
python seed_demo_data.py
```

Создаёт 10 датчиков вокруг Нукуса с 48 часами показаний.

### 6. Запустить API

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Документация API: http://localhost:8000/docs

### 7. Запустить Telegram-бота (в отдельном терминале)

```bash
python -m bot.telegram_bot
```

---

## 🧪 Тестирование API

### Health check

```bash
curl http://localhost:8000/health
```

### Отправить показание датчика

```bash
curl -X POST http://localhost:8000/sensor-data \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "sensor_001",
    "lat": 42.4597,
    "lon": 59.6093,
    "pm25": 75.5,
    "pm10": 110.2,
    "timestamp": "2026-05-01T10:00:00"
  }'
```

Ожидаемый ответ:
```json
{"status": "ok", "device_id": "sensor_001", "measurement_id": 1}
```

### Список всех датчиков

```bash
curl http://localhost:8000/sensors
```

### Данные конкретного датчика

```bash
curl http://localhost:8000/sensors/sensor_001
```

### Тренд по городу

```bash
curl http://localhost:8000/trend
```

### Batch-нагрузочный тест (10 датчиков)

```bash
for i in $(seq 1 10); do
  curl -s -X POST http://localhost:8000/sensor-data \
    -H "Content-Type: application/json" \
    -d "{
      \"device_id\": \"sensor_$(printf '%03d' $i)\",
      \"lat\": $(python3 -c \"import random; print(round(42.45 + random.uniform(-0.05,0.05), 4))\"),
      \"lon\": $(python3 -c \"import random; print(round(59.61 + random.uniform(-0.05,0.05), 4))\"),
      \"pm25\": $(python3 -c \"import random; print(round(random.uniform(10,200), 1))\"),
      \"pm10\": $(python3 -c \"import random; print(round(random.uniform(15,280), 1))\"),
      \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%S)\"
    }" &
done
wait
echo "Done"
```

---

## 🤖 Команды Telegram-бота

| Команда / Действие | Описание |
|---|---|
| `/start` | Приветствие и описание |
| `/map` | HTML-карта города со всеми датчиками |
| `/trend` | Тренд PM2.5 за последние N часов |
| 📍 Геолокация | Ближайший датчик + AI-совет |
| 🗺 Карта (кнопка) | То же, что `/map` |
| 📈 Тренд (кнопка) | То же, что `/trend` |

---

## 🗺 Описание карты

- **Базовый слой:** CartoDB Positron (чистый, минималистичный)
- **Тепловая карта:** IDW-интерполяция PM2.5 по всем датчикам
- **Маркеры датчиков:** цветные кружки с pop-up (PM2.5, PM10, время)
- **Легенда:** цветовая шкала в углу карты
- **Переключение слоёв:** Layer Control (датчики / тепловая карта)

---

## 📡 Интеграция с реальными IoT устройствами

### ESP32 + SDS011 пример (Arduino/MicroPython):

```python
import urequests, ujson, time

API_URL = "http://your-server:8000/sensor-data"
DEVICE_ID = "esp32_001"

def send_reading(pm25, pm10):
    payload = {
        "device_id": DEVICE_ID,
        "lat": 42.4597,
        "lon": 59.6093,
        "pm25": pm25,
        "pm10": pm10,
        "timestamp": "2026-05-01T10:00:00"   # use RTC
    }
    r = urequests.post(API_URL,
                       headers={"Content-Type": "application/json"},
                       data=ujson.dumps(payload))
    r.close()
```

### LoRaWAN через TTN / ChirpStack

Payload decoder → HTTP Integration → POST /sensor-data

---

## 🚀 Production деплой

### PostgreSQL

```env
DATABASE_URL=postgresql+asyncpg://airuser:secret@db:5432/airquality
```

### Docker Compose (минимальный)

```yaml
services:
  api:
    build: .
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000
    env_file: .env
    ports: ["8000:8000"]
  bot:
    build: .
    command: python -m bot.telegram_bot
    env_file: .env
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: airquality
      POSTGRES_USER: airuser
      POSTGRES_PASSWORD: secret
```

---

## 🛡 Безопасность (production)

- Добавить Bearer-токен аутентификацию к `/sensor-data`
- Ограничить CORS до доменов вашего фронтенда
- Использовать HTTPS (nginx reverse proxy + Let's Encrypt)
- Поставить rate-limiting (slowapi или nginx)

---

## 📈 Планы расширения

- [ ] Реальные ESP32 + SDS011 датчики с LoRa
- [ ] PM1.0, температура, влажность
- [ ] Push-уведомления при превышении порогов
- [ ] Исторические графики (Chart.js в WebApp)
- [ ] Экспорт CSV / JSON по API
- [ ] Grafana + Prometheus мониторинг
