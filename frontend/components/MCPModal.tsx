"use client";

import React, { useState, useEffect } from 'react';
import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronDown,
  Code,
  Copy,
  Cpu,
  Globe,
  Layers,
  Loader2,
  Plus,
  Radio,
  Server,
  Terminal,
  Trash2,
  Wrench,
  X,
  Zap,
} from 'lucide-react';
import clsx from 'clsx';
import { MCPConnection } from '../lib/types';
import { deleteMCPConnection, registerMCPConnection } from '../lib/api';

interface MCPModalProps {
  isOpen: boolean;
  onClose: () => void;
  connections: MCPConnection[];
  onRefreshConnections: () => void;
}

type ModalTab = 'server_mode' | 'client_mode';
type EnvMode = 'local' | 'deployed';

export function MCPModal({
  isOpen,
  onClose,
  connections,
  onRefreshConnections,
}: MCPModalProps) {
  const [activeTab, setActiveTab] = useState<ModalTab>('server_mode');
  const [envMode, setEnvMode] = useState<EnvMode>('local');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const [expandedServers, setExpandedServers] = useState<Record<string, boolean>>({});

  // Form states for registering external tools
  const [name, setName] = useState('');
  const [endpointUrl, setEndpointUrl] = useState('');
  const [transport, setTransport] = useState<'sse' | 'stdio'>('sse');
  const [scope, setScope] = useState<'workspace' | 'session'>('workspace');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Dynamic API host detection
  const [currentOrigin, setCurrentOrigin] = useState('http://localhost:8000');
  const [deployedDomain, setDeployedDomain] = useState('https://api.yourdomain.com');

  useEffect(() => {
    if (typeof window !== 'undefined') {
      const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || (isLocal ? 'http://localhost:8000' : window.location.origin);
      setCurrentOrigin(apiUrl);
      if (!isLocal) {
        setDeployedDomain(window.location.origin);
      }
    }
  }, []);

  // Expand all servers by default when connections change
  useEffect(() => {
    if (connections && connections.length > 0) {
      const initial: Record<string, boolean> = {};
      connections.forEach((c) => {
        initial[c.id] = true;
      });
      setExpandedServers(initial);
    }
  }, [connections]);

  if (!isOpen) return null;

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const toggleServerExpand = (id: string) => {
    setExpandedServers((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  const effectiveMcpUrl = envMode === 'local' ? `${currentOrigin}/mcp` : `${deployedDomain}/mcp`;

  const claudeDesktopConfig = envMode === 'local'
    ? `{
  "mcpServers": {
    "lumina-rag": {
      "command": "python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "f:/AI/Lumina/backend"
    }
  }
}`
    : `{
  "mcpServers": {
    "lumina-rag": {
      "url": "${deployedDomain}/mcp"
    }
  }
}`;

  const cursorMcpConfig = `{
  "mcpServers": {
    "lumina-rag": {
      "url": "${effectiveMcpUrl}"
    }
  }
}`;

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !endpointUrl.trim()) {
      setErrorMsg('Server name and endpoint URL are required');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      await registerMCPConnection({
        name: name.trim(),
        endpoint_url: endpointUrl.trim(),
        transport,
        scope,
      });
      setSuccessMsg(`Successfully registered ${name}!`);
      setName('');
      setEndpointUrl('');
      onRefreshConnections();
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setErrorMsg(`Registration failed: ${message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (connId: string) => {
    try {
      await deleteMCPConnection(connId);
      onRefreshConnections();
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setErrorMsg(`Failed to delete connection: ${message}`);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-800 rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden animate-fade-up"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-[#EDF3FA] dark:border-slate-800 flex items-center justify-between bg-[#F9FBFE] dark:bg-slate-900/90">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-lumina-50 dark:bg-lumina-950/50 flex items-center justify-center text-lumina-600 shadow-2xs">
              <Cpu size={20} />
            </div>
            <div>
              <h3 className="font-sans text-base font-semibold text-slate-900 dark:text-white">
                Model Context Protocol (MCP) Hub
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Expose Lumina to other AI or connect external tools into Lumina
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            aria-label="Close modal"
          >
            <X size={18} />
          </button>
        </div>

        {/* Tab navigation */}
        <div className="flex border-b border-[#EDF3FA] dark:border-slate-800 bg-white dark:bg-slate-900 px-6 pt-2 gap-4">
          <button
            onClick={() => setActiveTab('server_mode')}
            className={`pb-3 px-2 text-xs font-semibold border-b-2 flex items-center gap-2 transition-colors ${
              activeTab === 'server_mode'
                ? 'border-lumina-600 text-lumina-600'
                : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <Radio size={14} />
            <span>Expose Lumina to Other AI (Claude / Cursor)</span>
          </button>

          <button
            onClick={() => setActiveTab('client_mode')}
            className={`pb-3 px-2 text-xs font-semibold border-b-2 flex items-center gap-2 transition-colors ${
              activeTab === 'client_mode'
                ? 'border-lumina-600 text-lumina-600'
                : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <Layers size={14} />
            <span>Connect External Tools to Lumina</span>
            {connections.length > 0 && (
              <span className="px-1.5 py-0.5 bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 rounded text-[10px] font-mono">
                {connections.length}
              </span>
            )}
          </button>
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* TAB 1: SERVER MODE (Lumina as MCP Server) */}
          {activeTab === 'server_mode' && (
            <div className="space-y-5">
              <div className="p-4 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-xl text-xs space-y-1">
                <p className="font-semibold text-emerald-900 dark:text-emerald-200 flex items-center gap-1.5">
                  <CheckCircle2 size={15} className="text-emerald-600 dark:text-emerald-400" />
                  <span>Lumina RAG Server is Live & Ready</span>
                </p>
                <p className="text-emerald-800 dark:text-emerald-300 leading-relaxed">
                  Any AI coding assistant can search, retrieve, and cite your Lumina document knowledge base using the open Model Context Protocol.
                </p>
              </div>

              {/* Environment Selector: Localhost vs Deployed */}
              <div className="p-3.5 bg-slate-50 dark:bg-slate-800/40 rounded-xl border border-slate-200 dark:border-slate-800 flex items-center justify-between flex-wrap gap-2">
                <div>
                  <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                    Configuration Target Environment
                  </p>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400">
                    {envMode === 'local'
                      ? 'Targeting local development on this machine (port 8000)'
                      : 'Targeting your deployed public URL in production'}
                  </p>
                </div>
                <div className="flex items-center gap-1 p-1 bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 text-xs">
                  <button
                    type="button"
                    onClick={() => setEnvMode('local')}
                    className={clsx(
                      'px-2.5 py-1 rounded-md font-medium transition-colors flex items-center gap-1',
                      envMode === 'local'
                        ? 'bg-lumina-600 text-white font-semibold shadow-2xs'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900',
                    )}
                  >
                    <Terminal size={12} />
                    Local Dev
                  </button>
                  <button
                    type="button"
                    onClick={() => setEnvMode('deployed')}
                    className={clsx(
                      'px-2.5 py-1 rounded-md font-medium transition-colors flex items-center gap-1',
                      envMode === 'deployed'
                        ? 'bg-lumina-600 text-white font-semibold shadow-2xs'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900',
                    )}
                  >
                    <Globe size={12} />
                    Deployed
                  </button>
                </div>
              </div>

              {/* Deployed URL Input (when Deployed selected) */}
              {envMode === 'deployed' && (
                <div className="p-3.5 bg-amber-50/70 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/50 rounded-xl text-xs space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="font-semibold text-amber-900 dark:text-amber-200">
                      Your Deployed Backend URL:
                    </label>
                    <span className="text-[10px] font-mono text-amber-700 dark:text-amber-300">
                      Render / Railway / Fly / VPS
                    </span>
                  </div>
                  <input
                    type="text"
                    value={deployedDomain}
                    onChange={(e) => setDeployedDomain(e.target.value)}
                    placeholder="https://lumina-backend.onrender.com"
                    className="w-full bg-white dark:bg-slate-900 border border-amber-300 dark:border-amber-800 rounded-lg px-3 py-1.5 text-xs text-slate-900 dark:text-white font-mono focus:outline-none focus:ring-1 focus:ring-amber-500"
                  />
                  <p className="text-[11px] text-amber-800/80 dark:text-amber-300/80 leading-relaxed">
                    💡 When you deploy your backend to the cloud, AI clients (like Cursor or remote agent runners) connect over HTTPS to <code className="font-mono bg-amber-100 dark:bg-amber-900/50 px-1 py-0.5 rounded">{deployedDomain}/mcp</code> instead of localhost.
                  </p>
                </div>
              )}

              {/* Exposed Native MCP Tools */}
              <div className="space-y-2">
                <h4 className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                  Exposed MCP Tools
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="p-3.5 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-[#EDF3FA] dark:border-slate-800 text-xs">
                    <div className="flex items-center gap-1.5 font-mono font-semibold text-lumina-600 dark:text-lumina-400">
                      <Wrench size={13} />
                      <span>query_knowledge_base</span>
                    </div>
                    <p className="text-[11px] text-slate-600 dark:text-slate-400 mt-1">
                      Runs hybrid dense+BM25 search & reranking across all indexed passages.
                    </p>
                  </div>
                  <div className="p-3.5 bg-slate-50 dark:bg-slate-800/60 rounded-xl border border-[#EDF3FA] dark:border-slate-800 text-xs">
                    <div className="flex items-center gap-1.5 font-mono font-semibold text-lumina-600 dark:text-lumina-400">
                      <Wrench size={13} />
                      <span>list_documents</span>
                    </div>
                    <p className="text-[11px] text-slate-600 dark:text-slate-400 mt-1">
                      Returns titles, chunk counts, and metadata for all holdings in the library.
                    </p>
                  </div>
                </div>
              </div>

              {/* Cursor / Windsurf Configuration */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                    <Code size={14} className="text-lumina-600" />
                    <span>Cursor / Windsurf Config (`.cursor/mcp.json`)</span>
                  </h4>
                  <button
                    onClick={() => copyToClipboard(cursorMcpConfig, 'cursor')}
                    className="text-xs font-mono text-lumina-600 hover:text-lumina-700 flex items-center gap-1 font-medium"
                  >
                    {copiedKey === 'cursor' ? <Check size={13} /> : <Copy size={13} />}
                    <span>{copiedKey === 'cursor' ? 'Copied' : 'Copy JSON'}</span>
                  </button>
                </div>
                <pre className="p-3.5 bg-slate-950 text-slate-200 text-xs font-mono rounded-xl overflow-x-auto border border-slate-800">
                  {cursorMcpConfig}
                </pre>
              </div>

              {/* Claude Desktop Configuration */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                    <Code size={14} className="text-lumina-600" />
                    <span>Claude Desktop (`claude_desktop_config.json`)</span>
                  </h4>
                  <button
                    onClick={() => copyToClipboard(claudeDesktopConfig, 'claude')}
                    className="text-xs font-mono text-lumina-600 hover:text-lumina-700 flex items-center gap-1 font-medium"
                  >
                    {copiedKey === 'claude' ? <Check size={13} /> : <Copy size={13} />}
                    <span>{copiedKey === 'claude' ? 'Copied' : 'Copy JSON'}</span>
                  </button>
                </div>
                <pre className="p-3.5 bg-slate-950 text-slate-200 text-xs font-mono rounded-xl overflow-x-auto border border-slate-800">
                  {claudeDesktopConfig}
                </pre>
              </div>
            </div>
          )}

          {/* TAB 2: CLIENT MODE (External Tools Connected to Lumina) */}
          {activeTab === 'client_mode' && (
            <div className="space-y-6">
              {/* Registration Form */}
              <form onSubmit={handleRegister} className="space-y-4 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-[#EDF3FA] dark:border-slate-800">
                <div className="flex items-center justify-between">
                  <h4 className="font-sans font-semibold text-sm text-slate-900 dark:text-white">
                    Add External Tool Server
                  </h4>
                  <span className="text-[10px] font-mono text-slate-400">
                    Auto-discovers tools upon connect
                  </span>
                </div>

                {errorMsg && (
                  <div className="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-lg text-xs text-red-700 dark:text-red-300 flex items-center gap-2">
                    <AlertCircle size={14} className="shrink-0" />
                    <span>{errorMsg}</span>
                  </div>
                )}

                {successMsg && (
                  <div className="p-3 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-lg text-xs text-emerald-700 dark:text-emerald-300 flex items-center gap-2">
                    <CheckCircle2 size={14} className="shrink-0" />
                    <span>{successMsg}</span>
                  </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                      Server Name
                    </label>
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="e.g. GitHub, Postgres DB, Weather"
                      className="w-full bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:border-lumina-600 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                      Endpoint URL
                    </label>
                    <input
                      type="text"
                      value={endpointUrl}
                      onChange={(e) => setEndpointUrl(e.target.value)}
                      placeholder="http://localhost:8000/mcp or https://.../sse"
                      className="w-full bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-white focus:border-lumina-600 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between pt-2">
                  <div className="flex items-center gap-3">
                    <label className="text-xs font-medium text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                      <span>Transport:</span>
                      <select
                        value={transport}
                        onChange={(e) => setTransport(e.target.value as 'sse' | 'stdio')}
                        className="bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-700 rounded-lg px-2.5 py-1 text-xs text-slate-900 dark:text-white outline-none"
                      >
                        <option value="sse">SSE (HTTP/HTTPS)</option>
                        <option value="stdio">stdio (Local Process)</option>
                      </select>
                    </label>
                  </div>

                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="flex items-center gap-1.5 py-2 px-4 bg-lumina-600 hover:bg-lumina-700 text-white rounded-xl text-xs font-semibold disabled:opacity-50 transition-colors shadow-sm cursor-pointer"
                  >
                    {isSubmitting ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                    <span>Register Server & Discover Tools</span>
                  </button>
                </div>
              </form>

              {/* Connected Tool Servers & Exposed Tools Catalog */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                    Connected Servers & Discovered Tools ({connections.length})
                  </h4>
                  <span className="text-[10px] text-slate-400 font-mono">
                    {connections.reduce((acc, c) => acc + ((c.tools?.length || c.tools_schema?.length) || 0), 0)} tools callable
                  </span>
                </div>

                {connections.length === 0 ? (
                  <div className="text-center py-6 px-4 rounded-xl border border-dashed border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50">
                    <Cpu size={24} className="mx-auto text-slate-400 mb-2 opacity-60" />
                    <p className="text-xs text-slate-600 dark:text-slate-300 font-medium">
                      No external tool servers registered yet.
                    </p>
                    <p className="text-[11px] text-slate-400 mt-1 max-w-sm mx-auto">
                      Add an MCP server URL above (e.g. GitHub, Database, Zapier, Weather) to automatically import its tools into Lumina!
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {connections.map((conn) => {
                      const tools = conn.tools || (conn.tools_schema as any) || [];
                      const isExpanded = expandedServers[conn.id] !== false;

                      return (
                        <div
                          key={conn.id}
                          className="bg-white dark:bg-slate-900 rounded-xl border border-[#DCE5F2] dark:border-slate-800 overflow-hidden shadow-2xs transition-all"
                        >
                          {/* Server Card Header */}
                          <div
                            onClick={() => toggleServerExpand(conn.id)}
                            className="p-3.5 flex items-center justify-between cursor-pointer hover:bg-slate-50/70 dark:hover:bg-slate-800/40 transition-colors"
                          >
                            <div className="flex items-center gap-3 min-w-0">
                              <div className="w-8 h-8 rounded-lg bg-indigo-50 dark:bg-indigo-950/60 flex items-center justify-center text-indigo-600 dark:text-indigo-400 shrink-0">
                                <Server size={15} />
                              </div>
                              <div className="min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="font-semibold text-slate-900 dark:text-white text-xs">
                                    {conn.name}
                                  </span>
                                  <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300">
                                    {conn.transport}
                                  </span>
                                  <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 flex items-center gap-1">
                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                                    {tools.length} tool{tools.length === 1 ? '' : 's'}
                                  </span>
                                </div>
                                <p className="font-mono text-[10px] text-slate-400 truncate mt-0.5">
                                  {conn.endpoint_url}
                                </p>
                              </div>
                            </div>

                            <div className="flex items-center gap-1.5 shrink-0" onClick={(e) => e.stopPropagation()}>
                              <button
                                onClick={() => handleDelete(conn.id)}
                                className="p-1.5 text-slate-400 hover:text-red-600 transition-colors rounded-lg hover:bg-red-50 dark:hover:bg-red-950/30"
                                title="Delete server connection"
                              >
                                <Trash2 size={14} />
                              </button>
                              <button
                                onClick={() => toggleServerExpand(conn.id)}
                                className="p-1.5 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors rounded-lg"
                              >
                                <ChevronDown
                                  size={15}
                                  className={clsx('transition-transform duration-200', isExpanded && 'rotate-180')}
                                />
                              </button>
                            </div>
                          </div>

                          {/* Exposed Tools Catalog */}
                          {isExpanded && (
                            <div className="px-3.5 pb-3.5 pt-1 border-t border-slate-100 dark:border-slate-800/60 space-y-2 bg-slate-50/40 dark:bg-slate-900/30">
                              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider pt-1">
                                Discovered Tools Catalog ({tools.length})
                              </p>

                              {tools.length === 0 ? (
                                <p className="text-[11px] italic text-slate-400 py-2">
                                  No tools discovered on this server yet.
                                </p>
                              ) : (
                                <div className="grid grid-cols-1 gap-2">
                                  {tools.map((tool: any, idx: number) => {
                                    const toolName = tool.name || tool.id || `tool_${idx + 1}`;
                                    const desc = tool.description || 'Callable external tool via MCP protocol';
                                    const params = tool.input_schema?.properties
                                      ? Object.keys(tool.input_schema.properties)
                                      : [];

                                    return (
                                      <div
                                        key={toolName + idx}
                                        className="p-2.5 rounded-xl bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 text-xs space-y-1 hover:border-slate-300 dark:hover:border-slate-700 transition-colors"
                                      >
                                        <div className="flex items-center justify-between gap-2 flex-wrap">
                                          <div className="flex items-center gap-1.5">
                                            <Wrench size={12} className="text-lumina-600 dark:text-lumina-400 shrink-0" />
                                            <span className="font-mono font-semibold text-slate-900 dark:text-slate-100 text-xs">
                                              {toolName}
                                            </span>
                                          </div>
                                          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400">
                                            Callable
                                          </span>
                                        </div>

                                        <p className="text-[11px] text-slate-600 dark:text-slate-400 leading-relaxed">
                                          {desc}
                                        </p>

                                        {params.length > 0 && (
                                          <div className="flex items-center gap-1 flex-wrap pt-0.5">
                                            <span className="text-[9px] text-slate-400 font-mono">
                                              params:
                                            </span>
                                            {params.map((p) => (
                                              <span
                                                key={p}
                                                className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"
                                              >
                                                {p}
                                              </span>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    );
                                  })}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default MCPModal;
