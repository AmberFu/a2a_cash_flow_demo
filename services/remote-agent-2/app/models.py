"""Pydantic models for transport plan generation."""

from __future__ import annotations

from datetime import date as Date, time
from typing import List

from pydantic import BaseModel, Field, PositiveInt, field_validator


class StationInfo(BaseModel):
    """紀錄起訖站資訊。"""

    origin: str = Field(..., description="出發車站名稱")
    destination: str = Field(..., description="抵達車站名稱")


class TimeInfo(BaseModel):
    """紀錄出發與抵達時間。"""

    departure: time = Field(..., description="出發時間 (24 小時制)")
    arrival: time = Field(..., description="抵達時間 (24 小時制)")


class PricingAndServiceInfo(BaseModel):
    """紀錄票價與班次資訊。"""

    price: int = Field(..., description="票價 (新台幣)")
    service_number: str = Field(..., description="班次代號")


class TransportPlan(BaseModel):
    """交通資訊回傳格式，僅包含指定的四個欄位。"""

    stations: StationInfo = Field(..., description="起訖站資訊")
    time: TimeInfo = Field(..., description="出發與抵達時間")
    date: Date = Field(..., description="出發日期")
    pricing_and_service: PricingAndServiceInfo = Field(
        ..., description="票價與班次資訊"
    )


class TransportPlanRequest(BaseModel):
    """產生交通資訊所需的輸入。"""

    destination: str = Field(..., description="目的地車站")
    arrival_time: time = Field(..., description="希望抵達時間 (24 小時制)")
    date: Date = Field(..., description="出發日期")
    results: PositiveInt = Field(5, description="需要的方案數量 (預設為 5)", le=10)

    @field_validator("destination")
    @classmethod
    def destination_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("destination 不能為空白。")
        return value.strip()


class TransportPlanResponse(BaseModel):
    """交通資訊回傳物件。"""

    destination: str
    requested_arrival_time: time
    date: Date
    plans: List[TransportPlan]
