"use client";

import React, { useState } from 'react';
import { ChevronDown, ChevronUp, ExternalLink, Globe } from 'lucide-react';
import { WebSearchResult } from '../lib/types';

interface WebResultsCardProps {
  results: WebSearchResult[];
}

export function WebResultsCard({ results }: WebResultsCardProps) {
  const [expanded, setExpanded] = useState(false);

  if (!results || results.length === 0) return null;

  const displayResults = expanded ? results : results.slice(0, 3);

  return (
    <div className="mt-5 border border-[#DCE5F2] dark:border-slate-800 bg-white dark:bg-slate-900 rounded-2xl p-4 shadow-sm animate-fade-up">
      <div className="flex items-center justify-between pb-2.5 mb-3 border-b border-[#EDF3FA] dark:border-slate-800">
        <div className="flex items-center gap-2">
          <Globe size={15} className="text-lumina-600" />
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-800 dark:text-slate-200">
            Live Web Discoveries · {results.length}
          </span>
        </div>
        {results.length > 3 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-[11px] font-mono text-slate-400 hover:text-lumina-600 transition-colors font-medium"
          >
            <span>{expanded ? 'Show less' : `+${results.length - 3} more`}</span>
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
        )}
      </div>

      <div className="space-y-2.5">
        {displayResults.map((item, idx) => {
          let domain = '';
          try {
            domain = new URL(item.url).hostname.replace('www.', '');
          } catch {
            domain = item.url;
          }

          return (
            <div
              key={item.url || idx}
              className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-[#EDF3FA] dark:border-slate-800 hover:border-lumina-400 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-sans font-semibold text-xs text-slate-900 dark:text-white hover:text-lumina-600 transition-colors flex items-center gap-1.5 group"
                >
                  <span className="line-clamp-1">{item.title || domain}</span>
                  <ExternalLink size={12} className="shrink-0 opacity-60 group-hover:opacity-100 transition-opacity" />
                </a>
                <span className="shrink-0 text-[10px] font-mono px-2 py-0.5 rounded bg-white dark:bg-slate-900 text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
                  {domain}
                </span>
              </div>
              {item.content && (
                <p className="mt-1.5 text-xs font-sans text-slate-600 dark:text-slate-400 line-clamp-2 leading-relaxed">
                  {item.content}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default WebResultsCard;
