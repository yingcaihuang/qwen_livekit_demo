/** Azure OpenAI 实例配置 */
export interface Instance {
  id: string;
  name: string;
  endpoint: string;
  deployment: string;
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
  active_sessions: number;
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
