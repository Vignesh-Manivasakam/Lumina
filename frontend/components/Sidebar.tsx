"use client";

import React, { useState, useRef } from 'react';
import {
  Activity,
  CheckCircle2,
  ChevronLeft,
  Cpu,
  FileCode,
  FileSpreadsheet,
  FileText,
  History,
  Image as ImageIcon,
  Loader2,
  Plus,
  Server,
  Sparkles,
  Trash2,
  Upload,
  Zap,
} from 'lucide-react';
import clsx from 'clsx';
import { Conversation, DocumentItem, MCPConnection } from '../lib/types';
import { deleteDocument } from '../lib/api';

interface SidebarProps {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  documents: DocumentItem[];
  isUploading: boolean;
  onFileUpload: (file: File) => Promise<void>;
  onDeleteDocument?: (id: string) => Promise<void> | void;
  conversations: Conversation[];
  activeConversation: Conversation | null;
  onSelectConversation: (conv: Conversation) => void;
  onNewConversation: () => void;
  mcpConnections: MCPConnection[];
  onOpenMCPModal: () => void;
  onOpenSkillsModal?: () => void;
  queriesRunCount?: number;
  tokensUsedCount?: number;
}

export function Sidebar({
  sidebarOpen,
  setSidebarOpen,
  documents,
  isUploading,
  onFileUpload,
  onDeleteDocument,
  conversations,
  activeConversation,
  onSelectConversation,
  onNewConversation,
  mcpConnections,
  onOpenMCPModal,
  onOpenSkillsModal,
  queriesRunCount = 0,
  tokensUsedCount = 0,
}: SidebarProps) {
  const [activeSection, setActiveSection] = useState<'documents' | 'sessions' | 'collections'>('documents');
  const [isDragging, setIsDragging] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      await onFileUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      await onFileUpload(e.target.files[0]);
      e.target.value = '';
    }
  };

  const handleDeleteDoc = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeletingId(id);
    try {
      await deleteDocument(id);
      if (onDeleteDocument) {
        await onDeleteDocument(id);
      }
    } catch (err) {
      console.error('Delete failed:', err);
    } finally {
      setDeletingId(null);
    }
  };

  const getFileIcon = (fileType?: string) => {
    const ft = (fileType || '').toLowerCase();
    if (ft.includes('pdf')) return <FileText size={15} className="text-red-500 shrink-0" />;
    if (ft.includes('sheet') || ft.includes('csv') || ft.includes('xls'))
      return <FileSpreadsheet size={15} className="text-emerald-600 shrink-0" />;
    if (ft.includes('image') || ft.includes('png') || ft.includes('jpg'))
      return <ImageIcon size={15} className="text-indigo-500 shrink-0" />;
    if (ft.includes('code') || ft.includes('py') || ft.includes('json') || ft.includes('js'))
      return <FileCode size={15} className="text-lumina-600 shrink-0" />;
    return <FileText size={15} className="text-slate-500 shrink-0" />;
  };

  return (
    <>
      <aside
        className={clsx(
          'w-[274px] shrink-0 h-full border-r flex flex-col z-30 transition-all duration-300',
          'bg-[#F9FBFE] dark:bg-[#0B0F19] border-[#EDF3FA] dark:border-slate-800/80',
          'lg:relative lg:translate-x-0 fixed inset-y-0 left-0',
          sidebarOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full lg:translate-x-0',
        )}
      >
        {/* Top Header: Official Lumina Wordmark Image + Collapse Button */}
        <div className="h-16 px-5 flex items-center justify-between border-b border-[#EDF3FA] dark:border-slate-800/80">
          <div className="flex items-center py-1">
            <img
              src="/images/lumina-logo.png"
              alt="Lumina"
              className="h-9 w-auto max-h-10 object-contain dark:hidden select-none transition-transform hover:scale-105"
            />
            <img
              src="/images/lumina-logo-white.png"
              alt="Lumina"
              className="h-9 w-auto max-h-10 object-contain hidden dark:block select-none transition-transform hover:scale-105"
            />
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            aria-label="Collapse sidebar"
          >
            <ChevronLeft size={16} />
          </button>
        </div>

        {/* Action Button: + New Chat */}
        <div className="px-4 pt-4 pb-2">
          <button
            type="button"
            onClick={onNewConversation}
            className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl bg-lumina-600 hover:bg-lumina-700 active:scale-[0.98] text-white text-xs font-semibold shadow-sm shadow-lumina-600/20 transition-all cursor-pointer"
          >
            <Plus size={15} strokeWidth={2.5} />
            <span>New Chat</span>
          </button>
        </div>

        {/* Main Navigation Tabs */}
        <div className="px-3 py-2 space-y-1">
          {/* Documents Tab */}
          <button
            onClick={() => setActiveSection('documents')}
            className={clsx(
              'w-full flex items-center gap-3 px-3 py-2 rounded-xl text-xs font-medium transition-colors text-left',
              activeSection === 'documents'
                ? 'bg-lumina-50 dark:bg-lumina-950/40 text-lumina-600 dark:text-lumina-400 font-semibold'
                : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100/70 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-white',
            )}
          >
            <FileText size={15} className="shrink-0 opacity-80" />
            <span className="flex-1">Documents</span>
            {documents.length > 0 && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-md bg-slate-200/60 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                {documents.length}
              </span>
            )}
          </button>

          {/* Sessions Tab */}
          <button
            onClick={() => setActiveSection('sessions')}
            className={clsx(
              'w-full flex items-center gap-3 px-3 py-2 rounded-xl text-xs font-medium transition-colors text-left',
              activeSection === 'sessions'
                ? 'bg-lumina-50 dark:bg-lumina-950/40 text-lumina-600 dark:text-lumina-400 font-semibold'
                : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100/70 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-white',
            )}
          >
            <History size={15} className="shrink-0 opacity-80" />
            <span className="flex-1">Sessions</span>
            {conversations.length > 0 && (
              <span className="text-[10px] font-mono text-slate-400">
                {conversations.length}
              </span>
            )}
          </button>

          {/* Collections & MCP Tab */}
          <button
            onClick={() => setActiveSection('collections')}
            className={clsx(
              'w-full flex items-center gap-3 px-3 py-2 rounded-xl text-xs font-medium transition-colors text-left',
              activeSection === 'collections'
                ? 'bg-lumina-50 dark:bg-lumina-950/40 text-lumina-600 dark:text-lumina-400 font-semibold'
                : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100/70 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-white',
            )}
          >
            <Cpu size={15} className="shrink-0 opacity-80 text-lumina-600" />
            <span className="flex-1">Collections & MCP</span>
            {mcpConnections.length > 0 ? (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded-md bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300">
                {mcpConnections.length} active
              </span>
            ) : (
              <span className="text-[10px] font-mono text-slate-400">Hub</span>
            )}
          </button>

          {/* Cognitive Skills Button */}
          {onOpenSkillsModal && (
            <button
              onClick={onOpenSkillsModal}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-xl text-xs font-medium transition-colors text-left text-slate-600 dark:text-slate-400 hover:bg-slate-100/70 dark:hover:bg-slate-800/50 hover:text-slate-900 dark:hover:text-white"
            >
              <Sparkles size={15} className="shrink-0 opacity-80 text-amber-500" />
              <span className="flex-1">Cognitive Skills</span>
            </button>
          )}
        </div>

        {/* Middle Scrollable Section */}
        <div className="flex-1 overflow-y-auto px-4 py-2 space-y-3">
          {activeSection === 'documents' && (
            <div className="space-y-3 animate-fade-up">
              {/* Drag and Drop Upload Box */}
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => !isUploading && fileInputRef.current?.click()}
                className={clsx(
                  'border-2 border-dashed rounded-xl p-3 text-center cursor-pointer transition-all',
                  isDragging
                    ? 'border-lumina-600 bg-lumina-50/50 dark:bg-lumina-950/20'
                    : 'border-[#DCE5F2] dark:border-slate-800 hover:border-lumina-500 bg-white dark:bg-slate-900',
                  isUploading && 'opacity-60 cursor-wait pointer-events-none',
                )}
              >
                <div className="flex flex-col items-center gap-1.5 py-1">
                  <div className="w-7 h-7 rounded-full bg-lumina-50 dark:bg-slate-800 flex items-center justify-center text-lumina-600">
                    {isUploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                  </div>
                  <p className="text-[11px] font-medium text-slate-800 dark:text-slate-200">
                    {isUploading ? 'Ingesting…' : 'Drop documents here'}
                  </p>
                  <p className="text-[9px] text-slate-400">PDF, DOCX, CSV, Image, Audio</p>
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  onChange={handleFileInputChange}
                  className="hidden"
                  accept=".pdf,.docx,.pptx,.txt,.md,.csv,.xlsx,.json,.py,.js,.ts,image/*,audio/*"
                />
              </div>

              {/* Uploaded Documents List */}
              <div className="space-y-1">
                <div className="flex items-center justify-between pb-1">
                  <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                    Library ({documents.length})
                  </span>
                </div>
                {documents.length === 0 ? (
                  <p className="text-xs italic text-slate-400 py-3 text-center">No documents in library.</p>
                ) : (
                  <div className="space-y-1 max-h-56 overflow-y-auto pr-1">
                    {documents.map((doc) => (
                      <div
                        key={doc.id}
                        className="group flex items-center justify-between p-2 rounded-xl bg-white dark:bg-slate-900 border border-[#EDF3FA] dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 transition-all text-xs"
                      >
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                          {getFileIcon(doc.file_type)}
                          <div className="min-w-0 flex-1">
                            <p className="truncate font-medium text-slate-800 dark:text-slate-200 text-xs">
                              {doc.filename}
                            </p>
                            <p className="text-[9px] font-mono text-slate-400 truncate">
                              {doc.dept || 'General'}
                            </p>
                          </div>
                        </div>
                        <button
                          onClick={(e) => handleDeleteDoc(doc.id, e)}
                          disabled={deletingId === doc.id}
                          className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-red-500 transition-all"
                          title="Delete document"
                        >
                          {deletingId === doc.id ? (
                            <Loader2 size={12} className="animate-spin" />
                          ) : (
                            <Trash2 size={12} />
                          )}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {activeSection === 'sessions' && (
            <div className="space-y-2 animate-fade-up">
              <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                Recent Inquests
              </p>
              {conversations.length === 0 ? (
                <p className="text-xs italic text-slate-400 py-3 text-center">No prior conversations.</p>
              ) : (
                <div className="space-y-1 max-h-56 overflow-y-auto pr-1">
                  {conversations.map((conv) => {
                    const isActive = activeConversation?.id === conv.id;
                    return (
                      <div
                        key={conv.id}
                        onClick={() => onSelectConversation(conv)}
                        className={clsx(
                          'p-2.5 rounded-xl border cursor-pointer transition-all text-xs',
                          isActive
                            ? 'border-lumina-600 bg-lumina-50/70 dark:bg-lumina-950/30 text-lumina-600 font-medium shadow-2xs'
                            : 'border-[#EDF3FA] dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300',
                        )}
                      >
                        <p className="truncate leading-snug">{conv.title || 'Untitled Session'}</p>
                        <p className="text-[9px] font-mono text-slate-400 mt-1">
                          {new Date(conv.created_at || Date.now()).toLocaleDateString()}
                        </p>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {activeSection === 'collections' && (
            <div className="space-y-3 animate-fade-up">
              <div className="flex items-center justify-between">
                <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                  MCP Hub ({mcpConnections.length})
                </p>
                <button
                  onClick={onOpenMCPModal}
                  className="text-[10px] font-semibold text-lumina-600 dark:text-lumina-400 hover:underline"
                >
                  + Add
                </button>
              </div>

              {/* Default Lumina SSE Server */}
              <div className="p-3 bg-white dark:bg-slate-900 rounded-xl border border-[#DCE5F2] dark:border-slate-800 space-y-1.5 text-xs shadow-2xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <Server size={13} className="text-lumina-600" />
                    <span className="font-semibold text-slate-800 dark:text-slate-200">Lumina Native MCP</span>
                  </div>
                  <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300">
                    Online
                  </span>
                </div>
                <p className="font-mono text-[10px] text-slate-400 truncate">
                  8 native RAG & retrieval tools
                </p>
              </div>

              {/* Dynamic Connected MCP Servers */}
              {mcpConnections.map((conn) => {
                const toolCount = conn.tools?.length || conn.tools_schema?.length || 0;
                return (
                  <div
                    key={conn.id}
                    onClick={onOpenMCPModal}
                    className="p-3 bg-white dark:bg-slate-900 rounded-xl border border-[#DCE5F2] dark:border-slate-800 space-y-1.5 text-xs shadow-2xs hover:border-slate-300 dark:hover:border-slate-700 cursor-pointer transition-all"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <Zap size={13} className="text-amber-500" />
                        <span className="font-semibold text-slate-800 dark:text-slate-200 truncate max-w-[120px]">
                          {conn.name}
                        </span>
                      </div>
                      <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300">
                        {toolCount} tool{toolCount === 1 ? '' : 's'}
                      </span>
                    </div>
                    <p className="font-mono text-[10px] text-slate-400 truncate">
                      {conn.endpoint_url}
                    </p>
                  </div>
                );
              })}

              <button
                onClick={onOpenMCPModal}
                className="w-full py-2 px-3 bg-lumina-50 dark:bg-slate-800 hover:bg-lumina-100 text-lumina-600 dark:text-lumina-400 rounded-xl text-xs font-semibold border border-lumina-200 dark:border-slate-700 transition-colors"
              >
                Manage MCP Connections
              </button>
            </div>
          )}
        </div>

        {/* Activity Widget Card: Today's Activity */}
        <div className="px-4 py-3 border-t border-[#EDF3FA] dark:border-slate-800">
          <div className="p-3.5 rounded-2xl bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-800 shadow-2xs space-y-2.5">
            <p className="text-[11px] font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
              <Activity size={13} className="text-lumina-600" />
              <span>Today&apos;s Activity</span>
            </p>
            <div className="space-y-1.5 text-xs">
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
                <span>Documents Indexed</span>
                <span className="font-mono font-semibold text-slate-800 dark:text-slate-200">
                  {documents.length}
                </span>
              </div>
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
                <span>Queries Run</span>
                <span className="font-mono font-semibold text-slate-800 dark:text-slate-200">
                  {Math.max(0, queriesRunCount || 0)}
                </span>
              </div>
              <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
                <span>Token Usage</span>
                <span className="font-mono font-semibold text-lumina-600 dark:text-lumina-400">
                  {tokensUsedCount > 999
                    ? `${(tokensUsedCount / 1000).toFixed(1)}k`
                    : tokensUsedCount.toLocaleString()}
                </span>
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile Drawer Backdrop */}
      {sidebarOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-slate-900/40 backdrop-blur-xs z-20"
          onClick={() => setSidebarOpen(false)}
        />
      )}
    </>
  );
}

export default Sidebar;
