"use client";

import React, { useState } from 'react';
import {
  Check,
  Copy,
  Loader2,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { Message } from '../lib/types';
import { MarkdownRenderer } from './MarkdownRenderer';
import { CitationList } from './CitationCard';
import { ThinkingArea } from './ThinkingArea';
import { ImageResultCard } from './ImageResultCard';
import { WebResultsCard } from './WebResultsCard';
import { ToolResultCard } from './ToolResultCard';
import { synthesizeSpeech } from '../lib/api';

interface MessageItemProps {
  message: Message;
  isStreaming?: boolean;
  isLatestAssistant?: boolean;
}

export function MessageItem({
  message,
  isStreaming = false,
  isLatestAssistant = false,
}: MessageItemProps) {
  const [copied, setCopied] = useState(false);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);
  const [audioLoading, setAudioLoading] = useState(false);
  const [activeAudioElement, setActiveAudioElement] = useState<HTMLAudioElement | null>(null);

  const handleCopy = () => {
    if (!message.content) return;
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleVoicePlayback = async () => {
    if (isPlayingAudio && activeAudioElement) {
      activeAudioElement.pause();
      setIsPlayingAudio(false);
      return;
    }

    if (!message.content) return;

    // Clean markdown before speaking
    const plainText = message.content
      .replace(/[*#`_~[\]]/g, '')
      .replace(/\|.*\|/g, '')
      .slice(0, 1000);

    setAudioLoading(true);
    try {
      // 1. Try backend TTS synthesis endpoint
      const audioBlob = await synthesizeSpeech(plainText);
      if (audioBlob && audioBlob.size > 0) {
        const audioUrl = URL.createObjectURL(audioBlob);
        const audio = new Audio(audioUrl);
        setActiveAudioElement(audio);
        audio.onended = () => setIsPlayingAudio(false);
        audio.onerror = () => {
          fallbackSpeechSynthesis(plainText);
        };
        await audio.play();
        setIsPlayingAudio(true);
      } else {
        fallbackSpeechSynthesis(plainText);
      }
    } catch {
      fallbackSpeechSynthesis(plainText);
    } finally {
      setAudioLoading(false);
    }
  };

  const fallbackSpeechSynthesis = (text: string) => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.pitch = 0.95;
    utterance.onend = () => setIsPlayingAudio(false);
    utterance.onerror = () => setIsPlayingAudio(false);
    window.speechSynthesis.speak(utterance);
    setIsPlayingAudio(true);
  };

  return (
    <article className="space-y-3 animate-fade-up">
      {/* Eyebrow role label */}
      <div className="flex items-baseline justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
            {message.role === 'user' ? 'You asked' : 'Lumina replied'}
          </span>
          {message.image_b64 && (
            <span className="text-[10px] font-mono text-lumina-600 bg-lumina-50 dark:bg-lumina-950/40 px-2 py-0.5 rounded-md">
              with attachment
            </span>
          )}
        </div>

        {/* Action icons for assistant responses */}
        {message.role === 'assistant' && message.content && (
          <div className="flex items-center gap-1.5 opacity-70 hover:opacity-100 transition-opacity">
            <button
              onClick={handleVoicePlayback}
              disabled={audioLoading}
              className="p-1.5 text-slate-400 hover:text-lumina-600 transition-colors rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
              title={isPlayingAudio ? 'Stop readout' : 'Read aloud'}
              aria-label="Read aloud"
            >
              {audioLoading ? (
                <Loader2 size={13} className="animate-spin text-lumina-600" />
              ) : isPlayingAudio ? (
                <VolumeX size={13} className="text-lumina-600" />
              ) : (
                <Volume2 size={13} />
              )}
            </button>

            <button
              onClick={handleCopy}
              className="p-1.5 text-slate-400 hover:text-lumina-600 transition-colors rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
              title="Copy message"
              aria-label="Copy message"
            >
              {copied ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
            </button>
          </div>
        )}
      </div>

      {/* User message rendering */}
      {message.role === 'user' && (
        <div className="space-y-3">
          {message.attachment && message.attachment.type === 'image' && message.attachment.b64 && (
            <div className="inline-block p-1.5 bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-800 rounded-xl shadow-xs">
              <img
                src={`data:image/jpeg;base64,${message.attachment.b64}`}
                alt="Your attachment"
                className="max-h-60 max-w-sm object-cover rounded-lg"
              />
            </div>
          )}
          {message.image_b64 && !message.attachment && (
            <div className="inline-block p-1.5 bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-800 rounded-xl shadow-xs">
              <img
                src={`data:image/jpeg;base64,${message.image_b64}`}
                alt="Your attachment"
                className="max-h-60 max-w-sm object-cover rounded-lg"
              />
            </div>
          )}
          {message.attachment && message.attachment.type !== 'image' && (
            <div className="inline-flex items-center gap-2.5 p-2.5 px-3.5 bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-800 rounded-xl shadow-2xs">
              <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                📎 {message.attachment.name}
              </span>
              {message.attachment.size ? (
                <span className="text-[10px] text-slate-400 font-mono">
                  ({(message.attachment.size / 1024).toFixed(1)} KB)
                </span>
              ) : null}
            </div>
          )}
          {message.content && (
            <p className="font-display text-lg text-slate-900 dark:text-white leading-relaxed">
              {message.content}
            </p>
          )}
        </div>
      )}

          {/* Thinking Notes Ledger / Cognitive Hub */}
          {message.thinking && message.thinking.length > 0 && (
            <ThinkingArea
              events={message.thinking}
              isStreaming={Boolean(isStreaming && isLatestAssistant)}
            />
          )}

          {/* Main message text */}
          {message.content ? (
            <MarkdownRenderer content={message.content} />
          ) : (
            isStreaming &&
            isLatestAssistant && (
              <p className="font-display italic text-slate-400 text-base flex items-center gap-2">
                <Loader2 size={15} className="animate-spin text-lumina-600 shrink-0" />
                <span>consulting the shelves…</span>
              </p>
            )
          )}

          {/* Generated Image Result */}
          {message.image_result && (
            <ImageResultCard imageResult={message.image_result} />
          )}

          {/* Web Search Discoveries */}
          {message.web_results && message.web_results.length > 0 && (
            <WebResultsCard results={message.web_results} />
          )}

          {/* Tool Result Card */}
          {message.tool_result && (
            <ToolResultCard toolResult={message.tool_result} />
          )}

          {/* Citations Deckled List */}
          {message.sources && message.sources.length > 0 && (
            <CitationList sources={message.sources} />
          )}
    </article>
  );
}

export default MessageItem;
