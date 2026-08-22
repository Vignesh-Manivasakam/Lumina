-- ============================================================
-- Lumina Enterprise: Usage & Token Metering
-- Migration: 003_usage_tracking.sql
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS usage_log (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   TEXT NOT NULL,
    user_id      UUID REFERENCES users(id) ON DELETE SET NULL,
    query        TEXT,
    model        TEXT,
    route        TEXT,
    prompt_tokens INT NOT NULL DEFAULT 0,
    completion_tokens INT NOT NULL DEFAULT 0,
    total_tokens INT NOT NULL DEFAULT 0,
    latency_ms   INT NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_usage_log_session_id ON usage_log(session_id);
CREATE INDEX IF NOT EXISTS idx_usage_log_user_id ON usage_log(user_id);
CREATE INDEX IF NOT EXISTS idx_usage_log_created_at ON usage_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_log_model ON usage_log(model);

-- Enable RLS
ALTER TABLE usage_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS usage_log_all_service ON usage_log;
CREATE POLICY usage_log_all_service ON usage_log
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
