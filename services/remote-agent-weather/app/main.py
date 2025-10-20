"""Weather-focused remote agent service.

This FastAPI application simulates a lightweight weather planning agent that
could be orchestrated by the root agent in the cash flow demo.  It exposes a
health check endpoint for Kubernetes liveness probes and a JSON API for
producing travel-oriented weather advice based on a deterministic knowledge
base.  The knowledge base is seeded from static climate bands to avoid external
API dependencies while still providing realistic responses.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import date
from typing import Dict, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, ValidationInfo
import uvicorn

APP = FastAPI(title="Weather Remote Agent", version="0.1.0")
PORT = int(os.environ.get("PORT", 50010))
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "bedrock")
LLM_MODEL_ID = os.environ.get("LLM_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")

# --- Internal data model ---------------------------------------------------

@dataclass(frozen=True)
class ClimateBand:
    """Represents the climate baseline for a supported location."""

    base_temp_c: float
    base_precip_pct: int
    breezy: bool = False


CLIMATE_BANDS: Dict[str, ClimateBand] = {
    "taipei": ClimateBand(base_temp_c=27.0, base_precip_pct=55, breezy=True),
    "taichung": ClimateBand(base_temp_c=25.0, base_precip_pct=35),
    "kaohsiung": ClimateBand(base_temp_c=28.5, base_precip_pct=45),
    "taoyuan": ClimateBand(base_temp_c=24.5, base_precip_pct=50, breezy=True),
    "hsinchu": ClimateBand(base_temp_c=24.0, base_precip_pct=40, breezy=True),
    "tainan": ClimateBand(base_temp_c=27.5, base_precip_pct=40),
}


class WeatherPreferences(BaseModel):
    """Optional preferences supplied by the downstream workflow."""

    preferred_condition: str | None = Field(
        None,
        description="Optional textual hint for the desired weather condition (e.g. '晴朗').",
    )
    max_precipitation_percent: int | None = Field(
        None,
        ge=0,
        le=100,
        description="Upper bound for acceptable precipitation probability.",
    )
    min_temperature_c: float | None = Field(
        None,
        description="Lower bound for comfortable temperature in Celsius.",
    )
    max_temperature_c: float | None = Field(
        None,
        description="Upper bound for comfortable temperature in Celsius.",
    )

    @field_validator("max_temperature_c")
    @classmethod
    def _validate_temperature_range(cls, value, info: ValidationInfo):
        min_temp = info.data.get("min_temperature_c") if info.data else None
        if value is not None and min_temp is not None and value < min_temp:
            raise ValueError("max_temperature_c must be greater than or equal to min_temperature_c")
        return value


class WeatherAdviceRequest(BaseModel):
    location: str = Field(..., description="City or county name supported by the agent.")
    travel_date: date = Field(..., description="Planned travel date.")
    unit: str = Field(
        "metric",
        pattern="^(metric|imperial)$",
        description="Preferred temperature unit. Supported values: metric (°C) or imperial (°F).",
    )
    preferences: WeatherPreferences | None = Field(
        default=None,
        description="Optional structured preferences from the calling workflow.",
    )


class WeatherAdviceResponse(BaseModel):
    location: str
    travel_date: date
    temperature: float
    unit: str
    condition: str
    precipitation_chance: int
    advisory: str
    provider: str
    model: str


# --- Helpers ----------------------------------------------------------------

def _stable_random(location: str, travel_date: date) -> Tuple[int, int]:
    """Return deterministic pseudo-random deltas for temperature and precipitation."""

    key = f"{location.lower()}::{travel_date.isoformat()}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    temp_delta = int(digest[:2], 16) % 7 - 3  # -3 to +3 °C variation
    precip_delta = int(digest[2:4], 16) % 21 - 10  # -10 to +10 percent
    return temp_delta, precip_delta


def _pick_condition(temp_c: float, precip_pct: int, breezy: bool) -> str:
    """Derive a human-friendly weather condition."""

    if precip_pct >= 70:
        return "雷陣雨"
    if precip_pct >= 50:
        return "短暫陣雨"
    if temp_c >= 32:
        return "酷熱晴朗"
    if temp_c >= 28:
        return "晴時多雲"
    if precip_pct <= 20 and temp_c <= 20:
        return "涼爽晴朗"
    if precip_pct <= 30:
        return "多雲時晴"
    return "局部多雲" if not breezy else "多雲有風"


def _craft_advisory(
    request: WeatherAdviceRequest,
    temp_c: float,
    precip_pct: int,
    condition: str,
    breezy: bool,
) -> str:
    """Generate advisory text based on conditions and optional preferences."""

    statements = [
        f"已根據 {request.location} {request.travel_date.isoformat()} 的預估天氣產生建議。",
        f"模型資訊：{LLM_PROVIDER} / {LLM_MODEL_ID}。",
        f"天氣概況：{condition}，降雨機率約 {precip_pct}% 。",
    ]

    if request.unit == "metric":
        statements.append(f"預估氣溫約 {temp_c:.1f}°C。")
    else:
        temp_f = temp_c * 9 / 5 + 32
        statements.append(f"預估氣溫約 {temp_f:.1f}°F。")

    if breezy:
        statements.append("當地容易有陣風，建議攜帶輕便外套。")

    prefs = request.preferences
    if prefs:
        if prefs.max_precipitation_percent is not None and precip_pct > prefs.max_precipitation_percent:
            statements.append("降雨機率高於偏好門檻，建議準備雨具或調整行程。")
        if prefs.min_temperature_c is not None and temp_c < prefs.min_temperature_c:
            statements.append("氣溫低於舒適範圍，可考慮攜帶保暖衣物。")
        if prefs.max_temperature_c is not None and temp_c > prefs.max_temperature_c:
            statements.append("氣溫高於舒適範圍，建議增加補水與防曬。")
        if prefs.preferred_condition and prefs.preferred_condition not in condition:
            statements.append(f"目前狀態與偏好『{prefs.preferred_condition}』不同，可備用室內行程。")

    statements.append("若需更進階分析可回報 Root Agent 啟動額外推論。")
    return "".join(statements)


def _metric_temperature(temp_c: float, unit: str) -> float:
    return temp_c if unit == "metric" else temp_c * 9 / 5 + 32


# --- Routes -----------------------------------------------------------------

@APP.get("/")
def healthcheck() -> JSONResponse:
    """Return the service status and configured model metadata."""

    return JSONResponse(
        {
            "status": "OK",
            "agent": "Weather Remote Agent",
            "port": PORT,
            "llm_provider": LLM_PROVIDER,
            "llm_model_id": LLM_MODEL_ID,
            "supported_locations": sorted(CLIMATE_BANDS.keys()),
        }
    )


@APP.post("/weather/advice", response_model=WeatherAdviceResponse)
def weather_advice(request: WeatherAdviceRequest) -> WeatherAdviceResponse:
    """Return contextual weather guidance for the requested location."""

    location_key = request.location.strip().lower()
    if location_key not in CLIMATE_BANDS:
        raise HTTPException(status_code=404, detail=f"Location '{request.location}' is not supported.")

    band = CLIMATE_BANDS[location_key]
    temp_delta, precip_delta = _stable_random(location_key, request.travel_date)
    temp_c = band.base_temp_c + temp_delta
    precip_pct = min(max(band.base_precip_pct + precip_delta, 5), 95)
    condition = _pick_condition(temp_c=temp_c, precip_pct=precip_pct, breezy=band.breezy)
    advisory = _craft_advisory(
        request=request,
        temp_c=temp_c,
        precip_pct=precip_pct,
        condition=condition,
        breezy=band.breezy,
    )

    return WeatherAdviceResponse(
        location=request.location,
        travel_date=request.travel_date,
        temperature=round(_metric_temperature(temp_c, request.unit), 1),
        unit="°C" if request.unit == "metric" else "°F",
        condition=condition,
        precipitation_chance=precip_pct,
        advisory=advisory,
        provider=LLM_PROVIDER,
        model=LLM_MODEL_ID,
    )


if __name__ == "__main__":
    uvicorn.run(app="main:APP", host="0.0.0.0", port=PORT, reload=True)
