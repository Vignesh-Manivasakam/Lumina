"use client";

import React, { useState } from 'react';
import { Check, Copy } from 'lucide-react';

interface TableData {
  headers: string[];
  rows: string[][];
}

interface MarkdownRendererProps {
  content: string;
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  if (!content) return null;

  const elements = parseMarkdown(content);
  return <div className="space-y-4 font-sans text-sm md:text-base text-slate-800 dark:text-slate-200 leading-[1.7]">{elements}</div>;
}

function parseMarkdown(content: string): React.ReactNode[] {
  const lines = content.split('\n');
  const nodes: React.ReactNode[] = [];
  let currentTable: TableData | null = null;
  let codeBlock: { language: string; lines: string[] } | null = null;
  let textBuffer: string[] = [];

  const flushTextBuffer = (key: string) => {
    if (textBuffer.length > 0) {
      const text = textBuffer.join('\n').trim();
      if (text) {
        nodes.push(
          <div key={key} className="space-y-2.5">
            {text.split('\n\n').map((paragraph, pIdx) => {
              // Check if heading
              if (paragraph.startsWith('### ')) {
                return (
                  <h3 key={pIdx} className="font-display font-semibold text-base md:text-lg text-slate-900 dark:text-white mt-4 mb-2">
                    {renderInline(paragraph.slice(4))}
                  </h3>
                );
              }
              if (paragraph.startsWith('## ')) {
                return (
                  <h2 key={pIdx} className="font-display font-semibold text-lg md:text-xl text-slate-900 dark:text-white mt-5 mb-2.5">
                    {renderInline(paragraph.slice(3))}
                  </h2>
                );
              }
              if (paragraph.startsWith('# ')) {
                return (
                  <h1 key={pIdx} className="font-display font-bold text-xl md:text-2xl text-slate-900 dark:text-white mt-6 mb-3">
                    {renderInline(paragraph.slice(2))}
                  </h1>
                );
              }
              // Check if blockquote
              if (paragraph.startsWith('> ')) {
                const quoteText = paragraph
                  .split('\n')
                  .map((l) => (l.startsWith('> ') ? l.slice(2) : l))
                  .join(' ');
                return (
                  <blockquote key={pIdx} className="my-3 pl-4 border-l-2 border-lumina-500 italic text-slate-600 dark:text-slate-400 text-sm">
                    {renderInline(quoteText)}
                  </blockquote>
                );
              }
              // Check if bullet list
              if (paragraph.split('\n').some((l) => l.trim().startsWith('- ') || l.trim().startsWith('* '))) {
                const listItems = paragraph.split('\n');
                return (
                  <ul key={pIdx} className="list-none space-y-1.5 my-3 pl-2">
                    {listItems.map((li, liIdx) => {
                      const trimmed = li.trim();
                      const itemContent = trimmed.replace(/^[-*]\s+/, '');
                      return (
                        <li key={liIdx} className="flex items-start gap-2.5 text-sm text-slate-700 dark:text-slate-300">
                          <span className="text-lumina-600 font-mono text-xs mt-1 shrink-0">❖</span>
                          <span>{renderInline(itemContent)}</span>
                        </li>
                      );
                    })}
                  </ul>
                );
              }
              // Normal paragraph
              return (
                <p
                  key={pIdx}
                  className="text-slate-800 dark:text-slate-200 leading-relaxed text-sm md:text-base"
                >
                  {renderInline(paragraph)}
                </p>
              );
            })}
          </div>,
        );
      }
      textBuffer = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Fenced Code block toggle
    if (line.trim().startsWith('```')) {
      if (codeBlock === null) {
        flushTextBuffer(`pre-code-${i}`);
        const lang = line.trim().slice(3).trim();
        codeBlock = { language: lang || 'text', lines: [] };
      } else {
        nodes.push(
          <CodeBlockView
            key={`code-${i}`}
            language={codeBlock.language}
            code={codeBlock.lines.join('\n')}
          />,
        );
        codeBlock = null;
      }
      continue;
    }

    if (codeBlock !== null) {
      codeBlock.lines.push(line);
      continue;
    }

    // Table parsing
    const trimmedLine = line.trim();
    if (trimmedLine.startsWith('|') && trimmedLine.endsWith('|')) {
      const cells = trimmedLine.split('|').map((c) => c.trim()).slice(1, -1);

      if (currentTable === null) {
        const nextLine = lines[i + 1]?.trim();
        if (nextLine && nextLine.startsWith('|') && nextLine.includes('---')) {
          currentTable = { headers: cells, rows: [] };
          i++; // Skip delimiter line
          flushTextBuffer(`pre-table-${i}`);
        } else {
          textBuffer.push(line);
        }
      } else {
        currentTable.rows.push(cells);
      }
    } else {
      if (currentTable !== null) {
        nodes.push(renderVisualTable(currentTable, `table-${i}`));
        currentTable = null;
      }
      textBuffer.push(line);
    }
  }

  if (codeBlock !== null) {
    nodes.push(
      <CodeBlockView
        key="code-end"
        language={codeBlock.language}
        code={codeBlock.lines.join('\n')}
      />,
    );
  }

  if (currentTable !== null) {
    nodes.push(renderVisualTable(currentTable, 'table-end'));
  }

  flushTextBuffer('text-end');
  return nodes;
}

function renderInline(text: string): React.ReactNode {
  if (!text) return '';

  // Process bold (**text**), italic (*text*), inline code (`code`), links ([title](url))
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let keyIdx = 0;

  // Regex pattern for bold, code, and link
  const tokenRegex = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|\*[^*]+\*)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenRegex.exec(remaining)) !== null) {
    if (match.index > lastIndex) {
      parts.push(remaining.substring(lastIndex, match.index));
    }

    const token = match[0];
    if (token.startsWith('**') && token.endsWith('**')) {
      parts.push(
        <strong key={`b-${keyIdx++}`} className="font-semibold text-slate-900 dark:text-white font-sans">
          {token.slice(2, -2)}
        </strong>,
      );
    } else if (token.startsWith('`') && token.endsWith('`')) {
      parts.push(
        <code
          key={`c-${keyIdx++}`}
          className="font-mono text-xs bg-slate-100 dark:bg-slate-800 text-lumina-600 dark:text-lumina-400 px-1.5 py-0.5 rounded border border-slate-200 dark:border-slate-700 mx-0.5"
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith('*') && token.endsWith('*')) {
      parts.push(
        <em key={`i-${keyIdx++}`} className="italic text-slate-700 dark:text-slate-300">
          {token.slice(1, -1)}
        </em>,
      );
    } else if (token.startsWith('[') && token.includes('](')) {
      const closeBracket = token.indexOf('](');
      const label = token.slice(1, closeBracket);
      const url = token.slice(closeBracket + 2, -1);
      parts.push(
        <a
          key={`a-${keyIdx++}`}
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-lumina-600 hover:text-lumina-700 underline transition-colors font-medium"
        >
          {label}
        </a>,
      );
    }

    lastIndex = tokenRegex.lastIndex;
  }

  if (lastIndex < remaining.length) {
    parts.push(remaining.substring(lastIndex));
  }

  return parts.length > 0 ? parts : text;
}

