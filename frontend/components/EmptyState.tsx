"use client";

import React from 'react';
import {
  Archive,
  ArrowUpRight,
  FileSpreadsheet,
  Globe,
  Image as ImageIcon,
  Sparkles,
} from 'lucide-react';

const PROMPT_STARTERS = [
  {
    icon: Archive,
    title: 'Archive Retrieval',
    description: 'Hybrid dense vector & sparse BM25 search across repository files.',
    prompt: 'Summarize the core capabilities and key findings across our uploaded documents.',
  },
  {
    icon: Globe,
    title: 'Live Web Research',
    description: 'Real-time web discovery with instant vector indexing & verification.',
    prompt: 'Search the live web for the latest breakthroughs in agentic AI in 2026.',
  },
  {
    icon: FileSpreadsheet,
    title: 'Financial & Table Synthesis',
    description: 'Deep extraction and reasoning over balance sheets and metrics.',
    prompt: 'According to the financial report, what was the Q4 Cloud ARR and gross margin percentage?',
  },
  {
    icon: ImageIcon,
    title: 'Multimodal Reasoning',
    description: 'Visual understanding of system architecture and diagrams.',
    prompt: 'Explain the difference between dense and sparse vector retrieval in 2 concise sentences.',
  },
];

interface EmptyStateProps {
  onSelectPrompt?: (prompt: string) => void;
}

export function EmptyState({ onSelectPrompt }: EmptyStateProps = {}) {
  return (
    <div className="py-8 md:py-16 space-y-10 animate-fade-up max-w-4xl mx-auto px-4">
      {/* ─── Hero Heading & Subtitle ─────────────────────────────────── */}
      <div className="text-center space-y-3 pt-4">
        <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-lumina-50 dark:bg-slate-800 border border-lumina-100 dark:border-slate-700 text-xs font-semibold text-lumina-600 dark:text-lumina-400 mb-1 shadow-2xs">
          <Sparkles size={13} />
          <span>Enterprise Corrective RAG Platform</span>
        </div>
        <h1 className="font-display text-4xl sm:text-5xl md:text-[54px] font-normal text-[#0F172A] dark:text-white leading-[1.08] tracking-tight">
          Enterprise Intelligence,
          <br />
          Reimagined.
        </h1>
        <p className="font-sans text-sm sm:text-base text-slate-500 dark:text-slate-400 max-w-xl mx-auto leading-relaxed">
          Synthesize complex documents, query live multimodal data, and extract verified insights with precision.
        </p>
      </div>

      {/* ─── 4 Interactive Prompt Starter Cards ──────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {PROMPT_STARTERS.map((starter, idx) => {
          const Icon = starter.icon;
          return (
            <button
              key={idx}
              type="button"
              onClick={() => onSelectPrompt?.(starter.prompt)}
              className="text-left p-5 rounded-2xl bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-800 flex flex-col justify-between h-[170px] shadow-2xs transition-all hover:border-lumina-500/80 hover:shadow-md dark:hover:border-slate-700 group cursor-pointer relative"
            >
              <div className="flex items-center justify-between w-full mb-3">
                <div className="w-9 h-9 rounded-xl bg-lumina-50 dark:bg-slate-800 group-hover:bg-lumina-600 group-hover:text-white transition-colors flex items-center justify-center">
                  <Icon size={18} className="text-lumina-600 dark:text-lumina-400 group-hover:text-white transition-colors" />
                </div>
                <ArrowUpRight size={16} className="text-slate-300 dark:text-slate-600 group-hover:text-lumina-600 dark:group-hover:text-lumina-400 transition-colors transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
              </div>
              <div>
                <h3 className="font-sans font-semibold text-sm text-slate-900 dark:text-white leading-snug group-hover:text-lumina-600 dark:group-hover:text-lumina-400 transition-colors">
                  {starter.title}
                </h3>
                <p className="font-sans text-xs text-slate-500 dark:text-slate-400 mt-1.5 leading-relaxed line-clamp-2">
                  {starter.description}
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default EmptyState;
