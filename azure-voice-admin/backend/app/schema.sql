-- Azure Voice Testing Admin - Database Schema

CREATE TABLE IF NOT EXISTS instances (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    api_key TEXT NOT NULL,
    deployment TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'voice',
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    instance_id TEXT NOT NULL REFERENCES instances(id),
    room_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'connecting',
    start_time TEXT NOT NULL DEFAULT (datetime('now')),
    end_time TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS session_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    timestamp TEXT NOT NULL,
    direction TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sessions_instance_id ON sessions(instance_id);
CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON sessions(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_session_logs_session_id ON session_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_session_logs_event_type ON session_logs(event_type);

CREATE TABLE IF NOT EXISTS session_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,  -- 'user' or 'assistant'
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    model TEXT,     -- deployment/model used for an assistant turn; NULL for user rows
    endpoint TEXT   -- full resolved Azure URL hit for an assistant turn; NULL for user rows
);

CREATE INDEX IF NOT EXISTS idx_session_messages_session_id ON session_messages(session_id);

CREATE TABLE IF NOT EXISTS image_generations (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    instance_id TEXT NOT NULL REFERENCES instances(id) ON DELETE CASCADE,
    session_id TEXT,
    prompt TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    size TEXT,
    quality TEXT,
    output_format TEXT,
    compression INTEGER,
    n INTEGER DEFAULT 1,
    has_reference INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    image_paths TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'completed',
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    ended_at TEXT,
    duration_ms INTEGER,
    ttfb_ms INTEGER
);

CREATE INDEX IF NOT EXISTS idx_image_generations_instance_id ON image_generations(instance_id);
CREATE INDEX IF NOT EXISTS idx_image_generations_created_at ON image_generations(created_at DESC);

-- ============================================================
-- 鉴权系统表（user-auth-rbac-sso）
-- ============================================================

-- 用户（本地账号与 SSO 账号统一存储）
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    username TEXT NOT NULL UNIQUE,        -- 本地登录名 / SSO 稳定标识（sub 或 preferred_username）
    email TEXT,
    auth_source TEXT NOT NULL DEFAULT 'local',  -- 'local' | 'sso'
    password_hash TEXT,                   -- 仅本地账号；SSO 账号为 NULL
    sso_subject TEXT UNIQUE,              -- OIDC sub；本地账号为 NULL
    is_active INTEGER NOT NULL DEFAULT 1, -- 0 表示禁用
    must_change_password INTEGER NOT NULL DEFAULT 0,
    sso_groups TEXT DEFAULT '[]',         -- JSON array of Authentik group names
    role_override INTEGER NOT NULL DEFAULT 0,  -- 1=角色已手动覆盖,SSO登录不再自动更新
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 用户→角色（多对多；四级角色以字符串存储，取值受应用层校验约束）
CREATE TABLE IF NOT EXISTS user_roles (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                   -- 'super_admin'|'admin'|'tester'|'viewer'
    PRIMARY KEY (user_id, role)
);

-- Authentik 组名 → 平台角色 映射
CREATE TABLE IF NOT EXISTS group_role_mappings (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    group_name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,                   -- 四个合法角色之一（应用层校验）
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- SSO 配置（单行有效；client_secret 密文存储）
CREATE TABLE IF NOT EXISTS sso_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),  -- 单例行
    issuer TEXT,
    discovery_url TEXT,
    client_id TEXT,
    client_secret_encrypted TEXT,         -- 对称加密后的密文，绝不明文
    authorization_endpoint TEXT,
    token_endpoint TEXT,
    userinfo_endpoint TEXT,
    jwks_uri TEXT,
    redirect_uri TEXT,
    scopes TEXT NOT NULL DEFAULT 'openid profile email groups',
    groups_claim TEXT NOT NULL DEFAULT 'groups',
    groups_source TEXT NOT NULL DEFAULT 'userinfo',  -- 'userinfo' | 'id_token'
    end_session_endpoint TEXT,
    login_button_enabled INTEGER NOT NULL DEFAULT 0,  -- 首页统一认证入口开关
    cookie_secure INTEGER NOT NULL DEFAULT 0,
    scim_token TEXT,                              -- SCIM v2 Bearer token (plaintext)
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 服务端会话
CREATE TABLE IF NOT EXISTS auth_sessions (
    id TEXT PRIMARY KEY,                  -- session token（随机 256bit，存哈希更佳）
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,
    csrf_token TEXT NOT NULL              -- 双提交 CSRF 令牌
);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);

-- 登录失败限流记录
CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL,             -- 客户端标识（IP / 用户名）
    attempted_at TEXT NOT NULL DEFAULT (datetime('now')),
    success INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_login_attempts_source ON login_attempts(source_key, attempted_at);

-- OIDC 登录临时态（state/nonce/PKCE），短生命周期
CREATE TABLE IF NOT EXISTS oidc_login_state (
    state TEXT PRIMARY KEY,
    nonce TEXT NOT NULL,
    code_verifier TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
