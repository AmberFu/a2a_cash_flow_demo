"""模擬 LLM 根據天氣資料產出摘要的輔助函式。"""
from __future__ import annotations

from .models import CityWeatherVariables, WeatherReportRequest


def synthesize_weather_summary(
    request: WeatherReportRequest, variables: CityWeatherVariables
) -> str:
    """模擬 LLM 將天氣變數整理為繁體中文摘要。

    :param request: WeatherReportRequest，包含城市、日期與時間區段。
    :param variables: CityWeatherVariables，來自天氣變數產生器的原始指標。
    :return: 字串，格式包含基本資訊與整體天氣敘述。
    """

    base_segments = [
        f"氣溫 {variables.temperature_c:.1f} 度，",
        f"降雨機率 {variables.precipitation_chance_percent}%，",
        f"相對濕度 {variables.humidity_percent}%，",
        f"風速 {variables.wind_speed_kmh:.1f} 公里/小時，",
        f"預估降雨量 {variables.precipitation_mm:.1f} 毫米，",
        f"空氣品質 {variables.air_quality}。",
    ]

    if variables.special_weather:
        base_segments.append(f"留意特殊現象：{variables.special_weather}。")
    base = "".join(base_segments)

    overall_condition = "晴時多雲"
    if variables.precipitation_chance_percent >= 70:
        overall_condition = "陰雨天"
    elif variables.precipitation_chance_percent >= 40:
        overall_condition = "短暫陣雨"
    elif variables.temperature_c >= 32:
        overall_condition = "炎熱晴朗"
    elif variables.temperature_c <= 20:
        overall_condition = "涼爽舒適"

    summary = (
        f"{base}整體而言，在 {request.city} {request.date.isoformat()} {request.time_range} "
        f"整體天氣狀況是{overall_condition}。"
    )
    return summary

