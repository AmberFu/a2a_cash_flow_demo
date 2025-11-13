"""Business logic for combining remote agent outputs into actionable advice."""

from __future__ import annotations

from datetime import date as Date, datetime, time
from typing import Dict, List, Tuple

from .models import (
    RecommendationCriterion,
    RecommendationItem,
    SummaryRequest,
    SummaryResponse,
    TransportPlan,
)


def _combine_date_time(target_date: Date, value: time) -> datetime:
    return datetime.combine(target_date, value)


def _compute_travel_minutes(plan: TransportPlan) -> int:
    departure_dt = _combine_date_time(plan.date, plan.time.departure)
    arrival_dt = _combine_date_time(plan.date, plan.time.arrival)
    return max(int((arrival_dt - departure_dt).total_seconds() // 60), 0)


def _format_duration(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    parts: List[str] = []
    if hours:
        parts.append(f"{hours} 小時")
    if mins or not parts:
        parts.append(f"{mins} 分")
    return "".join(parts)


def _build_plan_title(prefix: str, plan: TransportPlan) -> str:
    return (
        f"{prefix} - {plan.pricing_and_service.service_number} "
        f"({plan.time.departure.strftime('%H:%M')} 出發 / {plan.time.arrival.strftime('%H:%M')} 抵達)"
    )


def _build_plan_detail(plan: TransportPlan, extra: str) -> str:
    duration = _format_duration(_compute_travel_minutes(plan))
    return (
        f"從 {plan.stations.origin} 前往 {plan.stations.destination}，"
        f"行車時間約 {duration}，票價 NT$ {plan.pricing_and_service.price}。{extra}"
    )


def _select_recommended_plans(
    request: SummaryRequest,
) -> Dict[RecommendationCriterion, TransportPlan]:
    plans = request.transport.plans
    target_arrival = _combine_date_time(
        request.transport.date, request.transport.requested_arrival_time
    )

    def shortest_key(plan: TransportPlan) -> int:
        return _compute_travel_minutes(plan)

    def lowest_price_key(plan: TransportPlan) -> int:
        return plan.pricing_and_service.price

    def closest_arrival_key(plan: TransportPlan) -> int:
        arrival_dt = _combine_date_time(plan.date, plan.time.arrival)
        return abs(int((arrival_dt - target_arrival).total_seconds()))

    return {
        RecommendationCriterion.SHORTEST_TRAVEL_TIME: min(plans, key=shortest_key),
        RecommendationCriterion.LOWEST_PRICE: min(plans, key=lowest_price_key),
        RecommendationCriterion.CLOSEST_ARRIVAL: min(plans, key=closest_arrival_key),
    }


def _build_recommendation_items(
    selected: Dict[RecommendationCriterion, TransportPlan]
) -> List[RecommendationItem]:
    items: List[RecommendationItem] = []

    descriptions: Dict[RecommendationCriterion, Tuple[str, str]] = {
        RecommendationCriterion.SHORTEST_TRAVEL_TIME: (
            "旅程最短",
            "適合希望縮短車程的旅客。",
        ),
        RecommendationCriterion.LOWEST_PRICE: (
            "票價最省",
            "幫你節省交通費用。",
        ),
        RecommendationCriterion.CLOSEST_ARRIVAL: (
            "抵達時間最接近需求",
            "讓抵達時間最貼近你的預期。",
        ),
    }

    for criterion, plan in selected.items():
        title_prefix, detail_prefix = descriptions[criterion]
        title = _build_plan_title(title_prefix, plan)
        detail = _build_plan_detail(plan, detail_prefix)
        items.append(
            RecommendationItem(criterion=criterion, title=title, detail=detail, plan=plan)
        )

    return items


def _generate_weather_reminders(request: SummaryRequest) -> List[str]:
    variables = request.weather_report.variables
    reminders: List[str] = []

    if variables.precipitation_chance_percent >= 50 or variables.precipitation_mm > 0:
        reminders.append("降雨機率偏高，請記得攜帶雨具以免淋雨。")

    if variables.temperature_c >= 30:
        reminders.append("氣溫較高，務必多補充水分並留意中暑風險。")

    if variables.precipitation_chance_percent <= 30 and variables.temperature_c >= 26:
        reminders.append("天氣炎熱且陽光充足，建議做好防曬措施。")

    if variables.special_weather:
        reminders.append(f"特別注意：{variables.special_weather}。")

    if not reminders:
        reminders.append("天氣狀況穩定，仍請留意即時預報調整行程。")

    return reminders


def craft_summary_response(
    request: SummaryRequest, provider: str, model_id: str
) -> SummaryResponse:
    # Gracefully handle missing data
    if request.transport:
        selected_plans = _select_recommended_plans(request)
        recommendation_items = _build_recommendation_items(selected_plans)
    else:
        recommendation_items = []

    if request.weather_report:
        reminders = _generate_weather_reminders(request)
        weather_summary = request.weather_report.summary
    else:
        reminders = ["天氣資訊缺失，請查詢即時天氣預報。"]
        weather_summary = "天氣資訊缺失。"


    overview = (
        f"{request.user_requirement.origin} → {request.user_requirement.destination}"
        f" 旅程，建議於 {request.user_requirement.travel_date.isoformat()} 出發。"
    )
    if request.user_requirement.desired_arrival_time:
        overview += (
            f" 目標抵達時間為 {request.user_requirement.desired_arrival_time.strftime('%H:%M')}，"
            "已依此挑選最佳車次。"
        )

    if request.user_requirement.transport_note:
        overview += f" 交通備註：{request.user_requirement.transport_note}。"

    return SummaryResponse(
        task_id=request.task_id,
        provider=provider,
        model=model_id,
        overview=overview,
        recommended_plans=recommendation_items,
        weather_summary=weather_summary,
        weather_reminders=reminders,
    )

