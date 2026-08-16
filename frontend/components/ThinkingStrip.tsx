'use client';

import React from 'react';
import { ThinkingEvent } from '../lib/types';
import { ThinkingArea } from './ThinkingArea';

interface ThinkingStripProps {
  events: ThinkingEvent[];
  isStreaming?: boolean;
}

export function ThinkingStrip({ events, isStreaming }: ThinkingStripProps) {
  if (!events || events.length === 0) return null;
  return <ThinkingArea events={events} isStreaming={isStreaming} />;
}

export default ThinkingStrip;
