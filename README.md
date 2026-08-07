# LiveKit × Qwen-Omni-Realtime Demo

用 [LiveKit Agents](https://docs.livekit.io/agents/) 对接阿里云百炼的
**Qwen-Omni-Realtime** 实时音视频对话模型。

## 为什么可行

Qwen-Omni-Realtime 在协议层复刻了 **OpenAI Realtime API**（相同事件名：
`session.update` / `input_audio_buffer.*` / `response.create` /
`response.audio.*` / `conversation.item.*`），因此可以直接复用 LiveKit 的
`openai.realtime.RealtimeModel` 插件，只把 endpoint / api_key / model 指向百炼即可。

## 目录结构

```
qwen_livekit_demo/
├── qwen_realtime_agent.py   # 主程序
├── .env.example             # 环境变量模板
├── requirements.txt         # 依赖
└── README.md
```

## 前置准备

1. **LiveKit 账号**：注册 [LiveKit Cloud](https://cloud.livekit.io/)（或自建服务），
   拿到 `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET`。
2. **阿里云百炼（Model Studio）**：开通 Qwen-Omni-Realtime，拿到：
   - `DASHSCOPE_API_KEY`（API Key）
   - `QWEN_WORKSPACE_ID`（百炼 workspace ID）
   - region：新加坡 `ap-southeast-1` 或北京 `cn-beijing`（两地 key 独立）

## 安装

```bash
# 推荐用 uv
uv add "livekit-agents[openai,silero]~=1.5" python-dotenv

# 或用 pip
pip install -r requirements.txt
```

## 配置

```bash
cp .env.example .env
# 编辑 .env，填入上面拿到的各项 key
```

`.env` 字段说明：

| 变量 | 说明 |
| --- | --- |
| `LIVEKIT_URL` | LiveKit 服务地址，如 `wss://xxx.livekit.cloud` |
| `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | LiveKit 鉴权 |
| `DASHSCOPE_API_KEY` | 百炼 API Key（`sk-...`） |
| `QWEN_WORKSPACE_ID` | 百炼 workspace ID |
| `QWEN_REGION` | `ap-southeast-1`（新加坡）或 `cn-beijing`（北京） |
| `QWEN_MODEL` | 默认 `qwen3.5-omni-plus-realtime` |

## 运行

```bash
python qwen_realtime_agent.py dev
```

启动后 worker 会连接到你的 LiveKit 项目。用
[Agents Playground](https://agents-playground.livekit.io/) 或你自己的前端 SDK
加入同一个房间，即可开始语音对话。

## ⚠️ 实测时重点验证

由于是「借用」OpenAI 插件对接 Qwen，以下几处最容易踩坑：

1. **鉴权 / URL 拼接**：确认插件能原样拼出带 `{WorkspaceId}` 与 `?model=` 的
   URL，并带上 `Authorization: Bearer <DASHSCOPE_API_KEY>` 头。若不行，需要覆盖
   `base_url` 拼接逻辑或改用方案 B。
2. **音频格式 / 采样率**：确认 Qwen 接受的 PCM 格式与 LiveKit 默认发送的一致
   （通常 24kHz PCM16）。
3. **事件字段细节**：`turn_detection` 参数、`voice`（音色名）等个别字段可能与
   OpenAI 有出入，按报错微调。

## 备选方案 B（最稳妥）

若方案 A 存在字段不兼容，可基于 LiveKit `llm.RealtimeModel` 基类封装一个
Qwen 专用插件，内部用 DashScope 的 `OmniRealtimeConversation` SDK 或原生
WebSocket 桥接。

## 参考

- [LiveKit Agents 文档](https://docs.livekit.io/agents/)
- [Qwen-Omni-Realtime 官方文档](https://help.aliyun.com/zh/model-studio/realtime)
