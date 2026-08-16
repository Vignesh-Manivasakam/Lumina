"use client";

import React from 'react';
import clsx from 'clsx';
import { AgentName, AgentStatus, AgentTraceStep } from '../lib/types';

interface AgentTraceProps {
  steps: AgentTraceStep[];
  isStreaming: boolean;
}

const PIPELINE: { name: AgentName; label: string }[] = [
  { name: 'router', label: 'Route' },
  { name: 'retriever', label: 'Retrieve' },
  { name: 'grader', label: 'Grade' },
  { name: 'rewriter', label: 'Rewrite' },
  { name: 'generator', label: 'Generate' },
];

function statusFor(steps: AgentTraceStep[], name: AgentName): AgentStatus {
  const last = [...steps].reverse().find((s) => s.agent === name);
  return (last?.status ?? 'pending') as AgentStatus;
}

export function AgentTrace({ steps, isStreaming }: AgentTraceProps) {
  if (!isStreaming && steps.length === 0) return null;

  // Only render agents that have actually been touched by the pipeline
  const visibleAgents = PIPELINE.filter((p) =>
    steps.some((s) => s.agent === p.name) || isStreaming,
  );

  // Find the last active agent (the "current" step)
  const activeStep = [...steps].reverse().find((s) => s.status === 'active');

  return (
    <div
      className="border-t border-[#EDF3FA] dark:border-slate-800 pt-4 mt-4"
      role="status"
      aria-live="polite"
      aria-label="Agent pipeline progress"
    >
      {/* Eyebrow label */}
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2.5">
        Tracing the retrieval pipeline
      </p>

      {/* Trace bars — one per visible agent */}
      <div className="space-y-2">
        {visibleAgents.map(({ name, label }) => {
          const status = statusFor(steps, name);
          return (
            <div key={name} className="flex items-center gap-3">
              <span
                className={clsx(
                  'text-[10px] font-semibold uppercase tracking-wider w-20 shrink-0 transition-colors',
                  status === 'active' && 'text-lumina-600 dark:text-lumina-400 font-bold',
                  status === 'complete' && 'text-slate-800 dark:text-slate-200',
                  status === 'skipped' && 'text-slate-400 line-through',
                  status === 'pending' && 'text-slate-400 opacity-50',
                )}
              >
                {label}
              </span>
              <div className="h-1.5 flex-1 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden relative" aria-hidden="true">
                {status === 'complete' && (
                  <div className="h-full bg-slate-700 dark:bg-slate-300 w-full" />
                )}
                {status === 'active' && (
                  <div
                    className="h-full bg-lumina-600 animate-pulse w-full"
                  />
                )}
                {status === 'skipped' && (
                  <div className="absolute inset-0 bg-slate-300 dark:bg-slate-700 opacity-40" />
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Current step caption */}
      {activeStep?.message && (
        <p className="mt-3 text-xs font-mono text-lumina-600 dark:text-lumina-400">
          → {activeStep.message}
        </p>
      )}
    </div>
  );
}

export default AgentTrace;
