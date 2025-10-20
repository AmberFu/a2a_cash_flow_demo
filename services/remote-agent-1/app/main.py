"""天氣規劃 Remote Agent 服務。

此 FastAPI 應用模擬一個由 Root Agent 調用的天氣諮詢 Agent，
透過靜態氣候帶資料與決定性亂數來產生旅遊建議，避免外部 API 依賴。
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import date
from typing import Dict, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationInfo, field_validator
import uvicorn

app = FastAPI(title="Weather Remote Agent", version="0.1.0")
PORT = int(os.environ.get("PORT", 50001))
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "bedrock")
LLM_MODEL_ID = os.environ.get("LLM_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")


# --- Internal data model ----------------------------------------------------


@dataclass(frozen=True)
class ClimateBand:
    """代表單一城市的氣候帶基準資料。"""

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
    """呼叫者可提供的偏好設定。"""

    preferred_condition: str | None = Field(
        None,
        description="希望的天氣描述，例如『晴朗』。",
    )
    max_precipitation_percent: int | None = Field(
        None,
        ge=0,
        le=100,
        description="可接受的最高降雨機率 (0-100)。",
    )
    min_temperature_c: float | None = Field(
        None,
        description="可接受的最低攝氏溫度。",
    )
    max_temperature_c: float | None = Field(
        None,
        description="可接受的最高攝氏溫度。",
    )

    @field_validator("max_temperature_c")
    @classmethod
    def _validate_temperature_range(cls, value: float | None, info: ValidationInfo) -> float | None:
        """檢查溫度上下限是否一致。

        :param value: `max_temperature_c` 的輸入值 (float 或 None)。
        :param info: Pydantic 的驗證資訊，提供其他欄位的值。
        :return: 驗證後的 `max_temperature_c`，型別為 float 或 None。
        :raises ValueError: 當最大溫度小於最小溫度時拋出。
        """

        min_temp = info.data.get("min_temperature_c") if info.data else None
        if value is not None and min_temp is not None and value < min_temp:
            raise ValueError("max_temperature_c 必須大於或等於 min_temperature_c")
        return value


class WeatherAdviceRequest(BaseModel):
    """天氣建議 API 的請求模型。"""

    location: str = Field(..., description="城市名稱，需為支援清單內的英文字串。")
    travel_date: date = Field(..., description="計畫旅遊日期。")
    unit: str = Field(
        "metric",
        pattern="^(metric|imperial)$",
        description="溫度單位：metric 代表攝氏、imperial 代表華氏。",
    )
    preferences: WeatherPreferences | None = Field(
        default=None,
        description="可選的偏好設定，用於客製化建議。",
    )


class WeatherAdviceResponse(BaseModel):
    """天氣建議 API 的回應模型。"""

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
    """依據地點與日期產生決定性亂數。

    :param location: 城市名稱字串 (str)。
    :param travel_date: 旅遊日期 (datetime.date)。
    :return: 兩個整數 (Tuple[int, int])，分別代表溫度與降雨機率的偏移量。
    """

    key = f"{location.lower()}::{travel_date.isoformat()}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    temp_delta = int(digest[:2], 16) % 7 - 3  # -3 到 +3 °C
    precip_delta = int(digest[2:4], 16) % 21 - 10  # -10 到 +10 %
    return temp_delta, precip_delta


def _pick_condition(temp_c: float, precip_pct: int, breezy: bool) -> str:
    """根據溫度、降雨機率與是否多風判斷天氣描述。

    :param temp_c: 計算後的攝氏溫度 (float)。
    :param precip_pct: 降雨機率百分比 (int)。
    :param breezy: 是否易有陣風 (bool)。
    :return: 天氣敘述字串 (str)。
    """

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
    return "多雲有風" if breezy else "局部多雲"


def _craft_advisory(
    request: WeatherAdviceRequest,
    temp_c: float,
    precip_pct: int,
    condition: str,
    breezy: bool,
) -> str:
    """組合完整的旅遊建議文字。

    :param request: 原始請求模型 (WeatherAdviceRequest)。
    :param temp_c: 預估攝氏溫度 (float)。
    :param precip_pct: 預估降雨機率 (int)。
    :param condition: 天氣描述字串 (str)。
    :param breezy: 是否多風 (bool)。
    :return: 中文建議內容 (str)。
    """

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
            statements.append("降雨機率高於偏好門檻，請準備雨具或考慮調整行程。")
        if prefs.min_temperature_c is not None and temp_c < prefs.min_temperature_c:
            statements.append("氣溫低於舒適範圍，可攜帶保暖衣物。")
        if prefs.max_temperature_c is not None and temp_c > prefs.max_temperature_c:
            statements.append("氣溫高於舒適範圍，建議加強補水與防曬。")
        if prefs.preferred_condition and prefs.preferred_condition not in condition:
            statements.append(f"目前狀態與偏好『{prefs.preferred_condition}』不同，可準備室內備案。")

    statements.append("若需更進階分析可回報 Root Agent 啟動後續推論。")
    return "".join(statements)


def _metric_temperature(temp_c: float, unit: str) -> float:
    """依指定單位回傳溫度數值。

    :param temp_c: 攝氏溫度 (float)。
    :param unit: 溫度單位字串，僅接受 'metric' 或 'imperial'。
    :return: 若為攝氏則直接回傳 float，若為華氏則轉換後回傳 float。
    """

    return temp_c if unit == "metric" else temp_c * 9 / 5 + 32


# --- Routes -----------------------------------------------------------------


@app.get("/")
def healthcheck() -> JSONResponse:
    """提供服務狀態與模型資訊。

    :return: FastAPI JSONResponse，內容包含狀態、模型與支援的城市清單。
    """

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


@app.post("/weather/advice", response_model=WeatherAdviceResponse)
def weather_advice(request: WeatherAdviceRequest) -> WeatherAdviceResponse:
    """回傳指定地點的天氣建議。

    :param request: WeatherAdviceRequest，含地點、日期、單位與偏好。
    :return: WeatherAdviceResponse，提供溫度、降雨機率與建議文字。
    :raises HTTPException: 當地點不在支援清單時回傳 404。
    """

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
    uvicorn.run(app="main:app", host="0.0.0.0", port=PORT, reload=True)
