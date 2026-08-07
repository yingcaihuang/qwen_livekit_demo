"""Pydantic models for Image Generation (Images generations/edits) testing."""

from typing import Literal

from pydantic import BaseModel


class ImageParams(BaseModel):
    """图像生成参数（服务端会对越界值做二次约束）。"""

    size: str = "1024x1024"  # 图片尺寸，如 "1024x1024"
    quality: Literal["low", "medium", "high"] = "high"  # 生成质量
    output_format: str = "png"  # 输出格式，至少支持 png
    compression: int = 100  # 压缩级别，clamp 到 [0, 100]
    n: int = 1  # 生成变体数量，>= 1


class ImageGenerationRequest(BaseModel):
    """图像生成请求（结构化校验用）。

    实际 HTTP 端点为 multipart/form-data（见 POST /api/images/generations），
    该模型用于组织/校验从表单解析出的字段；可选参考图另经 UploadFile 传入。
    """

    instance_id: str  # 目标 image 实例 ID
    prompt: str  # 生成提示词
    params: ImageParams = ImageParams()  # 生成参数（size/quality/output_format/compression/n）


class ImageGenerationResponse(BaseModel):
    """图像生成响应（POST /api/images/generations）。"""

    generation_id: str  # 本次生成的唯一 ID
    instance_id: str  # 所属实例 ID
    prompt: str  # 生成提示词（回显）
    params: ImageParams  # 实际使用的参数（回显）
    images: list[str]  # 可访问 URL 列表：/api/images/{generation_id}/{index}
    input_tokens: int  # 输入 token 用量（Azure usage.input_tokens）
    output_tokens: int  # 输出 token 用量（Azure usage.output_tokens）
    has_reference: bool  # 是否为参考图编辑（edits 分支）
    created_at: str  # 创建时间戳
    started_at: str | None = None  # Azure 请求开始的墙钟时间（UTC）
    ended_at: str | None = None  # Azure 请求结束的墙钟时间（UTC）
    duration_ms: int | None = None  # Azure 请求总耗时（毫秒），不含本地写文件
    ttfb_ms: int | None = None  # 首字节耗时（毫秒），从发起请求到收到响应头
