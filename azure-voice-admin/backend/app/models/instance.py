"""Pydantic models for Instance configuration management."""

from typing import Literal

from pydantic import BaseModel

# 实例测试类型：语音实时对话 / 大语言模型对话 / 图像生成 / 实时翻译 / 实时转录
InstanceType = Literal["voice", "chat", "image", "translate", "transcribe"]


class InstanceCreate(BaseModel):
    """Request model for creating a new Instance."""

    name: str  # 非空，唯一
    endpoint: str  # 非空，Azure 端点 URL
    api_key: str  # 非空
    deployment: str  # 非空，部署名称
    type: InstanceType  # 必填，测试类型（创建后不可变）
    description: str = ""


class InstanceUpdate(BaseModel):
    """Request model for updating an existing Instance (partial update)."""

    name: str | None = None
    endpoint: str | None = None
    api_key: str | None = None
    deployment: str | None = None
    description: str | None = None


class InstanceSummary(BaseModel):
    """Response model for Instance list items (no api_key exposed)."""

    id: str
    name: str
    endpoint: str
    deployment: str
    type: InstanceType  # 测试类型
    description: str
    created_at: str


class InstanceDetail(BaseModel):
    """Response model for Instance detail view with masked key and usage stats."""

    id: str
    name: str
    endpoint: str
    api_key_masked: str  # 脱敏后的 key
    deployment: str
    type: InstanceType  # 测试类型
    description: str
    created_at: str
    updated_at: str
    total_sessions: int
    total_input_tokens: int
    total_output_tokens: int


class ExportRequest(BaseModel):
    """Request model for exporting instances."""

    instance_ids: list[str]
    include_api_key: bool = False


class ImportInstanceItem(BaseModel):
    """Single instance item in an import payload."""

    name: str
    endpoint: str
    api_key: str = ""
    deployment: str
    type: InstanceType
    description: str = ""


class ImportRequest(BaseModel):
    """Request model for importing instances."""

    instances: list["ImportInstanceItem"]
    conflict_strategy: Literal["skip", "update"] = "skip"


class ImportResult(BaseModel):
    """Response model for import operation results."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = []
