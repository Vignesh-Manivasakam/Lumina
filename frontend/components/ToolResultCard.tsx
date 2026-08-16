"use client";

import React, { useState } from 'react';
import { Check, ChevronDown, ChevronRight, Copy, Terminal } from 'lucide-react';

interface ToolResultCardProps {
  toolResult: any;
}

export function ToolResultCard({ toolResult }: ToolResultCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  if (!toolResult) return null;

  const rawJson =
    typeof toolResult === 'string'
      ? toolResult
      : JSON.stringify(toolResult, null, 2);

  const handleCopy = () => {
    navigator.clipboard.writeText(rawJson);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="mt-4 border border-[#DCE5F2] dark:border-slate-800 bg-white dark:bg-slate-900 rounded-xl text-xs shadow-2xs overflow-hidden animate-fade-up">
      <div
        onClick={() => setIsOpen(!isOpen)}
        className="px-3.5 py-2.5 flex items-center justify-between cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors select-none"
      >
        <div className="flex items-center gap-2 text-slate-800 dark:text-slate-200">
          <Terminal size={14} className="text-lumina-600 shrink-0" />
          <span className="font-mono text-[11px] font-medium">
            Tool Execution Output
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              handleCopy();
            }}
            className="p-1 text-slate-400 hover:text-lumina-600 transition-colors rounded"
            title="Copy output"
          >
            {copied ? <Check size={12} className="text-emerald-600" /> : <Copy size={12} />}
          </button>
          <span className="text-slate-400">
            {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        </div>
      </div>

      {isOpen && (
        <div className="p-3 border-t border-[#EDF3FA] dark:border-slate-800 bg-slate-50 dark:bg-slate-950">
          <pre className="font-mono text-[11px] text-slate-700 dark:text-slate-300 overflow-x-auto max-h-60 leading-relaxed whitespace-pre-wrap">
            <code>{rawJson}</code>
          </pre>
        </div>
      )}
    </div>
  );
}

export default ToolResultCard;
