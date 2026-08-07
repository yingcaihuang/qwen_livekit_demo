"""Pydantic models for Unified History across voice / chat / image tests."""

from pydantic import BaseModel

from app.models.instance import InstanceType


class HistoryItem(BaseModel):
    """统一历史条目：合并 voice/chat 会话与 image 生成记录的通用视图。"""

    id: str
    type: InstanceType  # 记录类型：voice / chat / image（取自 instances.type）
    instance_id: str
    instance_name: str
    title: str  # chat: 首条用户消息摘要；image: prompt 摘要；voice: room_name
    start_time: str  # 开始时间，用于倒序排序
    input_tokens: int
    output_tokens: int
    status: str


class PaginatedHistory(BaseModel):
    """统一历史分页响应。"""

    items: list[HistoryItem]
    total: int
    page: int
    page_size: int
