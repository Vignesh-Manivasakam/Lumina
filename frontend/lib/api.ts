import {
  AgentStatus,
  AgentStatusEvent,
  AgentTraceStep,
  Conversation,
  DocumentItem,
  ImageResult,
  MCPConnection,
  RetrievalInfo,
  Source,
  SSEEvent,
  WebSearchResult,
} from './types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function getOrCreateSessionUUID(): string {
  if (typeof window === 'undefined') return '00000000-0000-4000-8000-000000000000';
  let uuid = localStorage.getItem('lumina_session_uuid');
  if (!uuid) {
    uuid = crypto.randomUUID();
    localStorage.setItem('lumina_session_uuid', uuid);
  }
  return uuid;
}

function getHeaders(extraHeaders: Record<string, string> = {}): Record<string, string> {
  return {
    'X-Session-ID': getOrCreateSessionUUID(),
    ...extraHeaders,
  };
}

export interface StreamChatCallbacks {
  onChunk?: (text: string) => void;
  onSources?: (sources: Source[]) => void;
  onAgentStatus?: (event: AgentStatusEvent) => void;
  onRetrievalInfo?: (info: RetrievalInfo) => void;
  onThinking?: (event: { agent: string; step: number; content: string }) => void;
  onImageResult?: (result: ImageResult) => void;
  onWebResults?: (results: WebSearchResult[]) => void;
  onToolResult?: (result: any) => void;
  onVoiceAudio?: (audioB64: string, format?: string) => void;
  onError?: (err: string) => void;
  sessionId?: string;
  webSearchMode?: 'auto' | 'always' | 'off';
  model?: string;
  attachment?: {
    name: string;
    type: string;
    content?: string;
    b64?: string;
  };
  signal?: AbortSignal;
}

export async function streamChat(
  query: string,
  history: { role: string; content: string }[],
  imageB64: string | undefined,
  callbacks: StreamChatCallbacks,
): Promise<void> {
  const {
    onChunk,
    onSources,
    onAgentStatus,
    onRetrievalInfo,
    onThinking,
    onImageResult,
    onWebResults,
    onToolResult,
    onVoiceAudio,
    onError,
    sessionId,
    webSearchMode,
    model,
    attachment,
    signal,
  } = callbacks;

  try {
    const formattedHistory = history.map((msg) => ({
      role: msg.role,
      content: msg.content,
    }));

    const response = await fetch(`${API_URL}/api/chat`, {
      method: 'POST',
      headers: getHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        query,
        history: formattedHistory,
        image_b64: imageB64 || attachment?.b64,
        attached_file_name: attachment?.name,
        attached_file_content: attachment?.content,
        attached_file_type: attachment?.type,
        session_id: sessionId || getOrCreateSessionUUID(),
        web_search_mode: webSearchMode || 'auto',
        model: model || undefined,
      }),
      signal,
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('Response body reader not available');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.trim() || !line.startsWith('data: ')) continue;
        const dataStr = line.slice(6).trim();
        if (dataStr === '[DONE]') return;

        let parsed: SSEEvent;
        try {
          parsed = JSON.parse(dataStr);
        } catch {
          console.error('Error parsing SSE line:', dataStr);
          continue;
        }

        switch (parsed.type) {
          case 'text':
            onChunk?.(parsed.content);
            break;
          case 'sources':
            onSources?.(parsed.sources);
            break;
          case 'agent_status':
            onAgentStatus?.({
              agent: parsed.agent,
              status: parsed.status,
              message: parsed.message,
              step: parsed.step,
            });
            break;
          case 'thinking':
            onThinking?.({
              agent: parsed.agent,
              step: parsed.step,
              content: parsed.content,
            });
            break;
          case 'retrieval_info':
            onRetrievalInfo?.(parsed.info);
            break;
          case 'image_result':
            onImageResult?.({
              image_b64: parsed.image_b64,
              prompt: parsed.prompt,
              refined_prompt: parsed.refined_prompt,
            });
            break;
          case 'web_results':
            onWebResults?.(parsed.results);
            break;
          case 'tool_result':
            onToolResult?.(parsed.result);
            break;
          case 'voice_audio':
            onVoiceAudio?.(parsed.audio_b64, parsed.format);
            break;
          case 'error':
            onError?.(parsed.content);
            break;
          case 'done':
          default:
            break;
        }
      }
    }
  } catch (error: unknown) {
    const message =
      error instanceof Error ? error.message : 'Failed to communicate with API server';
    onError?.(message);
  }
}

// ----- Ingestion & Documents -----------------------------------------------

export async function uploadFile(
  file: File,
  dept: string = 'General',
): Promise<{ doc_id: string; status: string }> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('dept', dept);

  const response = await fetch(`${API_URL}/api/ingest`, {
    method: 'POST',
    headers: getHeaders(),
    body: formData,
  });

  if (!response.ok) {
    const errorDetails = await response.json().catch(() => ({ detail: 'Failed to upload' }));
    throw new Error(errorDetails.detail || 'Upload failed');
  }

  return response.json();
}

export async function getIngestStatus(docId: string): Promise<{ doc_id: string; status: string }> {
  const response = await fetch(`${API_URL}/api/ingest/${docId}/status`, {
    headers: getHeaders(),
  });
  if (!response.ok) throw new Error('Failed to fetch ingestion status');
  return response.json();
}

