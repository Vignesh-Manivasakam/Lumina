"use client";

import React, { useRef, useState, useEffect } from 'react';
import {
  ChevronDown,
  Cpu,
  File,
  FileCode,
  FileSpreadsheet,
  FileText,
  Globe,
  Loader2,
  Mic,
  MicOff,
  Paperclip,
  Send,
  Sparkles,
  Zap,
  X,
} from 'lucide-react';
import clsx from 'clsx';
import { FileAttachment } from '../lib/types';
import { transcribeAudio } from '../lib/api';

export interface ModelOption {
  id: string;
  name: string;
  badge: string;
  provider: string;
  icon: string;
}

export const AVAILABLE_MODELS: ModelOption[] = [
  {
    id: 'gemini-flash-latest',
    name: 'Gemini Flash',
    badge: 'Multimodal',
    provider: 'Google Studio',
    icon: '⚡',
  },
  {
    id: 'nvidia/nemotron-mini-4b-instruct',
    name: 'NVIDIA Nemotron',
    badge: 'Reasoning',
    provider: 'NVIDIA NIM',
    icon: '🧠',
  },
  {
    id: 'llama-3.3-70b-versatile',
    name: 'Groq Llama 3.3',
    badge: 'Ultra-Fast',
    provider: 'Groq Cloud',
    icon: '🚀',
  },
];

interface ChatInputProps {
  inputQuery: string;
  setInputQuery: React.Dispatch<React.SetStateAction<string>>;
  selectedImage?: string | null;
  setSelectedImage?: (image: string | null) => void;
  attachment: FileAttachment | null;
  setAttachment: (att: FileAttachment | null) => void;
  webSearchMode: 'auto' | 'always' | 'off';
  setWebSearchMode: (mode: 'auto' | 'always' | 'off') => void;
  selectedModel: string;
  setSelectedModel: (modelId: string) => void;
  onSendMessage: () => void;
  isStreaming: boolean;
  onError?: (err: string) => void;
}

