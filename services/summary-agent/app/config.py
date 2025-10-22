"""Configuration helpers for the Summary Agent service."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field


class AgentSettings(BaseModel):
    """Runtime configuration loaded from environment variables."""

    port: int = Field(50003, description="Service port")
    llm_provider: str = Field("bedrock", description="Identifier of the backing LLM provider")
    llm_model_id: str = Field(
        "anthropic.claude-3-haiku-20240307-v1:0",
        description="Identifier of the backing LLM model",
    )

    @classmethod
    def from_env(cls) -> "AgentSettings":
        """Create a settings object from environment variables."""

        return cls(
            port=int(os.environ.get("PORT", cls.model_fields["port"].default)),
            llm_provider=os.environ.get(
                "LLM_PROVIDER", cls.model_fields["llm_provider"].default
            ),
            llm_model_id=os.environ.get(
                "LLM_MODEL_ID", cls.model_fields["llm_model_id"].default
            ),
        )


@lru_cache()
def get_settings() -> AgentSettings:
    """Return a cached :class:`AgentSettings` instance."""

    return AgentSettings.from_env()

