"use client";

import React, { useState, useMemo } from 'react';
import {
  Brain,
  Check,
  ChevronDown,
  Clock,
  Compass,
  Copy,
  Cpu,
  Layers,
  LucideIcon,
  RotateCcw,
  Scale,
  Search,
  Sparkles,
  Terminal,
  Zap,
} from 'lucide-react';
import clsx from 'clsx';
import { ThinkingEvent } from '../lib/types';

interface ThinkingAreaProps {
  events: ThinkingEvent[];
  isStreaming?: boolean;
  retrievalMs?: number;
}

type TabMode = 'timeline' | 'agents' | 'raw';

const AGENT_CONFIG: Record<
  string,
  {
    label: string;
    roleDesc: string;
    icon: LucideIcon;
    accentColor: string;
    badgeBg: string;
    badgeText: string;
    borderAccent: string;
  }
> = {
  router: {
    label: 'Router',
    roleDesc: 'Intent & Modality Classifier',
    icon: Compass,
    accentColor: 'text-indigo-500 dark:text-indigo-400',
    badgeBg: 'bg-indigo-50 dark:bg-indigo-950/50',
    badgeText: 'text-indigo-700 dark:text-indigo-300',
    borderAccent: 'border-indigo-500/30',
  },
  retriever: {
    label: 'Retriever',
    roleDesc: 'Hybrid Dense + BM25 Search',
    icon: Search,
    accentColor: 'text-sky-500 dark:text-sky-400',
    badgeBg: 'bg-sky-50 dark:bg-sky-950/50',
    badgeText: 'text-sky-700 dark:text-sky-300',
    borderAccent: 'border-sky-500/30',
  },
  grader: {
    label: 'Grader',
    roleDesc: 'Relevance & Sufficiency Score',
    icon: Scale,
    accentColor: 'text-emerald-600 dark:text-emerald-400',
    badgeBg: 'bg-emerald-50 dark:bg-emerald-950/50',
    badgeText: 'text-emerald-700 dark:text-emerald-300',
    borderAccent: 'border-emerald-500/30',
  },
  rewriter: {
    label: 'Rewriter',
    roleDesc: 'HyDE & Step-back Query Expansion',
    icon: RotateCcw,
    accentColor: 'text-purple-600 dark:text-purple-400',
    badgeBg: 'bg-purple-50 dark:bg-purple-950/50',
    badgeText: 'text-purple-700 dark:text-purple-300',
    borderAccent: 'border-purple-500/30',
  },
  generator: {
    label: 'Synthesizer',
    roleDesc: 'Context Grounding & Citation Engine',
    icon: Sparkles,
    accentColor: 'text-amber-600 dark:text-amber-400',
    badgeBg: 'bg-amber-50 dark:bg-amber-950/50',
    badgeText: 'text-amber-800 dark:text-amber-300',
    borderAccent: 'border-amber-500/30',
  },
};

function getAgentMeta(agentName: string) {
  const normalized = (agentName || '').toLowerCase().trim();
  return (
    AGENT_CONFIG[normalized] || {
      label: agentName || 'Agent',
      roleDesc: 'Cognitive Reasoning Step',
      icon: Cpu,
      accentColor: 'text-lumina-600 dark:text-lumina-400',
      badgeBg: 'bg-slate-100 dark:bg-slate-800',
      badgeText: 'text-slate-700 dark:text-slate-300',
      borderAccent: 'border-slate-300 dark:border-slate-700',
    }
  );
}

function formatThoughtSnippet(text: string) {
  // Highlight keywords like numbers, percentages, doc names, strategies
  const parts = text.split(
    /(\b(?:hyde|stepback|decompose|semantic|bm25|qdrant|reranked|sufficient|score:?\s*[\d.]+|[\d.]+ms|\d+\s*chunks?|\d+\s*sources?)\b)/gi,
  );

  return parts.map((part, index) => {
    if (
      /^(hyde|stepback|decompose|semantic|bm25|qdrant|reranked|sufficient|score:?\s*[\d.]+|[\d.]+ms|\d+\s*chunks?|\d+\s*sources?)$/i.test(
        part,
      )
    ) {
      return (
        <span
          key={index}
          className="font-semibold text-slate-900 dark:text-slate-100 bg-slate-200/70 dark:bg-slate-800/80 px-1 py-0.5 rounded text-[11px]"
        >
          {part}
        </span>
      );
    }
    return part;
  });
}

