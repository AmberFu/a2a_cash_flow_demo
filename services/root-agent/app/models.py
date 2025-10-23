"""Pydantic models for the Root Agent API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UserRequirement(BaseModel):
    origin: str = Field(..., description="User's starting point.")
    destination: str = Field(..., description="Where the user wants to travel.")
    travel_date: str = Field(..., description="Target travel date in YYYY-MM-DD format.")
    desired_arrival_time: str = Field(..., description="Preferred arrival time in HH:MM format.")
    time_range: Optional[str] = Field(
        None,
        description="High level time range hint such as '上午', '下午', '晚上'.",
    )
    transport_note: Optional[str] = Field(
        None,
        description="Additional note or preference provided by the user.",
    )


class CreateTaskRequest(BaseModel):
    loan_case_id: str = Field(..., description="The business identifier for the loan case.")
    user_requirement: Optional[UserRequirement] = Field(
        None,
        description="Optional structured travel requirement used for local end-to-end tests.",
    )


class CreateTaskResponse(BaseModel):
    task_id: str
    message: str
    status: Optional[str] = Field(
        None, description="Workflow status when the request returns."
    )
    summary: Optional[Dict[str, Any]] = Field(
        None, description="Final summary payload when running in local synchronous mode."
    )


class CallbackRequest(BaseModel):
    task_id: str
    source: str = Field(..., description="e.g., 'remote-agent-a', 'remote-agent-b'")
    status: str = Field(..., description="The new status to set for the task.")
    result: Dict[str, Any] = Field(description="The output from the remote agent.")
    needs_info: Optional[List[str]] = Field(
        None, description="Questions for HITL, if any."
    )


class HITLAnswerRequest(BaseModel):
    answer: str = Field(..., description="The human-provided answer or information.")


__all__ = [
    "UserRequirement",
    "CreateTaskRequest",
    "CreateTaskResponse",
    "CallbackRequest",
    "HITLAnswerRequest",
]
