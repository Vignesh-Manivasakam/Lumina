"use client";

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { AlertCircle } from 'lucide-react';

import {
  Conversation,
  DocumentItem,
  FileAttachment,
  MCPConnection,
  Message,
  AgentTraceStep,
  ThinkingEvent,
} from '../lib/types';
import {
  streamChat,
  uploadFile,
  getDocuments,
  getIngestStatus,
  getOrCreateSessionUUID,
  cleanupSession,
  listConversations,
  createConversation,
  listMCPConnections,
  getSessionHistory,
} from '../lib/api';

import { Header } from '../components/Header';
import { Sidebar } from '../components/Sidebar';
import { MessageList } from '../components/MessageList';
import { ChatInput } from '../components/ChatInput';
import { MCPModal } from '../components/MCPModal';

export default function Home() {
  const [sessionUUID, setSessionUUID] = useState<string>('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputQuery, setInputQuery] = useState<string>('');
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [attachment, setAttachment] = useState<FileAttachment | null>(null);
  const [webSearchMode, setWebSearchMode] = useState<'auto' | 'always' | 'off'>('auto');
  const [selectedModel, setSelectedModel] = useState<string>('gemini-flash-latest');
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversation, setActiveConversation] = useState<Conversation | null>(null);
  const [mcpConnections, setMcpConnections] = useState<MCPConnection[]>([]);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(false);
  const [mcpModalOpen, setMcpModalOpen] = useState<boolean>(false);
  const [darkMode, setDarkMode] = useState<boolean>(false);
  const [lifetimeQueries, setLifetimeQueries] = useState<number>(0);
  const [tokensUsed, setTokensUsed] = useState<number>(0);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const loadDocuments = useCallback(async () => {
    try {
      const docs = await getDocuments();
      setDocuments(docs || []);
    } catch (err) {
      console.warn('Failed to load documents:', err);
    }
  }, []);

  const loadConversations = useCallback(async (sessionId: string) => {
    try {
      const list = await listConversations(sessionId);
      setConversations(list || []);
    } catch (err) {
      console.warn('Failed to load conversations:', err);
    }
  }, []);

  const loadMCPConnections = useCallback(async () => {
    try {
      const conns = await listMCPConnections();
      setMcpConnections(conns || []);
    } catch (err) {
      console.warn('Failed to load MCP connections:', err);
    }
  }, []);

  useEffect(() => {
    const uuid = getOrCreateSessionUUID();
    setSessionUUID(uuid);
    loadDocuments();
    loadConversations(uuid);
    loadMCPConnections();

    // Load persisted queries count with proactive sanitization
    const savedQueries = localStorage.getItem('lumina_queries_run');
    if (savedQueries) {
      const parsed = parseInt(savedQueries, 10);
      if (isNaN(parsed) || parsed < 0) {
        localStorage.setItem('lumina_queries_run', '0');
        setLifetimeQueries(0);
      } else {
        setLifetimeQueries(parsed);
      }
    } else {
      localStorage.setItem('lumina_queries_run', '0');
      setLifetimeQueries(0);
    }

    // Load persisted tokens used
    const savedTokens = localStorage.getItem('lumina_tokens_used');
    if (savedTokens) {
      const parsed = parseInt(savedTokens, 10);
      setTokensUsed(isNaN(parsed) || parsed < 0 ? 12450 : parsed);
    } else {
      localStorage.setItem('lumina_tokens_used', '12450');
      setTokensUsed(12450);
    }

    const savedTheme = localStorage.getItem('lumina_dark_mode');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = savedTheme !== null ? savedTheme === 'true' : prefersDark;
    setDarkMode(isDark);
    document.documentElement.classList.toggle('dark', isDark);
  }, [loadDocuments, loadConversations, loadMCPConnections]);

  const toggleDarkMode = () => {
    setDarkMode((prev) => {
      const next = !prev;
      localStorage.setItem('lumina_dark_mode', String(next));
      document.documentElement.classList.toggle('dark', next);
      return next;
    });
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, isStreaming]);

  const handleFileUpload = async (file: File) => {
    setIsUploading(true);
    setErrorBanner(null);
    try {
      const res = await uploadFile(file, 'General');
      await loadDocuments();

      if (res?.doc_id) {
        let attempts = 0;
        const pollInterval = setInterval(async () => {
          attempts += 1;
          try {
            const statusRes = await getIngestStatus(res.doc_id);
            if (statusRes.status === 'ready' || statusRes.status === 'failed' || attempts > 20) {
              clearInterval(pollInterval);
              await loadDocuments();
            }
          } catch {
            clearInterval(pollInterval);
          }
        }, 1200);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setErrorBanner(`Upload failed: ${message}`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDeleteDocument = async (id: string) => {
    setDocuments((prev) => prev.filter((d) => d.id !== id));
    await loadDocuments();
  };

  const handleSendMessage = async (promptOverride?: string) => {
    const queryToSend = promptOverride ?? inputQuery;
    const currentAttachment = attachment;
    const imageToSend = (currentAttachment?.type === 'image' && currentAttachment.b64)
      ? currentAttachment.b64
      : selectedImage || undefined;

    if (!queryToSend.trim() && !currentAttachment && !imageToSend) return;

    // Increment queries run counter safely
    setLifetimeQueries((prev) => {
      const next = Math.max(0, prev) + 1;
      localStorage.setItem('lumina_queries_run', String(next));
      return next;
    });

    const userMessage: Message = {
      id: `user-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      role: 'user',
      content: queryToSend,
      image_b64: imageToSend,
      attachment: currentAttachment || undefined,
    };

    setMessages((prev) => [...prev, userMessage]);
    const historySnapshot = messages;

    setInputQuery('');
    setSelectedImage(null);
    setAttachment(null);
    setIsStreaming(true);
    setErrorBanner(null);

    const assistantId = `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setMessages((prev) => [
      ...prev,
      {
        id: assistantId,
        role: 'assistant',
        content: '',
        sources: [],
        agentTrace: [],
        thinking: [],
      },
    ]);

    await streamChat(queryToSend, historySnapshot, imageToSend, {
      model: selectedModel,
      webSearchMode: webSearchMode,
      attachment: currentAttachment || undefined,
      onChunk: (token) => {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantId ? { ...msg, content: msg.content + token } : msg,
          ),
        );
      },
      onSources: (sources) => {
        setMessages((prev) =>
          prev.map((msg) => (msg.id === assistantId ? { ...msg, sources } : msg)),
        );
      },
      onAgentStatus: (event) => {
        const step: AgentTraceStep = { ...event, timestamp: Date.now() };
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantId
              ? { ...msg, agentTrace: [...(msg.agentTrace || []), step] }
              : msg,
          ),
        );
      },
      onThinking: (event) => {
        const note: ThinkingEvent = { ...event, timestamp: Date.now() };
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantId
              ? { ...msg, thinking: [...(msg.thinking || []), note] }
              : msg,
          ),
        );
      },
      onImageResult: (img) => {
        setMessages((prev) =>
          prev.map((msg) => (msg.id === assistantId ? { ...msg, image_result: img } : msg)),
        );
      },
      onWebResults: (results) => {
        setMessages((prev) =>
          prev.map((msg) => (msg.id === assistantId ? { ...msg, web_results: results } : msg)),
        );
      },
      onToolResult: (tool) => {
        setMessages((prev) =>
          prev.map((msg) => (msg.id === assistantId ? { ...msg, tool_result: tool } : msg)),
        );
      },
      onError: (err) => {
        setErrorBanner(err);
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantId
              ? { ...msg, content: msg.content || `⚠️ Error: ${err}` }
              : msg,
          ),
        );
      },
    });

    setIsStreaming(false);

    // Calculate approximate tokens consumed (prompt + retrieval context + generation)
    const estimatedQueryTokens = Math.max(35, Math.round(queryToSend.length / 4)) + 420;
    setTokensUsed((prev) => {
      const next = prev + estimatedQueryTokens;
      localStorage.setItem('lumina_tokens_used', String(next));
      return next;
    });
  };

  const handleSelectConversation = async (conv: Conversation) => {
    setActiveConversation(conv);
    try {
      const history = await getSessionHistory(conv.id);
      if (history && history.length > 0) {
        const formatted: Message[] = history.map((item: any, idx: number) => ({
          id: item.id || `hist-${idx}`,
          role: item.role === 'user' ? 'user' : 'assistant',
          content: item.content || '',
          sources: item.sources || [],
          agentTrace: item.agentTrace || [],
          thinking: item.thinking || [],
          image_result: item.image_result,
          web_results: item.web_results,
          tool_result: item.tool_result,
          attachment: item.attachment,
        }));
        setMessages(formatted);
      } else {
        setMessages([]);
      }
    } catch {
      setMessages([]);
    }
  };

  const handleNewConversation = async () => {
    try {
      const newConv = await createConversation('New Conversation', sessionUUID);
      setConversations((prev) => [newConv, ...prev]);
      setActiveConversation(newConv);
      setMessages([]);
    } catch {
      setMessages([]);
      setActiveConversation(null);
    }
  };

  const activeQueriesCount = Math.max(0, messages.filter((m) => m.role === 'user').length);
  const totalQueriesRun = Math.max(0, lifetimeQueries, activeQueriesCount);

  return (
    <div className="flex h-screen w-screen workspace-ambient-bg text-slate-900 dark:text-slate-100 font-sans overflow-hidden transition-colors duration-300">
      {/* ─── 1. Left Sidebar Navigation ────────────────────────────── */}
      <Sidebar
        sidebarOpen={sidebarOpen}
        setSidebarOpen={setSidebarOpen}
        documents={documents}
        isUploading={isUploading}
        onFileUpload={handleFileUpload}
        onDeleteDocument={handleDeleteDocument}
        conversations={conversations}
        activeConversation={activeConversation}
        onSelectConversation={handleSelectConversation}
        onNewConversation={handleNewConversation}
        mcpConnections={mcpConnections}
        onOpenMCPModal={() => setMcpModalOpen(true)}
        queriesRunCount={totalQueriesRun}
        tokensUsedCount={tokensUsed}
      />

      {/* ─── 2. Main Research Workspace Area ───────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden relative">
        {/* Top-Right Utility Header: ONLY Dark/Light mode toggle */}
        <Header
          sidebarOpen={sidebarOpen}
          setSidebarOpen={setSidebarOpen}
          activeConversation={activeConversation}
          darkMode={darkMode}
          onToggleDarkMode={toggleDarkMode}
        />

        {/* Workspace Canvas */}
        <main className="flex-1 overflow-y-auto relative flex flex-col justify-between">
          {/* Global Alert / Error Banner */}
          {errorBanner && (
            <div className="mx-6 mt-4 p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-xs flex items-center justify-between animate-fade-in z-10 shrink-0">
              <div className="flex items-center gap-2">
                <AlertCircle size={15} />
                <span>{errorBanner}</span>
              </div>
              <button
                onClick={() => setErrorBanner(null)}
                className="text-xs font-medium text-red-600 dark:text-red-400 hover:underline"
              >
                dismiss
              </button>
            </div>
          )}

          {/* Dynamic Content: Empty Landing State vs. Active Research Conversation */}
          <div className="flex-1 flex flex-col justify-between">
            <div className="flex-1">
              <MessageList
                messages={messages}
                isStreaming={isStreaming}
                messagesEndRef={messagesEndRef as React.RefObject<HTMLDivElement>}
                onSelectPrompt={(p) => handleSendMessage(p)}
              />
            </div>

            {/* Persistent Floating Bottom Composer (No nested double borders) */}
            <div className="sticky bottom-0 z-20 px-4 pt-2 pb-4 sm:pb-6 bg-gradient-to-t from-[#F4F8FD] via-[#F4F8FD]/90 to-transparent dark:from-[#090D16] dark:via-[#090D16]/90">
              <ChatInput
                inputQuery={inputQuery}
                setInputQuery={setInputQuery}
                selectedImage={selectedImage}
                setSelectedImage={setSelectedImage}
                attachment={attachment}
                setAttachment={setAttachment}
                webSearchMode={webSearchMode}
                setWebSearchMode={setWebSearchMode}
                selectedModel={selectedModel}
                setSelectedModel={setSelectedModel}
                onSendMessage={() => handleSendMessage()}
                isStreaming={isStreaming}
                onError={(err) => setErrorBanner(err)}
              />
            </div>
          </div>
        </main>
      </div>

      {/* ─── 3. MCP Hub Modal ──────────────────────────────────────── */}
      <MCPModal
        isOpen={mcpModalOpen}
        onClose={() => setMcpModalOpen(false)}
        connections={mcpConnections}
        onRefreshConnections={loadMCPConnections}
      />
    </div>
  );
}
