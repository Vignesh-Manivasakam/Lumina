"use client";

import React, { useState } from 'react';
import { Source } from '../lib/types';
import { ChevronDown } from 'lucide-react';

interface CitationCardProps {
  source: Source;
  index: number;
}

const MODALITY_ICON: Record<string, string> = {
  text: '¶',
  table: '⊞',
  image: '▣',
  audio_transcript: '♪',
  video_frame: '◳',
};

export function CitationCard({ source, index }: CitationCardProps) {
  const [expanded, setExpanded] = useState(false);
  const modality = source.modality || 'text';
  const confidence =
    typeof source.rerank_score === 'number'
      ? source.rerank_score
      : source.score ?? null;

  const pageLabel = source.page_num ? `p. ${source.page_num}` : '';
  const docTitle = source.doc_title || 'Source';

  return (
    <details
      className="bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-800 rounded-xl cursor-pointer group animate-fade-up overflow-hidden shadow-2xs transition-all hover:border-lumina-400"
      style={{ animationDelay: `${index * 40}ms` }}
      onToggle={(e) => setExpanded((e.target as HTMLDetailsElement).open)}
    >
      <summary className="list-none px-4 py-3 flex items-baseline gap-3 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
        <span className="font-mono text-xs font-semibold text-lumina-600 tabular-nums shrink-0">
          [{String(index + 1).padStart(2, '0')}]
        </span>

        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 shrink-0">
          {MODALITY_ICON[modality] || '·'} {modality.replace('_', ' ')}
        </span>

        <span className="text-xs font-medium text-slate-800 dark:text-slate-200 flex-1 min-w-0 truncate">
          {pageLabel} {pageLabel && '·'} {docTitle}
        </span>

        {confidence !== null && (
          <span className="font-mono text-[10px] text-slate-400 tabular-nums shrink-0">
            {Math.round(confidence * 100)}%
          </span>
        )}
      </summary>

      {expanded && (
        <div className="px-4 pb-4 pt-2 border-t border-[#EDF3FA] dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/30">
          {source.contextual_header && (
            <p className="text-xs font-semibold text-lumina-600 mb-2">{source.contextual_header}</p>
          )}

          <blockquote className="text-xs leading-relaxed text-slate-700 dark:text-slate-300 italic border-l-2 border-lumina-500 pl-3">
            {source.original_text || source.text_repr}
          </blockquote>

          <div className="mt-3 pt-2 border-t border-slate-200/60 dark:border-slate-800 flex items-center justify-between text-[10px] font-mono text-slate-400">
            <span>chunk_id: {source.chunk_id?.slice(0, 12)}</span>
            {source.page_num !== undefined && (
              <span>page {source.page_num}</span>
            )}
          </div>
        </div>
      )}
    </details>
  );
}

interface CitationListProps {
  sources: Source[];
}

export function CitationList({ sources }: CitationListProps) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-5 space-y-3">
      <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
        Sources &nbsp;·&nbsp; {sources.length}
      </p>
      <div className="space-y-2">
        {sources.map((s, i) => (
          <CitationCard key={s.chunk_id || i} source={s} index={i} />
        ))}
      </div>
    </div>
  );
}

export default CitationCard;
