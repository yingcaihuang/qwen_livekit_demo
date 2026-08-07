"""Pydantic models for dashboard statistics."""

from pydantic import BaseModel


class DashboardStats(BaseModel):
    """Response model for overall system statistics."""

    total_instances: int
    total_sessions: int
    active_sessions: int
    total_input_tokens: int
    total_output_tokens: int


class InstanceUsage(BaseModel):
    """Response model for per-instance token usage summary."""

    instance_id: str
    instance_name: str
    session_count: int
    total_input_tokens: int
    total_output_tokens: int