export async function getDocuments(): Promise<DocumentItem[]> {
  const response = await fetch(`${API_URL}/api/documents`, {
    headers: getHeaders(),
  });
  if (!response.ok) throw new Error('Failed to fetch documents');
  return response.json();
}

export async function deleteDocument(docId: string): Promise<{ status: string }> {
  const response = await fetch(`${API_URL}/api/documents/${docId}`, {
    method: 'DELETE',
    headers: getHeaders(),
  });
  if (!response.ok) throw new Error('Failed to delete document');
  return response.json();
}

// ----- Sessions -------------------------------------------------------------

export async function createSession(): Promise<{ id: string }> {
  const response = await fetch(`${API_URL}/api/sessions`, {
    method: 'POST',
    headers: getHeaders(),
  });
  if (!response.ok) throw new Error('Failed to create session');
  return response.json();
}

export async function getSessionHistory(sessionId: string): Promise<any[]> {
  const response = await fetch(`${API_URL}/api/sessions/${sessionId}/history`, {
    headers: getHeaders(),
  });
  if (!response.ok) throw new Error('Failed to fetch session history');
  return response.json();
}

export async function cleanupSession(sessionId: string): Promise<any> {
  const response = await fetch(`${API_URL}/api/sessions/${sessionId}/cleanup`, {
    method: 'POST',
    headers: getHeaders(),
  });
  if (!response.ok) throw new Error('Failed to clean session');
  return response.json();
}

export async function deleteSession(sessionId: string): Promise<any> {
  const response = await fetch(`${API_URL}/api/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: getHeaders(),
  });
  if (!response.ok) throw new Error('Failed to delete session');
  return response.json();
}

// ----- Conversations API ---------------------------------------------------

export async function listConversations(
  sessionId?: string,
  limit: number = 50,
): Promise<Conversation[]> {
  const effectiveSession = sessionId || getOrCreateSessionUUID();
  const url = new URL(`${API_URL}/api/conversations`);
  url.searchParams.set('session_id', effectiveSession);
  url.searchParams.set('limit', String(limit));

  const response = await fetch(url.toString(), {
    headers: getHeaders(),
  });
  if (!response.ok) throw new Error('Failed to list conversations');
  return response.json();
}

export async function createConversation(
  title: string = 'New Conversation',
  sessionId?: string,
  metadata?: Record<string, any>,
): Promise<Conversation> {
  const effectiveSession = sessionId || getOrCreateSessionUUID();
  const response = await fetch(`${API_URL}/api/conversations`, {
    method: 'POST',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      title,
      session_id: effectiveSession,
      metadata,
    }),
  });
  if (!response.ok) throw new Error('Failed to create conversation');
  return response.json();
}

export async function getConversation(conversationId: string): Promise<Conversation> {
  const response = await fetch(`${API_URL}/api/conversations/${conversationId}`, {
    headers: getHeaders(),
  });
  if (!response.ok) throw new Error('Failed to get conversation details');
  return response.json();
}

export async function updateConversation(
  conversationId: string,
  data: { title?: string; archived?: boolean; metadata?: Record<string, any> },
): Promise<Conversation> {
  const response = await fetch(`${API_URL}/api/conversations/${conversationId}`, {
    method: 'PATCH',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to update conversation');
  return response.json();
}

// ----- MCP Connections API -------------------------------------------------

export async function listMCPConnections(
  scope?: string,
  sessionId?: string,
): Promise<MCPConnection[]> {
  const url = new URL(`${API_URL}/api/mcp/connections`);
  if (scope) url.searchParams.set('scope', scope);
  if (sessionId) url.searchParams.set('session_id', sessionId);

  const response = await fetch(url.toString(), {
    headers: getHeaders(),
  });
  if (!response.ok) throw new Error('Failed to list MCP connections');
  return response.json();
}

export async function registerMCPConnection(data: {
  name: string;
  endpoint_url: string;
  transport?: string;
  scope?: string;
  session_id?: string;
}): Promise<MCPConnection> {
  const response = await fetch(`${API_URL}/api/mcp/connections`, {
    method: 'POST',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Failed to register MCP server' }));
    throw new Error(err.detail || 'Failed to register MCP server');
  }
  return response.json();
}

export async function deleteMCPConnection(connectionId: string): Promise<any> {
  const response = await fetch(`${API_URL}/api/mcp/connections/${connectionId}`, {
    method: 'DELETE',
    headers: getHeaders(),
  });
  if (!response.ok) throw new Error('Failed to delete MCP connection');
  return response.json();
}

// ----- Voice STT / TTS API -------------------------------------------------

export async function transcribeAudio(
  fileOrBlob: Blob | File,
  format?: string,
): Promise<{ text: string }> {
  const formData = new FormData();
  formData.append('audio', fileOrBlob, 'recording.wav');
  if (format) formData.append('format', format);

  const response = await fetch(`${API_URL}/api/voice/transcribe`, {
    method: 'POST',
    headers: getHeaders(),
    body: formData,
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Transcription failed' }));
    throw new Error(err.detail || 'Transcription failed');
  }
  return response.json();
}

export async function synthesizeSpeech(
  text: string,
  voice: string = 'en-US',
): Promise<Blob> {
  const response = await fetch(`${API_URL}/api/voice/synthesize`, {
    method: 'POST',
    headers: getHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ text, voice }),
  });

  if (!response.ok) {
    throw new Error(`Speech synthesis failed with status ${response.status}`);
  }
  return response.blob();
}
