"use client";

import React from 'react';
import { Message } from '../lib/types';
import { MessageItem } from './MessageItem';
import { EmptyState } from './EmptyState';

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
  messagesEndRef: React.RefObject<HTMLDivElement>;
  onSelectPrompt?: (prompt: string) => void;
}

export function MessageList({
  messages,
  isStreaming,
  messagesEndRef,
  onSelectPrompt,
}: MessageListProps) {
  if (messages.length === 0) {
    return (
      <div className="w-full">
        <EmptyState onSelectPrompt={onSelectPrompt} />
        <div ref={messagesEndRef} />
      </div>
    );
  }

  const latestAssistantId = [...messages]
    .reverse()
    .find((m) => m.role === 'assistant')?.id;

  return (
    <div className="max-w-3xl mx-auto px-4 md:px-6 py-6 md:py-8">
      <div className="space-y-8">
        {messages.map((msg) => (
          <MessageItem
            key={msg.id}
            message={msg}
            isStreaming={isStreaming}
            isLatestAssistant={msg.id === latestAssistantId}
          />
        ))}
      </div>
      <div ref={messagesEndRef} className="h-6" />
    </div>
  );
}

export default MessageList;
