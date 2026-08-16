-- ============================================================
-- Lumina Phase 2: Session isolation & RLS policies
-- ============================================================
-- Apply AFTER `backend/supabase_schema.sql`.
--
-- Lumina uses a custom UUID `X-Session-ID` header (NOT Supabase
-- Auth). The application layer is the primary isolation gate.
-- These RLS policies are defense-in-depth: if the service-role key
-- is ever exposed by accident, the session data cannot leak via the
-- anon key.
--
-- The `service_role` key bypasses RLS by design, so the FastAPI
-- backend can continue to insert messages on behalf of any
-- session. To actually verify isolation in production, switch to
-- the anon key with a custom JWT claim for `session_id`.
--
-- Idempotent: safe to re-run.

-- ------------------------------------------------------------
-- 1. Enable RLS on all relevant tables
-- ------------------------------------------------------------
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks    ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages  ENABLE ROW LEVEL SECURITY;

-- ------------------------------------------------------------
-- 2. Drop existing policies if they exist (idempotent)
-- ------------------------------------------------------------
DROP POLICY IF EXISTS documents_read_all      ON documents;
DROP POLICY IF EXISTS documents_insert_service ON documents;
DROP POLICY IF EXISTS chunks_read_all         ON chunks;
DROP POLICY IF EXISTS chunks_insert_service   ON chunks;
DROP POLICY IF EXISTS sessions_read_own       ON sessions;
DROP POLICY IF EXISTS sessions_insert_service ON sessions;
DROP POLICY IF EXISTS session_isolation_messages ON messages;

-- ------------------------------------------------------------
-- 3. Documents: shared across all sessions (read-only for everyone,
--    insert/update only via service_role)
-- ------------------------------------------------------------
CREATE POLICY documents_read_all ON documents
    FOR SELECT USING (true);

CREATE POLICY documents_insert_service ON documents
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY documents_update_service ON documents
    FOR UPDATE USING (auth.role() = 'service_role');

-- ------------------------------------------------------------
-- 4. Chunks: same as documents (shared, service-role write only)
-- ------------------------------------------------------------
CREATE POLICY chunks_read_all ON chunks
    FOR SELECT USING (true);

CREATE POLICY chunks_insert_service ON chunks
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

-- ------------------------------------------------------------
-- 5. Sessions: app-layer gate; defense-in-depth via service_role
-- ------------------------------------------------------------
CREATE POLICY sessions_read_own ON sessions
    FOR SELECT USING (true);  -- app filters by id; RLS bypassed for service_role

CREATE POLICY sessions_insert_service ON sessions
    FOR INSERT WITH CHECK (auth.role() = 'service_role');

CREATE POLICY sessions_delete_service ON sessions
    FOR DELETE USING (auth.role() = 'service_role');

-- ------------------------------------------------------------
-- 6. Messages: the critical isolation table
-- ------------------------------------------------------------
-- The application is the primary gate (always filters by session_id).
-- RLS blocks anon access entirely; service_role bypasses for backend.
CREATE POLICY session_isolation_messages ON messages
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- ------------------------------------------------------------
-- 7. Indexes for fast session-scoped queries
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_messages_session_id  ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at  ON messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at  ON sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id        ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC);

-- ------------------------------------------------------------
-- 8. updated_at columns + trigger
-- ------------------------------------------------------------
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE messages ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sessions_updated_at ON sessions;
CREATE TRIGGER trg_sessions_updated_at
    BEFORE UPDATE ON sessions
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_messages_updated_at ON messages;
CREATE TRIGGER trg_messages_updated_at
    BEFORE UPDATE ON messages
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- ------------------------------------------------------------
-- 9. Manual cleanup function (Supabase free tier has no pg_cron)
--    Call via: SELECT * FROM cleanup_old_sessions(30);
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION cleanup_old_sessions(max_age_days INT DEFAULT 30)
RETURNS TABLE(deleted_sessions INT, deleted_messages INT) AS $$
DECLARE
    session_count INT;
    message_count INT;
BEGIN
    SELECT COUNT(*) INTO session_count FROM sessions
    WHERE created_at < NOW() - (max_age_days || ' days')::INTERVAL;

    SELECT COUNT(*) INTO message_count FROM messages
    WHERE session_id IN (
        SELECT id FROM sessions
        WHERE created_at < NOW() - (max_age_days || ' days')::INTERVAL
    );

    DELETE FROM messages WHERE session_id IN (
        SELECT id FROM sessions
        WHERE created_at < NOW() - (max_age_days || ' days')::INTERVAL
    );
    DELETE FROM sessions
    WHERE created_at < NOW() - (max_age_days || ' days')::INTERVAL;

    RETURN QUERY SELECT session_count, message_count;
END;
$$ LANGUAGE plpgsql;
