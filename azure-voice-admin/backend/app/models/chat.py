"""Pydantic models for LLM Chat (Chat Completions) testing."""

from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """单条对话消息（多轮上下文中的一项）。"""

    role: Literal["system", "user", "assistant"]  # 消息角色
    content: str  # 消息文本内容


class ChatCompletionRequest(BaseModel):
    """流式对话请求体（POST /api/chat/completions）。"""

    instance_id: str  # 目标 chat 实例 ID
    session_id: str | None = None  # 为空则惰性创建新会话
    model: str | None = None  # 从实例 deployment 列表中选定的具体部署；None 表示用实例默认
    messages: list[ChatMessage]  # 累积的多轮对话上下文
    system_prompt: str | None = None  # 可选系统提示词（注入首条 system 消息）
    temperature: float = 1.0  # 服务端 clamp 到 [0, 2]
    max_tokens: int | None = None  # None 透传；否则服务端约束为正整数


class ChatMessageRecord(BaseModel):
    """已持久化的对话消息记录（响应模型）。"""

    id: int  # session_messages 表自增主键
    session_id: str  # 所属会话 ID
    role: Literal["user", "assistant"]  # 持久化消息仅含 user / assistant
    content: str  # 消息文本内容
    timestamp: str  # 消息时间戳
