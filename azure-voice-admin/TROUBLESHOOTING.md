# Troubleshooting Guide / 故障排查指南

本文档记录部署 Azure Voice Testing Admin 过程中遇到的所有问题及解决方案。

---

## 1. LiveKit API Key 不一致 — 401 Unauthorized

**现象：** 浏览器连接 LiveKit 时返回 `invalid API key`

**原因：** `livekit.yaml` 中的 keys 和 `.env.production` 中的 `LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET` 不一致。Backend 用 `.env.production` 的 key 签发 JWT，但 LiveKit 用 `livekit.yaml` 的 key 验证。

**解决方案：** 使用 `genkey_config.sh` 生成配置，确保只有一份 key 来源。`livekit-entrypoint.sh` 会从环境变量动态生成 `livekit.yaml`，彻底消除不一致。

```bash
./genkey_config.sh
docker compose --env-file .env.production up -d --force-recreate
```

---

## 2. LiveKit panic: invalid argument to Intn

**现象：** LiveKit 容器反复 crash，日志显示 `panic: invalid argument to Intn` at `getNAT1to1IPsForConf`

**原因：** LiveKit 1.13.5 的 bug — 当配置了 `use_external_ip: true` 但容器内无法自动检测到外部 IP 时触发 panic。

**解决方案：** 不使用 `use_external_ip: true`，只配置 `node_ip`。`livekit-entrypoint.sh` 已修复为仅在设置了 `LIVEKIT_NODE_IP` 时添加 `node_ip` 行，不再设置 `use_external_ip`。

---

## 3. WebRTC Peer Connection 失败 — 语音房间 Disconnected

**现象：** 语音会话创建成功（Debug Console 显示 agent.started），但 Voice Room 显示 "Disconnected"，控制台报 `could not establish pc connection`

**原因：** WebRTC 需要 UDP/TCP 直连，浏览器无法到达 LiveKit 的 7881/7882 端口。

**解决方案：**
1. 在 `.env.production` 中设置 `LIVEKIT_NODE_IP=<服务器公网IP>`
2. 确保云平台安全组/防火墙开放：
   - **TCP 7881** — WebRTC TCP 候选
   - **UDP 7882** — WebRTC 媒体传输（**必须开放 UDP**）
3. 验证：`ss -tlnp | grep 7881` 和 `ss -ulnp | grep 7882`

---

## 4. WSS 连接失败 — ERR_SSL_PROTOCOL_ERROR

**现象：** 浏览器连接 `wss://rtc.verycloud.cn:7880` 时 SSL 协议错误

**原因：** LiveKit 的 7880 端口运行的是明文 WebSocket（ws://），但浏览器通过 HTTPS 页面尝试 wss:// 连接。

**解决方案：** 通过 Caddy 反向代理 LiveKit 的 WebSocket：
- Caddyfile 中添加 `{$RTC_DOMAIN}` 块代理到 `livekit:7880`
- `.env.production` 设置 `RTC_DOMAIN=rtc.verycloud.cn`
- `LIVEKIT_PUBLIC_URL=wss://rtc.verycloud.cn`（标准 443 端口，Caddy 自动 TLS）
- LiveKit 的 7880 端口不再对外暴露，只通过 Caddy 内部转发

---

## 5. livekit-agents import 导致 Core Dump（AVX2）

**现象：** `import livekit.agents` 在容器内 segfault/core dump，语音功能完全不可用

**原因：** `livekit-agents` >= 1.0 包含 Rust 编译的本地扩展（`livekit` 包的 `_livekit_ffi.so`），部分版本需要 AVX2 指令集。

**排查：**
```bash
# 检查宿主机 CPU 是否支持 AVX2
grep -o 'avx2' /proc/cpuinfo | head -1

# 在容器内测试 import
docker exec azure-voice-admin-backend-1 timeout 10 python -c "import livekit.agents; print('OK')"
```

**解决方案：**
- 如果宿主机**支持 AVX2** 但容器内还是 crash → `docker compose build backend --no-cache` 重新编译
- 如果宿主机**不支持 AVX2** → 升级到支持 AVX2 的 CPU（Intel Haswell 2013+ / AMD Excavator 2015+），前端会自动显示警告

---

## 6. Docker 构建缓存导致代码不更新

**现象：** `git pull` 拉了新代码但 Docker 容器里还是旧代码

**原因：** Docker 的 `COPY . .` 层有时因为 context hash 判断问题使用了旧缓存。

**解决方案：**
```bash
# 强制不使用缓存重新构建
docker compose build --no-cache
docker compose --env-file .env.production up -d --force-recreate
```

---

## 7. Backend 启动时 LiveKit 不可达

**现象：** `/api/health` 返回 `livekit_connected: false`，前端显示"实时功能不可用"

**原因：** Docker Compose 启动时序问题 — backend 启动检测 LiveKit 连通性时，livekit 容器还没完全 ready（尤其是使用 entrypoint 脚本时启动较慢）。

