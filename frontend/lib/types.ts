export interface FileAttachment {
  name: string;
  type: string; // 'image' | 'pdf' | 'docx' | 'text' | 'sheet' | 'code' | 'other'
  size?: number;
  content?: string; // extracted text representation
  b64?: string; // base64 representation if image or binary
  mimeType?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  image_b64?: string;
  attachment?: FileAttachment;
  sources?: Source[];
  /** Live agent trace captured during streaming. */
  agentTrace?: AgentTraceStep[];
  /** Per-agent thinking notes captured during streaming. */
  thinking?: ThinkingEvent[];
  /** AI-generated image result */
  image_result?: ImageResult;
  /** Web search results from tools */
  web_results?: WebSearchResult[];
  /** Custom tool execution output */
  tool_result?: any;
  /** Synthesized or streamed audio (base64 or URL) */
  audio_url?: string;
  /** Timestamp of creation */
  created_at?: string;
}

export interface Source {
  chunk_id: string;
  modality: string;
  text_repr: string;
  page_num?: number;
  score?: number;
  /** Post-rerank relevance score (preferred over score for display). */
  rerank_score?: number;
  /** Optional original chunk text without the contextual header prefix. */
  original_text?: string;
  /** Optional contextual header prepended to text_repr before embedding. */
  contextual_header?: string;
  /** Document title for citation display (from metadata.title). */
  doc_title?: string;
}

// ---------------------------------------------------------------
// Phase 4: agent streaming status types
// ---------------------------------------------------------------

export type AgentName = 'router' | 'retriever' | 'grader' | 'rewriter' | 'generator';

export type AgentStatus = 'pending' | 'active' | 'complete' | 'skipped';

export interface AgentStatusEvent {
  agent: AgentName;
  status: AgentStatus;
  /** Optional message attached to the status (e.g. "retrieved 12 chunks"). */
  message?: string;
  /** Index in the pipeline sequence — used by the trace bar to fill segments. */
  step: number;
}

export interface AgentTraceStep extends AgentStatusEvent {
  /** Server-side timestamp (ms since epoch). */
  timestamp: number;
}

export interface RetrievalInfo {
  /** Number of child chunks retrieved before reranking. */
  retrieved_count: number;
  /** Number of chunks kept after reranking. */
  reranked_count: number;
  /** Total time spent in retrieval (ms). */
  retrieval_ms: number;
  /** Departments or filters that were applied. */
  filters?: Record<string, string>;
  /** Did the grader decide retrieval was sufficient? */
  is_sufficient?: boolean;
}

// ---------------------------------------------------------------
// New Types: Conversations, MCP, Skills, Document
// ---------------------------------------------------------------

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at?: string;
  is_archived?: boolean;
  session_id?: string;
  metadata?: Record<string, any>;
}

export interface MCPConnection {
  id: string;
  name: string;
  endpoint_url: string;
  transport: 'sse' | 'stdio';
  scope: 'workspace' | 'session';
  tools_schema?: any[];
  tools?: {
    name: string;
    description: string;
    input_schema?: Record<string, any>;
  }[];
  is_active?: boolean;
  created_at?: string;
}

export interface ImageResult {
  image_b64: string;
  prompt: string;
  refined_prompt: string;
}

export interface WebSearchResult {
  title: string;
  url: string;
  content: string;
  score: number;
}

export interface DocumentItem {
  id: string;
  filename: string;
  file_type?: string;
  dept?: string;
  num_chunks?: number;
  num_pages?: number;
  created_at?: string;
  status?: string;
}

// ---------------------------------------------------------------
// SSE wire format
// ---------------------------------------------------------------

export interface ThinkingEvent {
  agent: AgentName | string;
  step: number;
  content: string;
  timestamp?: number;
}

export interface UsageInfo {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  latency_ms?: number;
  model?: string;
  route?: string;
}

export type SSEEvent =
  | { type: 'text'; content: string }
  | { type: 'sources'; sources: Source[] }
  | { type: 'agent_status'; agent: AgentName; status: AgentStatus; message?: string; step: number }
  | { type: 'retrieval_info'; info: RetrievalInfo }
  | { type: 'thinking'; agent: AgentName | string; step: number; content: string }
  | { type: 'image_result'; image_b64: string; prompt: string; refined_prompt: string }
  | { type: 'web_results'; results: WebSearchResult[] }
  | { type: 'tool_result'; result: any }
  | { type: 'voice_audio'; audio_b64: string; format?: string }
  | { type: 'usage_info'; usage: UsageInfo }
  | { type: 'error'; content: string }
  | { type: 'done' };

// ---------------------------------------------------------------
// Dynamic Skills Interface
// ---------------------------------------------------------------

export interface SkillItem {
  name: string;
  category: string;
  title?: string;
  description: string;
  triggers?: string[];
  tags?: string[];
  is_custom?: boolean;
  session_id?: string | null;
  confidence_threshold?: number;
  prompt?: string;
  parameters_schema?: Record<string, any>;
}

