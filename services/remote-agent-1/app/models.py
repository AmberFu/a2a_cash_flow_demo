"""Remote Agent 1 專用的資料模型模組。"""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class CityWeatherVariables(BaseModel):
    """"城市天氣變數產生器"所輸出的天氣指標。"""

    temperature_c: float = Field(
        ..., description="攝氏氣溫數值，單位為 °C。"
    )
    humidity_percent: int = Field(
        ..., ge=0, le=100, description="相對濕度百分比 (0-100)。"
    )
    wind_speed_kmh: float = Field(
        ..., ge=0, description="平均風速，單位為公里/小時。"
    )
    precipitation_chance_percent: int = Field(
        ..., ge=0, le=100, description="降雨機率百分比 (0-100)。"
    )
    precipitation_mm: float = Field(
        ..., ge=0, description="預估降雨量，單位為毫米。"
    )
    air_quality: str = Field(
        ..., description="空氣品質文字描述，例如『良好』或『普通』。"
    )
    special_weather: Optional[str] = Field(
        None, description="可選的特殊天氣狀況描述，例如『午後雷陣雨』。"
    )


class WeatherReportRequest(BaseModel):
    """Weather Remote Agent 接受的請求格式。"""

    city: str = Field(..., description="城市名稱，建議使用英文或中文名稱。")
    date: date = Field(..., description="查詢的日期，格式為 YYYY-MM-DD。")
    time_range: str = Field(
        ..., description="時間區段，例如『上午』、『下午』或『夜間』。"
    )


class WeatherReportResponse(BaseModel):
    """Weather Remote Agent 回傳的天氣摘要。"""

    city: str = Field(description="城市名稱，與請求中的值相同。")
    date: date = Field(description="查詢日期，與請求中的值相同。")
    time_range: str = Field(description="時間區段，與請求中的值相同。")
    variables: CityWeatherVariables = Field(
        description="城市天氣變數產生器生成的原始天氣指標。"
    )
    summary: str = Field(
        description="模擬 LLM 根據天氣指標輸出的繁體中文摘要句。"
    )

