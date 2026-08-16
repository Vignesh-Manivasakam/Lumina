-- ============================================================
-- Lumina Enterprise: Users, Conversations, and MCP Connections
-- Migration: 001_users_conversations.sql
-- ============================================================
-- Apply AFTER `backend/supabase_schema.sql` and `backend/supabase_migrations/002_session_rls.sql`.
--
-- Adds:
-- 1. `users` table for enterprise user profiles and authentication providers.
-- 2. `conversations` table for multi-turn persistent conversation threads.
-- 3. `conversation_id` FK column on existing `messages` table.
-- 4. `mcp_connections` table for Model Context Protocol server endpoints.
-- 5. Comprehensive indexes for performance and foreign key lookups.
-- 6. Row Level Security (RLS) policies and touch_updated_at triggers.
--
-- Idempotent: safe to re-run.

-- Ensure UUID generation extension is active
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ------------------------------------------------------------
-- 1. Users Table
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name  TEXT,
    email         TEXT UNIQUE,
    auth_provider TEXT NOT NULL DEFAULT 'anonymous',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 2. Conversations Table
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    session_id  TEXT,
    title       TEXT NOT NULL DEFAULT 'New conversation',
    is_archived BOOLEAN NOT NULL DEFAULT false,
    metadata    JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 3. Extend Messages Table with conversation_id FK
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'messages' AND column_name = 'conversation_id'
    ) THEN
        ALTER TABLE messages
            ADD COLUMN conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL;
    END IF;
END $$;

-- ------------------------------------------------------------
-- 4. MCP Connections Table
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mcp_connections (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL,
    endpoint_url TEXT NOT NULL,
    transport    TEXT NOT NULL DEFAULT 'sse',
    scope        TEXT NOT NULL DEFAULT 'workspace',
    session_id   UUID,
    user_id      UUID REFERENCES users(id) ON DELETE SET NULL,
    tools_schema JSONB NOT NULL DEFAULT '[]',
    is_active    BOOLEAN NOT NULL DEFAULT true,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 5. Performance Indexes
-- ------------------------------------------------------------
-- Users indexes
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_auth_provider ON users(auth_provider);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at DESC);

-- Conversations indexes
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_session_id ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_conversations_is_archived ON conversations(is_archived);
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at DESC);

-- Messages conversation lookup index
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);

-- MCP Connections indexes
CREATE INDEX IF NOT EXISTS idx_mcp_connections_user_id ON mcp_connections(user_id);
CREATE INDEX IF NOT EXISTS idx_mcp_connections_scope ON mcp_connections(scope);
CREATE INDEX IF NOT EXISTS idx_mcp_connections_name ON mcp_connections(name);
CREATE INDEX IF NOT EXISTS idx_mcp_connections_is_active ON mcp_connections(is_active);
CREATE INDEX IF NOT EXISTS idx_mcp_connections_session_id ON mcp_connections(session_id);
CREATE INDEX IF NOT EXISTS idx_mcp_connections_created_at ON mcp_connections(created_at DESC);

-- ------------------------------------------------------------
-- 6. Updated At Triggers
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_conversations_updated_at ON conversations;
CREATE TRIGGER trg_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_mcp_connections_updated_at ON mcp_connections;
CREATE TRIGGER trg_mcp_connections_updated_at
    BEFORE UPDATE ON mcp_connections
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- ------------------------------------------------------------
-- 7. Row Level Security (RLS)
-- ------------------------------------------------------------
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE mcp_connections ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if any
DROP POLICY IF EXISTS users_all_service ON users;
DROP POLICY IF EXISTS conversations_all_service ON conversations;
DROP POLICY IF EXISTS mcp_connections_all_service ON mcp_connections;

-- Service role bypass policies for backend operations
CREATE POLICY users_all_service ON users
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY conversations_all_service ON conversations
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY mcp_connections_all_service ON mcp_connections
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
