"use client";

import React, { useEffect, useRef } from 'react';
import MarkdownRenderer from './MarkdownRenderer';
import { Source, AgentTraceStep, RetrievalInfo, ThinkingEvent } from '../lib/types';
import { ThinkingArea } from './ThinkingArea';
import CitationCard from './CitationCard';

interface StreamingMessageProps {
  /** Token-by-token accumulated content. */
  content: string;
  /** Whether new tokens are still arriving. */
  isStreaming: boolean;
  /** Retrieved sources for citation display. */
  sources?: Source[];
  /** Pipeline trace steps (kept for backward compatibility). */
  agentTrace?: AgentTraceStep[];
  /** Retrieval metrics (chunk counts, timing). */
  retrievalInfo?: RetrievalInfo | null;
  /** Per-agent thinking notes. */
  thinking?: ThinkingEvent[];
}

export function StreamingMessage({
  content,
  isStreaming,
  sources = [],
  retrievalInfo = null,
  thinking = [],
}: StreamingMessageProps) {
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (contentRef.current && isStreaming) {
      contentRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [content, isStreaming]);

  return (
    <div className="space-y-3">
      {/* Innovative Out-of-the-Box Thinking Area */}
      {thinking && thinking.length > 0 && (
        <ThinkingArea
          events={thinking}
          isStreaming={isStreaming}
          retrievalMs={retrievalInfo?.retrieval_ms}
        />
      )}

      {/* Retrieval info metric pill (if available) */}
      {retrievalInfo && !isStreaming && (
        <div className="inline-flex items-center gap-2.5 text-[11px] font-mono text-slate-500 dark:text-slate-400 bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-800 rounded-xl px-3 py-1 shadow-2xs">
          <span>Retrieved: {retrievalInfo.retrieved_count}</span>
          <span className="text-slate-300 dark:text-slate-700">|</span>
          <span>Reranked: {retrievalInfo.reranked_count}</span>
          <span className="text-slate-300 dark:text-slate-700">|</span>
          <span>{retrievalInfo.retrieval_ms}ms</span>
          {retrievalInfo.is_sufficient && (
            <>
              <span className="text-slate-300 dark:text-slate-700">|</span>
              <span className="text-emerald-600 font-medium">✓ Sufficient</span>
            </>
          )}
        </div>
      )}

      {/* Streaming markdown content */}
      <div ref={contentRef} className="relative">
        {content ? (
          <MarkdownRenderer content={content} />
        ) : isStreaming ? (
          <div className="flex items-center gap-2 text-slate-400 py-1">
            <span className="streaming-dots">
              <span>·</span><span>·</span><span>·</span>
            </span>
          </div>
        ) : null}

        {/* Streaming cursor */}
        {isStreaming && content && (
          <span className="inline-block w-0.5 h-4 bg-lumina-600 animate-pulse ml-0.5 align-text-bottom" />
        )}
      </div>

      {/* Source citations */}
      {sources.length > 0 && !isStreaming && (
        <div className="space-y-2 pt-2 border-t border-[#EDF3FA] dark:border-slate-800">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            Sources ({sources.length})
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            {sources.map((source, idx) => (
              <CitationCard key={source.chunk_id || idx} source={source} index={idx} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default StreamingMessage;
