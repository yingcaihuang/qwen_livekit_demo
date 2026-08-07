-- Azure Voice Testing Admin - Database Schema

CREATE TABLE IF NOT EXISTS instances (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    api_key TEXT NOT NULL,
    deployment TEXT NOT NULL,
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
