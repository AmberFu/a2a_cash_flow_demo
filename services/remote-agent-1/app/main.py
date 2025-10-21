"""天氣規劃 Remote Agent 服務。"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
import uvicorn

from llm import synthesize_weather_summary
from models import WeatherReportRequest, WeatherReportResponse
from weather_generator import generate_city_weather_variables

PORT = int(os.environ.get("PORT", 50001))

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """初始化與釋放 Remote Agent 需要的資源。

    :param app: FastAPI 應用實例，用於在啟動與結束時掛鉤。
    :yield: None，供 FastAPI 管理生命週期。
    """

    logger.info("Weather Remote Agent is starting up on port %s", PORT)
    yield
    logger.info("Weather Remote Agent is shutting down")


app = FastAPI(
    title="Weather Remote Agent",
    version="0.2.0",
    lifespan=lifespan,
)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/")
def healthcheck() -> JSONResponse:
    """回傳服務狀態。

    :return: JSONResponse，包含 agent 名稱、描述與服務連接埠。
    """

    logger.debug("Healthcheck requested")
    return JSONResponse(
        {
            "status": "OK",
            "agent": "Weather Remote Agent",
            "port": PORT,
            "description": "提供隨機天氣摘要與行前提醒。",
        }
    )


@app.post("/weather/report", response_model=WeatherReportResponse)
def weather_report(request: WeatherReportRequest) -> WeatherReportResponse:
    """回傳指定城市在特定時段的隨機天氣摘要。

    :param request: WeatherReportRequest，包含城市、日期與時間區段。
    :return: WeatherReportResponse，內含天氣指標與 LLM 摘要字串。
    """

    logger.info(
        "Generating weather report for city=%s, date=%s, time_range=%s",
        request.city,
        request.date.isoformat(),
        request.time_range,
    )
    variables = generate_city_weather_variables(request.city)
    summary = synthesize_weather_summary(request, variables)
    logger.debug("Weather variables generated: %s", variables.model_dump())
    return WeatherReportResponse(
        city=request.city,
        date=request.date,
        time_range=request.time_range,
        variables=variables,
        summary=summary,
    )


if __name__ == "__main__":
    uvicorn.run(app="main:app", host="0.0.0.0", port=PORT)

