"""Pydantic models for dashboard statistics."""

from pydantic import BaseModel

from app.models.instance import InstanceType


class DashboardStats(BaseModel):
    """Response model for overall system statistics.

    Aggregates usage across all test types (``voice`` / ``chat`` sessions in the
    ``sessions`` table plus ``image`` records in the ``image_generations`` table).

    ``total_sessions`` is retained for backward compatibility with the original
    voice-only dashboard, while ``total_tests`` represents the combined count of
    sessions and image generations.
    """

    total_instances: int
    total_sessions: int
    # sessions + image_generations. Defaults to 0 so callers that only track
    # sessions (e.g. the legacy /stats route) keep working unchanged.
    total_tests: int = 0
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


class TypeUsage(BaseModel):
    """Response model for per-test-type usage aggregation.

    ``test_count`` combines sessions (for ``voice`` / ``chat``) or image
    generations (for ``image``) that match the requested filter.
    """

    type: InstanceType
    test_count: int
    total_input_tokens: int
    total_output_tokens: int