**解决方案：** 重启 backend（此时 livekit 已经在运行）：
```bash
docker compose --env-file .env.production restart backend
```

注意：`livekit_reachable` 只在启动时检测一次。未来可改为定期检测。

---

## 8. SCIM 用户同步后角色为 viewer（不是预期的 super_admin）

**现象：** Authentik SCIM 同步用户后，所有用户的 SSO 组为空，角色全是 viewer

**原因（分两层）：**
1. SCIM `PUT/PATCH Groups` 的 `members[].value` 用的是我们返回的 SCIM `id`（内部 user_id），但代码只查 `sso_subject` 匹配不上
2. SCIM 组的 members 操作代码之前完全没有实现（只处理了 displayName）

**解决方案：** 已修复代码 — `_sync_group_members` 现在同时查询 `id` 和 `sso_subject`，并正确处理 PUT/PATCH Groups 的 members 数组。

---

## 9. Caddy 502 Bad Gateway

**现象：** 访问站点返回 502，Caddy 日志显示 `dial tcp: connection refused`

**可能原因：**
- Backend 容器还没启动完成
- LiveKit 容器在 crash loop（Caddy 尝试代理 RTC 域名到 livekit 但 livekit 没启动）

**解决方案：**
```bash
# 确认所有容器状态
docker compose ps

# 如果 livekit 在 Restarting，检查其日志
docker logs azure-voice-admin-livekit-1 --tail 20

# 等所有容器稳定后重启 backend
docker compose --env-file .env.production restart backend
```

---

## 10. 前端没更新（缓存旧版本）

**现象：** 代码已更新但浏览器显示旧界面，`grep "翻译"` 在前端 JS 中找不到

**原因：** Caddy 镜像使用了 Docker 构建缓存中的旧前端产物。

**解决方案：**
```bash
docker compose build caddy --no-cache
docker compose --env-file .env.production up -d --force-recreate caddy
```

浏览器端：`Ctrl+Shift+R` 强制刷新清除缓存。

---

## 11. genkey_config.sh 域名为空

**现象：** 运行 `genkey_config.sh` 时直接回车，生成了 `SITE_DOMAIN=` 和 `LIVEKIT_PUBLIC_URL=wss://` 的无效配置

**解决方案：** 已修复 — 脚本现在使用 while 循环验证域名输入不能为空，会持续提示直到输入有效值。

---

## 12. Debian Docker 构建慢（apt/pip 超时）

**现象：** `docker compose build backend` 在 apt-get 或 pip install 步骤卡很久

**原因：** 默认使用国外源，国内网络慢。

**解决方案：** Dockerfile 已配置国内镜像源：
- APT: `mirrors.aliyun.com`
- pip: `mirrors.aliyun.com/pypi/simple/`
- npm/pnpm: `registry.npmmirror.com`

---

## 常用排查命令

```bash
# 查看所有服务状态
docker compose ps

# 查看所有服务日志
docker compose --env-file .env.production logs --tail 50

# 查看特定服务日志
docker logs azure-voice-admin-livekit-1 --tail 20
docker logs azure-voice-admin-backend-1 --tail 20
docker logs azure-voice-admin-caddy-1 --tail 20

# 健康检查
curl -sk https://your-domain/api/health

# 检查 LiveKit 连通性
docker exec azure-voice-admin-backend-1 python -c "
import socket
s = socket.socket(); s.settimeout(3)
try: s.connect(('livekit', 7880)); print('OK')
except Exception as e: print('FAIL:', e)
s.close()
"

# 检查活跃 worker 进程
docker exec azure-voice-admin-backend-1 python -c "
from app.services.process_manager import process_manager
print('active:', list(process_manager._processes.keys()))
"

# 清理僵尸会话
docker exec azure-voice-admin-backend-1 python -c "
import sqlite3
db = sqlite3.connect('/app/data/voice_admin.db')
cur = db.execute(\"UPDATE sessions SET status = 'cancelled' WHERE status = 'connecting'\")
db.commit()
print(f'清理了 {cur.rowcount} 个')
"

# 检查端口开放
ss -tlnp | grep 7881
ss -ulnp | grep 7882
```

---

## 端口清单

| 端口 | 协议 | 用途 | 对外暴露 |
|------|------|------|----------|
| 80 | TCP | HTTP → HTTPS 重定向 | ✅ |
| 443 | TCP/UDP | HTTPS + HTTP/3 (Caddy) | ✅ |
| 7880 | TCP | LiveKit WebSocket 信令 | ❌ (仅内部，通过 Caddy 代理) |
| 7881 | TCP | WebRTC TCP 候选 | ✅ 必须开放 |
| 7882 | UDP | WebRTC 媒体传输 | ✅ 必须开放 |
| 8090 | TCP | Backend API | ❌ (仅内部，通过 Caddy 代理) |