function CodeBlockView({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-4 rounded-xl border border-slate-800 bg-slate-950 text-slate-100 overflow-hidden shadow-sm">
      <div className="flex items-center justify-between px-4 py-2 bg-slate-900 border-b border-slate-800 text-xs font-mono text-slate-400">
        <span className="uppercase text-[10px] tracking-wider text-slate-400">{language || 'code'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 hover:text-slate-200 transition-colors text-[11px]"
          title="Copy code"
        >
          {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>
      <pre className="p-4 text-xs md:text-sm font-mono overflow-x-auto leading-relaxed text-slate-200">
        <code>{code}</code>
      </pre>
    </div>
  );
}

function renderVisualTable(table: TableData, key: string): React.ReactNode {
  return (
    <div
      key={key}
      className="my-5 overflow-x-auto border border-[#DCE5F2] dark:border-slate-800 bg-white dark:bg-slate-900 rounded-xl shadow-2xs"
    >
      <table className="w-full text-left border-collapse text-xs">
        <thead>
          <tr className="border-b border-[#EDF3FA] dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 text-slate-700 dark:text-slate-300">
            {table.headers.map((h, i) => (
              <th
                key={i}
                className="p-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400"
              >
                {h.replace(/\*\*/g, '')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-[#EDF3FA] dark:divide-slate-800 text-slate-800 dark:text-slate-200">
          {table.rows.map((row, idx) => (
            <tr key={idx} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
              {row.map((cell, cIdx) => (
                <td key={cIdx} className="p-3 font-sans text-xs leading-relaxed">
                  {renderInline(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default MarkdownRenderer;
