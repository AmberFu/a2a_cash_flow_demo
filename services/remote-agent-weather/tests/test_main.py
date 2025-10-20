from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from datetime import date

from fastapi.testclient import TestClient

from app.main import APP, CLIMATE_BANDS

client = TestClient(APP)


def test_healthcheck_returns_supported_locations():
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "OK"
    for location in CLIMATE_BANDS.keys():
        assert location in payload["supported_locations"]


def test_weather_advice_metric_units():
    payload = {
        "location": "Taipei",
        "travel_date": date(2024, 7, 1).isoformat(),
        "unit": "metric",
    }
    response = client.post("/weather/advice", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["location"] == payload["location"]
    assert data["unit"] == "°C"
    assert data["temperature"] == round(data["temperature"], 1)
    assert "模型資訊" in data["advisory"]


def test_weather_advice_imperial_units_and_preferences():
    payload = {
        "location": "Taichung",
        "travel_date": date(2024, 7, 2).isoformat(),
        "unit": "imperial",
        "preferences": {
            "preferred_condition": "晴朗",
            "max_precipitation_percent": 30,
            "min_temperature_c": 20,
            "max_temperature_c": 28,
        },
    }
    response = client.post("/weather/advice", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["unit"] == "°F"
    assert "降雨機率" in data["advisory"]
    if data["precipitation_chance"] > 30:
        assert "降雨機率高於偏好門檻" in data["advisory"]


def test_weather_advice_unknown_location():
    payload = {
        "location": "Tokyo",
        "travel_date": date(2024, 7, 3).isoformat(),
    }
    response = client.post("/weather/advice", json=payload)
    assert response.status_code == 404
    assert "not supported" in response.json()["detail"]
