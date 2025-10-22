"""Transport plan generation logic."""

from __future__ import annotations

import random
from datetime import datetime, time, timedelta
from typing import Iterable, List

from fastapi import HTTPException

from .models import (
    PricingAndServiceInfo,
    StationInfo,
    TimeInfo,
    TransportPlan,
    TransportPlanRequest,
)


ORIGIN_STATIONS = ["台北", "板橋", "桃園", "新竹", "台中", "嘉義", "台南", "左營"]
SERVICE_PREFIXES = ["T", "F", "E", "R"]
EARLIEST_DEPARTURE = time(5, 0)
MIN_BUFFER_MINUTES = 10
MAX_ARRIVAL_BUFFER_MINUTES = 90
MIN_TRAVEL_MINUTES = 25
MAX_TRAVEL_MINUTES = 210
PRICE_RANGE = (240, 1280)


def _random_origin_station(destination: str) -> str:
    candidates = [station for station in ORIGIN_STATIONS if station != destination]
    return random.choice(candidates) if candidates else destination


def _random_service_number() -> str:
    prefix = random.choice(SERVICE_PREFIXES)
    return f"{prefix}{random.randint(100, 999)}"


def _random_price() -> int:
    return random.randrange(PRICE_RANGE[0], PRICE_RANGE[1] + 1, 5)


def _generate_plan(request: TransportPlanRequest) -> TransportPlan:
    target_arrival_dt = datetime.combine(request.date, request.arrival_time)
    earliest_departure_dt = datetime.combine(request.date, EARLIEST_DEPARTURE)

    available_arrival_buffer = int(
        (target_arrival_dt - earliest_departure_dt).total_seconds() // 60
    ) - MIN_TRAVEL_MINUTES
    if available_arrival_buffer <= MIN_BUFFER_MINUTES:
        raise HTTPException(
            status_code=400,
            detail="抵達時間過早，無法在同日內生成更早抵達的班次。",
        )

    arrival_buffer_minutes = random.randint(
        MIN_BUFFER_MINUTES, min(MAX_ARRIVAL_BUFFER_MINUTES, available_arrival_buffer)
    )
    arrival_dt = target_arrival_dt - timedelta(minutes=arrival_buffer_minutes)

    max_travel_window = int((arrival_dt - earliest_departure_dt).total_seconds() // 60)
    travel_minutes = random.randint(
        MIN_TRAVEL_MINUTES, min(MAX_TRAVEL_MINUTES, max_travel_window)
    )
    departure_dt = arrival_dt - timedelta(minutes=travel_minutes)

    if departure_dt < earliest_departure_dt:
        departure_dt = earliest_departure_dt

    origin_station = _random_origin_station(request.destination)

    return TransportPlan(
        stations=StationInfo(origin=origin_station, destination=request.destination),
        time=TimeInfo(departure=departure_dt.time(), arrival=arrival_dt.time()),
        date=departure_dt.date(),
        pricing_and_service=PricingAndServiceInfo(
            price=_random_price(), service_number=_random_service_number()
        ),
    )


def generate_transport_plans(request: TransportPlanRequest) -> List[TransportPlan]:
    """Generate a list of transport plans sorted by arrival time."""

    plans = [_generate_plan(request) for _ in range(request.results)]
    plans.sort(key=lambda plan: plan.time.arrival)
    return plans


def preview_plans(request: TransportPlanRequest) -> Iterable[TransportPlan]:
    """Yield plans without materializing the list (useful for streaming)."""

    for _ in range(request.results):
        yield _generate_plan(request)