export function ChatInput({
  inputQuery,
  setInputQuery,
  selectedImage,
  setSelectedImage,
  attachment,
  setAttachment,
  webSearchMode,
  setWebSearchMode,
  selectedModel,
  setSelectedModel,
  onSendMessage,
  isStreaming,
  onError,
}: ChatInputProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [isWebMenuOpen, setIsWebMenuOpen] = useState(false);
  const [isModelMenuOpen, setIsModelMenuOpen] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-grow textarea smoothly
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [inputQuery]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const fileName = file.name;
    const fileSize = file.size;
    const mimeType = file.type;
    const ext = fileName.split('.').pop()?.toLowerCase() || '';

    if (file.type.startsWith('image/')) {
      const reader = new FileReader();
      reader.onload = () => {
        const base64Str = (reader.result as string).split(',')[1];
        setAttachment({
          name: fileName,
          type: 'image',
          size: fileSize,
          b64: base64Str,
          mimeType,
        });
        if (setSelectedImage) setSelectedImage(base64Str);
      };
      reader.readAsDataURL(file);
    } else if (
      ext === 'txt' ||
      ext === 'md' ||
      ext === 'csv' ||
      ext === 'json' ||
      ext === 'py' ||
      ext === 'js' ||
      ext === 'ts' ||
      ext === 'html' ||
      ext === 'css'
    ) {
      // Read plain text directly
      const reader = new FileReader();
      reader.onload = () => {
        const content = reader.result as string;
        setAttachment({
          name: fileName,
          type: ext === 'csv' ? 'sheet' : ext === 'py' || ext === 'js' || ext === 'ts' ? 'code' : 'text',
          size: fileSize,
          content,
          mimeType,
        });
      };
      reader.readAsText(file);
    } else {
      // Binary document (PDF, DOCX, XLSX, PPTX)
      const reader = new FileReader();
      reader.onload = () => {
        const base64Str = (reader.result as string).split(',')[1];
        setAttachment({
          name: fileName,
          type: ext === 'pdf' ? 'pdf' : ext === 'docx' ? 'docx' : ext === 'xlsx' ? 'sheet' : 'document',
          size: fileSize,
          b64: base64Str,
          content: `[Attached File: ${fileName} (${(fileSize / 1024).toFixed(1)} KB)]`,
          mimeType,
        });
      };
      reader.readAsDataURL(file);
    }

    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const clearAttachment = () => {
    setAttachment(null);
    if (setSelectedImage) setSelectedImage(null);
  };

  const startVoiceRecording = async () => {
    if (typeof window === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      onError?.('Voice recording is not supported in this browser environment');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
        stream.getTracks().forEach((track) => track.stop());

        if (audioBlob.size > 0) {
          setIsTranscribing(true);
          try {
            const result = await transcribeAudio(audioBlob, 'wav');
            if (result && result.text) {
              setInputQuery((prev) => (prev ? `${prev} ${result.text}` : result.text));
            }
          } catch (err: unknown) {
            const message = err instanceof Error ? err.message : String(err);
            onError?.(`Transcription failed: ${message}`);
          } finally {
            setIsTranscribing(false);
          }
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      onError?.(`Could not access microphone: ${message}`);
    }
  };

  const stopVoiceRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isStreaming && (inputQuery.trim() || attachment || selectedImage)) {
        onSendMessage();
      }
    }
  };

  const getAttachmentIcon = () => {
    if (!attachment) return null;
    if (attachment.type === 'pdf') return <FileText size={16} className="text-red-500" />;
    if (attachment.type === 'sheet') return <FileSpreadsheet size={16} className="text-emerald-600" />;
    if (attachment.type === 'code') return <FileCode size={16} className="text-lumina-600" />;
    if (attachment.type === 'docx' || attachment.type === 'text') return <FileText size={16} className="text-lumina-600" />;
    return <File size={16} className="text-slate-500" />;
  };

  const currentModelInfo = AVAILABLE_MODELS.find((m) => m.id === selectedModel) || AVAILABLE_MODELS[0];

  return (
    <div className="relative w-full max-w-4xl mx-auto">
      {/* Attached File Preview Pill */}
      {attachment && (
        <div className="mb-2 p-2 px-3 rounded-xl bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-800 shadow-2xs inline-flex items-center gap-2.5 animate-fade-up max-w-md">
          {attachment.type === 'image' && attachment.b64 ? (
            <img
              src={`data:image/jpeg;base64,${attachment.b64}`}
              alt="Attached preview"
              className="w-8 h-8 object-cover rounded-lg border border-slate-200 dark:border-slate-700"
            />
          ) : (
            <div className="w-8 h-8 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center shrink-0">
              {getAttachmentIcon()}
            </div>
          )}
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate">
              {attachment.name}
            </p>
            <p className="text-[10px] text-slate-400 font-mono">
              {attachment.size ? `${(attachment.size / 1024).toFixed(1)} KB` : 'Attached file'}
            </p>
          </div>
          <button
            onClick={clearAttachment}
            className="w-5 h-5 rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 flex items-center justify-center text-slate-500 hover:text-slate-800 transition-colors"
            title="Remove attachment"
          >
            <X size={12} />
          </button>
        </div>
      )}

      {/* Main Single-Border Card Composer */}
      <div className="bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-800 rounded-2xl shadow-card focus-within:border-lumina-600 focus-within:ring-2 focus-within:ring-lumina-600/10 transition-all p-3">
        {/* Text Area */}
        <textarea
          ref={textareaRef}
          value={inputQuery}
          onChange={(e) => setInputQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question of your archive, attach files, or search..."
          rows={1}
          disabled={isStreaming}
          className="w-full bg-transparent px-2 text-sm text-slate-900 dark:text-white placeholder:text-slate-400 outline-none resize-none max-h-44 leading-relaxed font-sans"
        />

        {/* Action Footer Toolbar */}
        <div className="pt-2.5 flex items-center justify-between gap-2 border-t border-slate-100 dark:border-slate-800/60 mt-1">
          <div className="flex items-center gap-1.5 sm:gap-2 relative flex-wrap">
            {/* 1. Model Selector Dropdown */}
            <div className="relative">
              <button
                type="button"
                onClick={() => {
                  setIsModelMenuOpen(!isModelMenuOpen);
                  setIsWebMenuOpen(false);
                }}
                className="flex items-center gap-2 py-1.5 px-3 rounded-xl bg-slate-100/90 hover:bg-slate-200/80 dark:bg-slate-800 dark:hover:bg-slate-700/80 text-xs font-medium text-slate-800 dark:text-slate-200 transition-all border border-slate-200/60 dark:border-slate-700/60 shadow-2xs cursor-pointer"
                title="Select Active LLM Provider & Model"
              >
                <div className="flex items-center gap-1.5">
                  <span className="font-sans font-semibold tracking-tight text-slate-900 dark:text-white text-xs">
                    {currentModelInfo.name}
                  </span>
                  <span className="text-[10px] font-mono text-slate-400 dark:text-slate-400">
                    ({currentModelInfo.badge})
                  </span>
                </div>
                <ChevronDown size={12} className="text-slate-400" />
              </button>

              {/* Model Dropdown Menu */}
              {isModelMenuOpen && (
                <div
                  className="absolute bottom-full mb-2 left-0 w-64 bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-800 rounded-2xl shadow-xl p-1.5 z-30 space-y-1"
                  onMouseLeave={() => setIsModelMenuOpen(false)}
                >
                  <p className="px-2.5 py-1 text-[10px] font-semibold text-slate-400 uppercase tracking-wider font-mono">
                    Select Active Model
                  </p>
                  {AVAILABLE_MODELS.map((model) => (
                    <button
                      key={model.id}
                      type="button"
                      onClick={() => {
                        setSelectedModel(model.id);
                        setIsModelMenuOpen(false);
                      }}
                      className={clsx(
                        'w-full text-left p-2.5 rounded-xl text-xs transition-all flex items-center justify-between cursor-pointer',
                        selectedModel === model.id
                          ? 'bg-lumina-50 text-lumina-600 dark:bg-lumina-950/50 font-semibold ring-1 ring-lumina-500/20'
                          : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100/80 dark:hover:bg-slate-800/80',
                      )}
                    >
                      <div className="space-y-0.5">
                        <p className="font-sans font-semibold text-xs tracking-tight text-slate-900 dark:text-slate-100">
                          {model.name}
                        </p>
                        <p className="text-[10px] text-slate-400 dark:text-slate-400 font-mono">
                          {model.provider}
                        </p>
                      </div>
                      <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                        {model.badge}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* 2. Web Search Mode Dropdown */}
            <div className="relative">
              <button
                type="button"
                onClick={() => {
                  setIsWebMenuOpen(!isWebMenuOpen);
                  setIsModelMenuOpen(false);
                }}
                className="flex items-center gap-1.5 py-1.5 px-2.5 rounded-xl bg-slate-100/90 hover:bg-slate-200/80 dark:bg-slate-800 dark:hover:bg-slate-700/80 text-xs font-medium text-slate-700 dark:text-slate-200 transition-colors"
              >
                <Globe size={14} className={clsx(webSearchMode === 'always' ? 'text-lumina-600' : 'text-slate-500')} />
                <span>Web: {webSearchMode === 'always' ? 'Always' : webSearchMode === 'off' ? 'Off' : 'Auto'}</span>
                <ChevronDown size={12} className="text-slate-400" />
              </button>

              {/* Web Menu Dropdown */}
              {isWebMenuOpen && (
                <div
                  className="absolute bottom-full mb-2 left-0 w-44 bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-800 rounded-2xl shadow-xl p-1.5 z-30 space-y-0.5"
                  onMouseLeave={() => setIsWebMenuOpen(false)}
                >
                  <button
                    type="button"
                    onClick={() => {
                      setWebSearchMode('auto');
                      setIsWebMenuOpen(false);
                    }}
                    className={clsx(
                      'w-full text-left px-3 py-1.5 rounded-xl text-xs font-medium transition-colors flex items-center justify-between',
                      webSearchMode === 'auto'
                        ? 'bg-lumina-50 text-lumina-600 dark:bg-lumina-950/40'
                        : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800',
                    )}
                  >
                    <span>Auto (Intelligent)</span>
                    {webSearchMode === 'auto' && <span className="w-1.5 h-1.5 rounded-full bg-lumina-600" />}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setWebSearchMode('always');
                      setIsWebMenuOpen(false);
                    }}
                    className={clsx(
                      'w-full text-left px-3 py-1.5 rounded-xl text-xs font-medium transition-colors flex items-center justify-between',
                      webSearchMode === 'always'
                        ? 'bg-lumina-50 text-lumina-600 dark:bg-lumina-950/40'
                        : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800',
                    )}
                  >
                    <span>Always On</span>
                    {webSearchMode === 'always' && <span className="w-1.5 h-1.5 rounded-full bg-lumina-600" />}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setWebSearchMode('off');
                      setIsWebMenuOpen(false);
                    }}
                    className={clsx(
                      'w-full text-left px-3 py-1.5 rounded-xl text-xs font-medium transition-colors flex items-center justify-between',
                      webSearchMode === 'off'
                        ? 'bg-lumina-50 text-lumina-600 dark:bg-lumina-950/40'
                        : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800',
                    )}
                  >
                    <span>Off (Docs Only)</span>
                    {webSearchMode === 'off' && <span className="w-1.5 h-1.5 rounded-full bg-lumina-600" />}
                  </button>
                </div>
              )}
            </div>

            {/* 3. Paperclip (Attach any file: images, PDFs, DOCX, TXT, CSV, Code) */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isStreaming}
              className="p-2 text-slate-500 hover:text-lumina-600 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors"
              title="Attach file (Image, PDF, DOCX, TXT, CSV, Code)"
            >
              <Paperclip size={16} />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              onChange={handleFileSelect}
              className="hidden"
              accept="image/*,.pdf,.docx,.pptx,.txt,.md,.csv,.xlsx,.json,.py,.js,.ts,.html,.css"
            />

            {/* 4. Microphone */}
            <button
              type="button"
              onClick={isRecording ? stopVoiceRecording : startVoiceRecording}
              disabled={isStreaming || isTranscribing}
              className={clsx(
                'p-2 rounded-xl transition-all',
                isRecording
                  ? 'bg-red-500 text-white animate-pulse'
                  : 'text-slate-500 hover:text-lumina-600 hover:bg-slate-100 dark:hover:bg-slate-800',
              )}
              title={isRecording ? 'Stop recording' : 'Voice input'}
            >
              {isTranscribing ? (
                <Loader2 size={16} className="animate-spin text-lumina-600" />
              ) : isRecording ? (
                <MicOff size={16} />
              ) : (
                <Mic size={16} />
              )}
            </button>
          </div>

          {/* Solid Blue Send Button */}
          <button
            type="button"
            onClick={onSendMessage}
            disabled={isStreaming || (!inputQuery.trim() && !attachment && !selectedImage)}
            className="flex items-center gap-2 py-2 px-5 bg-lumina-600 hover:bg-lumina-700 text-white rounded-xl text-xs font-semibold shadow-sm shadow-lumina-600/30 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-95 shrink-0"
          >
            {isStreaming ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Send size={13} />
            )}
            <span>Send</span>
          </button>
        </div>
      </div>
    </div>
  );
}

export default ChatInput;
