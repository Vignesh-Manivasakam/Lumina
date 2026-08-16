"use client";

import React from 'react';
import clsx from 'clsx';
import { AgentName, AgentStatus } from '../lib/types';

interface AgentBadgeProps {
  agent: AgentName;
  status: AgentStatus;
  /** Optional size variant. */
  size?: 'sm' | 'md';
}

const AGENT_CONFIG: Record<AgentName, { label: string; colorActive: string; colorDone: string; icon: string }> = {
  router:    { label: 'Route',    colorActive: 'badge-routing',     colorDone: 'badge-done', icon: '⎋' },
  retriever: { label: 'Retrieve', colorActive: 'badge-retrieving',  colorDone: 'badge-done', icon: '⊞' },
  grader:    { label: 'Grade',    colorActive: 'badge-grading',     colorDone: 'badge-done', icon: '✦' },
  rewriter:  { label: 'Rewrite',  colorActive: 'badge-rewriting',   colorDone: 'badge-done', icon: '↻' },
  generator: { label: 'Generate', colorActive: 'badge-generating',  colorDone: 'badge-done', icon: '◈' },
};

export function AgentBadge({ agent, status, size = 'sm' }: AgentBadgeProps) {
  const config = AGENT_CONFIG[agent];
  if (!config) return null;

  const isActive = status === 'active';
  const isComplete = status === 'complete';
  const isSkipped = status === 'skipped';
  const isPending = status === 'pending';

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full font-mono transition-all duration-300',
        size === 'sm' ? 'px-2 py-0.5 text-[10px]' : 'px-3 py-1 text-xs',
        isActive && `${config.colorActive} badge-pulse`,
        isComplete && config.colorDone,
        isSkipped && 'badge-skipped',
        isPending && 'badge-pending',
      )}
      role="status"
      aria-label={`${config.label}: ${status}`}
    >
      {/* Status indicator */}
      <span className={clsx(
        'inline-block rounded-full',
        size === 'sm' ? 'w-1.5 h-1.5' : 'w-2 h-2',
        isActive && 'bg-current animate-pulse',
        isComplete && 'bg-current',
        isSkipped && 'bg-current opacity-40',
        isPending && 'bg-current opacity-20',
      )} />

      {/* Icon */}
      <span className="opacity-70">{config.icon}</span>

      {/* Label */}
      <span className="font-semibold tracking-wider uppercase">
        {config.label}
      </span>

      {/* Completion checkmark */}
      {isComplete && (
        <svg
          className="w-3 h-3 badge-check-enter"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        >
          <path d="M3.5 8.5L6.5 11.5L12.5 4.5" />
        </svg>
      )}
    </span>
  );
}

export default AgentBadge;
