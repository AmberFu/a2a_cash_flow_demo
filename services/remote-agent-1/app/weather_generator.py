"""城市天氣變數產生器的實作。"""
from __future__ import annotations

import random
from typing import Iterable

from .models import CityWeatherVariables


_AIR_QUALITY_OPTIONS: Iterable[str] = (
    "良好",
    "普通",
    "對敏感族群不健康",
)

_SPECIAL_WEATHER_OPTIONS: Iterable[str] = (
    "午後雷陣雨",
    "局部短暫陣雨",
    "焚風",
    "海風增強",
)


def generate_city_weather_variables(city: str) -> CityWeatherVariables:
    """隨機生成指定城市的天氣指標。

    :param city: 城市名稱字串 (str)，目前僅用於產生亂數時保留語意。
    :return: CityWeatherVariables，包含溫度、濕度、風速等指標。
    """

    rng = random.Random()
    temperature_c = round(rng.uniform(18.0, 35.0), 1)
    humidity_percent = rng.randint(40, 95)
    wind_speed_kmh = round(rng.uniform(5.0, 35.0), 1)
    precipitation_chance_percent = rng.randint(10, 90)
    precipitation_mm = round(rng.uniform(0.0, 25.0), 1)
    air_quality = rng.choice(tuple(_AIR_QUALITY_OPTIONS))
    special_weather = (
        rng.choice(tuple(_SPECIAL_WEATHER_OPTIONS)) if rng.random() < 0.35 else None
    )

    return CityWeatherVariables(
        temperature_c=temperature_c,
        humidity_percent=humidity_percent,
        wind_speed_kmh=wind_speed_kmh,
        precipitation_chance_percent=precipitation_chance_percent,
        precipitation_mm=precipitation_mm,
        air_quality=air_quality,
        special_weather=special_weather,
    )

