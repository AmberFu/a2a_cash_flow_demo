"""Summary Agent stub service for aggregating downstream results.

This service is intentionally lightweight so the demo can run without
provisioning an additional LLM endpoint.  It exposes a JSON API that can be
invoked either directly (ClusterIP service, port-forward) or indirectly via
SQS/EventBridge callbacks handled by the root agent.
"""
from __future__ import annotations

import os
from typing import List, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn

APP = FastAPI(title="Summary Agent", version="0.1.0")
PORT = int(os.environ.get("PORT", 50003))
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "bedrock")
LLM_MODEL_ID = os.environ.get("LLM_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")


class SummaryRequest(BaseModel):
    task_id: str = Field(..., description="Workflow task identifier from the root agent")
    budget: Optional[str] = Field(None, description="Optional budget string provided by the user")
    weather_advice: Optional[str] = Field(None, description="Weather agent synthesized output")
    train_options: Optional[List[str]] = Field(
        None, description="Shortlist of train recommendations provided by the transport agent"
    )


class SummaryResponse(BaseModel):
    task_id: str
    provider: str
    model: str
    recommendation: str


def craft_summary(payload: SummaryRequest) -> SummaryResponse:
    """Mock a natural language suggestion using environment-provided metadata."""
    parts: List[str] = [
        "感謝使用 A2A Cash Flow Demo 摘要服務!",
        f"目前摘要代理正在使用 {LLM_PROVIDER} 的 {LLM_MODEL_ID} 模型。",
    ]
    if payload.weather_advice:
        parts.append(f"天氣建議：{payload.weather_advice}")
    if payload.train_options:
        items = "、".join(payload.train_options)
        parts.append(f"火車班次建議：{items}")
    if payload.budget:
        parts.append(f"預算參考：{payload.budget}")

    if len(parts) == 2:
        parts.append("尚未接收到遠端代理的建議，請稍候或透過 HITL 補充資訊。")

    recommendation = "\n".join(parts)
    return SummaryResponse(
        task_id=payload.task_id,
        provider=LLM_PROVIDER,
        model=LLM_MODEL_ID,
        recommendation=recommendation,
    )


@APP.get("/")
def healthcheck() -> JSONResponse:
    """Return a status payload describing the configured model."""
    return JSONResponse(
        {
            "status": "OK",
            "agent": "Summary Agent",
            "port": PORT,
            "llm_provider": LLM_PROVIDER,
            "llm_model_id": LLM_MODEL_ID,
        }
    )


@APP.post("/summaries", response_model=SummaryResponse)
def summarize(payload: SummaryRequest) -> SummaryResponse:
    """Accept intermediate results and craft a user friendly summary."""
    return craft_summary(payload)


if __name__ == "__main__":
    uvicorn.run(app="main:APP", host="0.0.0.0", port=PORT)
