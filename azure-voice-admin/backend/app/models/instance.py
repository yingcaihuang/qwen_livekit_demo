"""Pydantic models for Instance configuration management."""

from typing import Optional

from pydantic import BaseModel


class InstanceCreate(BaseModel):
    """Request model for creating a new Instance."""

    name: str  # 非空，唯一
    endpoint: str  # 非空，Azure 端点 URL
    api_key: str  # 非空
    deployment: str  # 非空，部署名称
    description: str = ""


class InstanceUpdate(BaseModel):
    """Request model for updating an existing Instance (partial update)."""

    name: Optional[str] = None
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    deployment: Optional[str] = None
    description: Optional[str] = None


class InstanceSummary(BaseModel):
    """Response model for Instance list items (no api_key exposed)."""

    id: str
    name: str
    endpoint: str
    deployment: str
    description: str
    created_at: str


class InstanceDetail(BaseModel):
    """Response model for Instance detail view with masked key and usage stats."""

    id: str
    name: str
    endpoint: str
    api_key_masked: str  # 脱敏后的 key
    deployment: str
    description: str
    created_at: str
    updated_at: str
    total_sessions: int
    total_input_tokens: int
    total_output_tokens: int