export function ThinkingArea({
  events,
  isStreaming = false,
  retrievalMs,
}: ThinkingAreaProps) {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<TabMode>('timeline');
  const [selectedAgentFilter, setSelectedAgentFilter] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const uniqueAgents = useMemo(() => {
    if (!events) return [];
    return Array.from(new Set(events.map((e) => e.agent)));
  }, [events]);

  const filteredEvents = useMemo(() => {
    if (!events) return [];
    if (!selectedAgentFilter) return events;
    return events.filter((e) => e.agent.toLowerCase() === selectedAgentFilter.toLowerCase());
  }, [events, selectedAgentFilter]);

  if (!events || events.length === 0) return null;

  const handleCopyAll = (e: React.MouseEvent) => {
    e.stopPropagation();
    const formatted = events
      .map((ev, i) => `[Step ${i + 1}] [${ev.agent.toUpperCase()}] ${ev.content}`)
      .join('\n');
    navigator.clipboard.writeText(formatted);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={clsx(
        'relative rounded-2xl border transition-all duration-300 overflow-hidden my-3',
        'bg-[#F8FAFD]/90 dark:bg-[#0B101B]/80 backdrop-blur-md',
        'border-[#E2E8F0] dark:border-[#1E293B] shadow-xs',
      )}
    >
      {/* Top Ambient Glow Shimmer */}
      <div
        className={clsx(
          'h-[2px] w-full transition-opacity duration-500',
          isStreaming
            ? 'bg-gradient-to-r from-indigo-500 via-lumina-500 to-emerald-400 animate-pulse'
            : 'bg-gradient-to-r from-slate-200 dark:from-slate-800 via-lumina-500/30 to-slate-200 dark:to-slate-800 opacity-60',
        )}
      />

      {/* Header Bar */}
      <div
        onClick={() => setIsOpen((prev) => !prev)}
        className="px-4 py-3 flex items-center justify-between cursor-pointer select-none hover:bg-slate-100/50 dark:hover:bg-slate-800/30 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          {/* Animated Brain / Orb */}
          <div
            className={clsx(
              'relative w-7 h-7 rounded-xl flex items-center justify-center shrink-0 transition-transform duration-300',
              isStreaming
                ? 'bg-lumina-600 text-white shadow-md shadow-lumina-600/30 scale-105'
                : 'bg-slate-100 dark:bg-slate-800/80 text-slate-600 dark:text-slate-300',
            )}
          >
            <Brain size={15} className={clsx(isStreaming && 'animate-pulse')} />
            {isStreaming && (
              <span className="absolute -top-0.5 -right-0.5 flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-lumina-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-lumina-500"></span>
              </span>
            )}
          </div>

          {/* Title & Stats */}
          <div className="flex items-center gap-2 flex-wrap min-w-0">
            <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">
              Thinking Process
            </span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-200/70 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-medium">
              {events.length} step{events.length === 1 ? '' : 's'}
            </span>

            {isStreaming ? (
              <span className="inline-flex items-center gap-1.5 text-[10px] font-medium text-lumina-600 dark:text-lumina-400">
                <span className="w-1.5 h-1.5 rounded-full bg-lumina-600 animate-ping" />
                Reasoning live…
              </span>
            ) : (
              <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
                <Check size={11} strokeWidth={3} />
                Complete
              </span>
            )}

            {retrievalMs ? (
              <span className="hidden sm:inline-flex items-center gap-1 text-[10px] font-mono text-slate-400">
                <Clock size={10} />
                {retrievalMs}ms
              </span>
            ) : null}
          </div>
        </div>

        {/* Right Header Actions */}
        <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            onClick={handleCopyAll}
            className="p-1.5 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-200/60 dark:hover:bg-slate-800 rounded-lg transition-colors"
            title="Copy thought trace"
            aria-label="Copy thought trace"
          >
            {copied ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
          </button>
          <button
            type="button"
            onClick={() => setIsOpen((prev) => !prev)}
            className="p-1.5 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-200/60 dark:hover:bg-slate-800 rounded-lg transition-colors"
            aria-label={isOpen ? 'Collapse thinking area' : 'Expand thinking area'}
          >
            <ChevronDown
              size={15}
              className={clsx('transition-transform duration-200', isOpen && 'rotate-180')}
            />
          </button>
        </div>
      </div>

      {/* Expandable Body */}
      {isOpen && (
        <div className="px-4 pb-4 pt-1 border-t border-[#EDF3FA] dark:border-slate-800/80">
          {/* Sub-Navigation Tabs */}
          <div className="flex items-center justify-between gap-2 pb-3 pt-1 border-b border-slate-100 dark:border-slate-800/50 flex-wrap">
            <div className="flex items-center gap-1 p-0.5 rounded-xl bg-slate-200/50 dark:bg-slate-800/50 text-[11px]">
              <button
                type="button"
                onClick={() => {
                  setActiveTab('timeline');
                  setSelectedAgentFilter(null);
                }}
                className={clsx(
                  'px-2.5 py-1 rounded-lg font-medium transition-colors flex items-center gap-1.5',
                  activeTab === 'timeline'
                    ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-2xs font-semibold'
                    : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-300',
                )}
              >
                <Layers size={12} />
                Timeline
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('agents')}
                className={clsx(
                  'px-2.5 py-1 rounded-lg font-medium transition-colors flex items-center gap-1.5',
                  activeTab === 'agents'
                    ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-2xs font-semibold'
                    : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-300',
                )}
              >
                <Compass size={12} />
                Agents Matrix
              </button>
              <button
                type="button"
                onClick={() => {
                  setActiveTab('raw');
                  setSelectedAgentFilter(null);
                }}
                className={clsx(
                  'px-2.5 py-1 rounded-lg font-medium transition-colors flex items-center gap-1.5',
                  activeTab === 'raw'
                    ? 'bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-2xs font-semibold'
                    : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-300',
                )}
              >
                <Terminal size={12} />
                Raw Log
              </button>
            </div>

            {/* Agent Filter Chips (Visible when in Agents mode) */}
            {activeTab === 'agents' && (
              <div className="flex items-center gap-1 overflow-x-auto py-1">
                <button
                  type="button"
                  onClick={() => setSelectedAgentFilter(null)}
                  className={clsx(
                    'px-2 py-0.5 rounded-md text-[10px] font-medium transition-colors',
                    selectedAgentFilter === null
                      ? 'bg-lumina-600 text-white font-semibold'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700',
                  )}
                >
                  All ({events.length})
                </button>
                {uniqueAgents.map((ag) => {
                  const meta = getAgentMeta(ag);
                  const count = events.filter((e) => e.agent === ag).length;
                  const isSelected = selectedAgentFilter?.toLowerCase() === ag.toLowerCase();
                  return (
                    <button
                      key={ag}
                      type="button"
                      onClick={() => setSelectedAgentFilter(isSelected ? null : ag)}
                      className={clsx(
                        'px-2 py-0.5 rounded-md text-[10px] font-medium transition-colors flex items-center gap-1',
                        isSelected
                          ? 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 font-semibold'
                          : `${meta.badgeBg} ${meta.badgeText} hover:opacity-80`,
                      )}
                    >
                      <span>{meta.label}</span>
                      <span className="opacity-70 font-mono">({count})</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Content View 1: Timeline Mode */}
          {activeTab === 'timeline' && (
            <div className="relative pl-6 pt-3 space-y-3 before:absolute before:left-2.5 before:top-4 before:bottom-2 before:w-0.5 before:bg-gradient-to-b before:from-indigo-400 before:via-lumina-500 before:to-emerald-400 dark:before:from-indigo-900 dark:before:via-lumina-800 dark:before:to-emerald-900">
              {filteredEvents.map((evt, idx) => {
                const meta = getAgentMeta(evt.agent);
                const IconComponent = meta.icon;
                const isLast = idx === filteredEvents.length - 1;

                return (
                  <div
                    key={`${evt.agent}-${evt.step}-${idx}`}
                    className="relative group animate-fade-in"
                  >
                    {/* Node Dot / Icon on Timeline */}
                    <div
                      className={clsx(
                        'absolute -left-6 top-1 w-5 h-5 rounded-full flex items-center justify-center transition-transform group-hover:scale-110',
                        'bg-white dark:bg-slate-900 border shadow-2xs',
                        meta.borderAccent,
                      )}
                    >
                      <IconComponent size={11} className={meta.accentColor} />
                    </div>

                    {/* Step Card */}
                    <div
                      className={clsx(
                        'p-3 rounded-xl border transition-all',
                        'bg-white/80 dark:bg-slate-900/60 border-slate-200/70 dark:border-slate-800/70 hover:border-slate-300 dark:hover:border-slate-700',
                        isLast && isStreaming && 'ring-1 ring-lumina-500/40',
                      )}
                    >
                      {/* Step Header */}
                      <div className="flex items-center justify-between gap-2 mb-1.5 flex-wrap">
                        <div className="flex items-center gap-2">
                          <span
                            className={clsx(
                              'text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-md',
                              meta.badgeBg,
                              meta.badgeText,
                            )}
                          >
                            {meta.label}
                          </span>
                          <span className="text-[10px] text-slate-400 font-mono">
                            {meta.roleDesc}
                          </span>
                        </div>
                        <span className="text-[10px] font-mono text-slate-400">
                          Step #{idx + 1}
                        </span>
                      </div>

                      {/* Step Thought Content */}
                      <p className="text-xs leading-relaxed text-slate-700 dark:text-slate-300 font-mono">
                        {formatThoughtSnippet(evt.content)}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Content View 2: Agents Matrix */}
          {activeTab === 'agents' && (
            <div className="pt-3 space-y-2.5">
              {filteredEvents.map((evt, idx) => {
                const meta = getAgentMeta(evt.agent);
                const IconComponent = meta.icon;

                return (
                  <div
                    key={`${evt.agent}-${idx}`}
                    className="p-3 rounded-xl bg-white/90 dark:bg-slate-900/70 border border-slate-200/80 dark:border-slate-800/80 flex items-start gap-3 hover:border-slate-300 transition-all"
                  >
                    <div
                      className={clsx(
                        'w-8 h-8 rounded-xl flex items-center justify-center shrink-0 border',
                        meta.badgeBg,
                        meta.borderAccent,
                      )}
                    >
                      <IconComponent size={15} className={meta.accentColor} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span
                          className={clsx(
                            'text-xs font-semibold uppercase tracking-wider',
                            meta.accentColor,
                          )}
                        >
                          {meta.label}
                        </span>
                        <span className="text-[10px] font-mono text-slate-400">
                          {meta.roleDesc}
                        </span>
                      </div>
                      <p className="text-xs font-mono text-slate-700 dark:text-slate-300 leading-relaxed">
                        {formatThoughtSnippet(evt.content)}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Content View 3: Raw Log */}
          {activeTab === 'raw' && (
            <div className="pt-3">
              <pre className="p-3 rounded-xl bg-slate-900 text-slate-100 font-mono text-[11px] leading-relaxed overflow-x-auto border border-slate-800">
                <code>
                  {events
                    .map(
                      (evt, i) =>
                        `[#${i + 1}] [${evt.agent.toUpperCase().padEnd(9)}] ${evt.content}`,
                    )
                    .join('\n')}
                </code>
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ThinkingArea;
