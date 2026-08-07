/** 实例测试类型：语音实时对话 / 大语言模型对话 / 图像生成 */
export type InstanceType = 'voice' | 'chat' | 'image';

/** Azure OpenAI 实例配置 */
export interface Instance {
  id: string;
  name: string;
  endpoint: string;
  deployment: string;
  type: InstanceType;
  description: string;
  created_at: string;
}

/** 实例详情（含脱敏 API Key 和用量统计） */
export interface InstanceDetail extends Instance {
  api_key_masked: string;
  updated_at: string;
  total_sessions: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

/** 语音对话会话 */
export interface Session {
  id: string;
  instance_id: string;
  instance_name: string;
  room_name: string;
  status: 'connecting' | 'connected' | 'completed' | 'error' | 'cancelled';
  start_time: string;
  end_time: string | null;
  input_tokens: number;
  output_tokens: number;
  error_message: string | null;
}

/** 调试日志条目 */
export interface LogEntry {
  id: number;
  session_id: string;
  timestamp: string;
  direction: 'inbound' | 'outbound' | 'internal';
  event_type: string;
  payload: string;
}

/** 连接状态 */
export type ConnectionState =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'agent_speaking'
  | 'user_speaking'
  | 'disconnected';

/** Dashboard 统计数据 */
export interface DashboardStats {
  total_instances: number;
  total_sessions: number;
  /** sessions + image_generations 的合计测试数 */
  total_tests: number;
  active_sessions: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

/** 按测试类型聚合的用量（voice / chat / image） */
export interface TypeUsage {
  type: InstanceType;
  test_count: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

/** 按实例统计的用量 */
export interface InstanceUsage {
  instance_id: string;
  instance_name: string;
  session_count: number;
  total_input_tokens: number;
  total_output_tokens: number;
}

/** 分页会话列表 */
export interface PaginatedSessions {
  items: Session[];
  total: number;
  page: number;
  page_size: number;
}

/** 创建会话响应 */
export interface SessionResponse {
  session_id: string;
  room_name: string;
  livekit_token: string;
  livekit_url: string;
}

/** 对话消息记录 */
export interface Message {
  id: number;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

// ---------------------------------------------------------------------------
// Chat（大语言模型对话）
// ---------------------------------------------------------------------------

/** 单条对话消息（多轮上下文中的一项） */
export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

/**
 * Chat 参数（客户端参数对象）。
 * 字段名与后端 ChatCompletionRequest 保持一致（system_prompt / temperature / max_tokens），
 * 便于直接作为请求体提交。
 */
export interface ChatParams {
  system_prompt: string;
  temperature: number; // clamp 到 [0, 2]
  max_tokens: number | null; // null 透传；否则为正整数
}

/** Token 用量（后端 usage：input_tokens / output_tokens） */
export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
}

/**
 * Chat SSE 事件（判别联合），对应后端 /api/chat/completions 下发的
 * text/event-stream 数据行的 `type` 字段。
 */
export type ChatStreamEvent =
  | { type: 'session'; session_id: string }
  | { type: 'delta'; content: string }
  | { type: 'done'; usage: TokenUsage }
  | { type: 'error'; message: string };

// ---------------------------------------------------------------------------
// Image（图像生成）
// ---------------------------------------------------------------------------

/** 图像生成参数 */
export interface ImageParams {
  size: string;
  quality: 'low' | 'medium' | 'high';
  output_format: string;
  compression: number; // 0-100
  n: number; // >= 1
}

/**
 * 图像生成记录。
 *
 * 覆盖后端两种响应形态：
 * - POST /api/images/generations 返回的 ImageGenerationResponse
 *   （generation_id / instance_id / prompt / params / images / input_tokens /
 *    output_tokens / has_reference / created_at）
 * - GET /api/images（列表）与 GET /api/images/{id}（详情）返回的行字典
 *   （额外含 id / session_id / size / quality / output_format / compression /
 *    n / image_paths / status / error_message）
 */
export interface ImageGeneration {
  generation_id: string;
  instance_id: string;
  prompt: string;
  params: ImageParams;
  images: string[]; // 可访问 URL：/api/images/{id}/{index}
  input_tokens: number;
  output_tokens: number;
  has_reference: boolean;
  created_at: string;
  // 列表/详情行字典附带字段（响应形态不同，标记为可选）
  id?: string;
  session_id?: string | null;
  size?: string;
  quality?: string;
  output_format?: string;
  compression?: number;
  n?: number;
  image_paths?: string[];
  status?: string;
  error_message?: string | null;
}

// ---------------------------------------------------------------------------
// Unified History（统一历史）
// ---------------------------------------------------------------------------

/** 统一历史条目的类型（与实例类型一致） */
export type HistoryItemType = InstanceType;

/** 统一历史条目：合并 voice/chat 会话与 image 生成记录 */
export interface HistoryItem {
  id: string;
  type: InstanceType;
  instance_id: string;
  instance_name: string;
  title: string; // chat: 首条用户消息摘要；image: prompt 摘要；voice: room_name
  start_time: string;
  input_tokens: number;
  output_tokens: number;
  status: string;
}

/** 统一历史分页响应 */
export interface PaginatedHistory {
  items: HistoryItem[];
  total: number;
  page: number;
  page_size: number;
}
