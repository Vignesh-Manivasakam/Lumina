-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Document registry
CREATE TABLE IF NOT EXISTS documents (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename     TEXT NOT NULL,
    file_type    TEXT NOT NULL,  -- pdf, docx, pptx, mp3, mp4, etc.
    dept         TEXT,           -- HR, Finance, Policy...
    uploaded_by  TEXT,
    status       TEXT DEFAULT 'pending',  -- pending/processing/ready/failed
    num_chunks   INT,
    storage_path TEXT,           -- Supabase Storage path
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Chunk metadata (searchable by doc, page, modality)
CREATE TABLE IF NOT EXISTS chunks (
    id           TEXT PRIMARY KEY,  -- matches Qdrant point ID
    doc_id       UUID REFERENCES documents(id) ON DELETE CASCADE,
    modality     TEXT NOT NULL,
    page_num     INT,
    timestamp_sec INT,
    text_repr    TEXT NOT NULL,
    has_image    BOOLEAN DEFAULT FALSE,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_modality ON chunks(modality);

-- Chat sessions
CREATE TABLE IF NOT EXISTS sessions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Chat history (for multi-turn context)
CREATE TABLE IF NOT EXISTS messages (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID REFERENCES sessions(id) ON DELETE CASCADE,
    role         TEXT NOT NULL,  -- user / assistant
    content      TEXT NOT NULL,
    image_b64    TEXT,           -- if user sent image
    source_chunks JSONB,         -- retrieved chunk IDs + scores
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);

-- Enable Row Level Security (RLS) for multi-tenant session isolation
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

-- Message Isolation Policy
CREATE POLICY IF NOT EXISTS "session_isolation_messages" ON messages
    FOR ALL USING (session_id = current_setting('request.headers', true)::json->>'x-session-id');

-- Document Isolation Policy
CREATE POLICY IF NOT EXISTS "documents_read_all" ON documents
    FOR SELECT USING (true);

