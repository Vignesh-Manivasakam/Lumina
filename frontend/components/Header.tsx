"use client";

import React from 'react';
import {
  Menu,
  Moon,
  Sparkles,
  Sun,
  X,
} from 'lucide-react';
import { Conversation } from '../lib/types';

interface HeaderProps {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  sessionUUID?: string;
  activeConversation?: Conversation | null;
  darkMode?: boolean;
  onToggleDarkMode?: () => void;
  onOpenSkillsModal?: () => void;
}

export function Header({
  sidebarOpen,
  setSidebarOpen,
  activeConversation,
  darkMode = false,
  onToggleDarkMode,
  onOpenSkillsModal,
}: HeaderProps) {
  return (
    <header className="h-16 px-4 md:px-8 flex items-center justify-between shrink-0 select-none bg-transparent border-b border-[#EDF3FA] dark:border-slate-800/80">
      {/* Left side: Hamburger on mobile + active conversation indicator */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="lg:hidden p-2 rounded-xl text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          aria-label="Toggle sidebar"
        >
          {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
        </button>

        {activeConversation && activeConversation.title !== 'New Conversation' && (
          <div className="hidden sm:flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <span className="w-1.5 h-1.5 rounded-full bg-lumina-600" />
            <span className="font-medium text-slate-800 dark:text-slate-200 truncate max-w-sm">
              {activeConversation.title}
            </span>
          </div>
        )}
      </div>

      {/* Right side: Skills Hub button & Dark / Light Mode Toggle */}
      <div className="flex items-center gap-2">
        {onOpenSkillsModal && (
          <button
            onClick={onOpenSkillsModal}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium text-slate-700 dark:text-slate-200 hover:text-lumina-600 dark:hover:text-lumina-400 hover:bg-white dark:hover:bg-slate-800 transition-all border border-[#EDF3FA] dark:border-slate-800 hover:border-[#DCE5F2] dark:hover:border-slate-700 shadow-2xs"
            title="Manage Cognitive Skills & Add Custom Skills"
          >
            <Sparkles size={14} className="text-lumina-500" />
            <span className="hidden sm:inline">Cognitive Skills</span>
          </button>
        )}

        {onToggleDarkMode && (
          <button
            onClick={onToggleDarkMode}
            className="p-2.5 rounded-xl text-slate-500 hover:text-lumina-600 hover:bg-white dark:hover:bg-slate-800 transition-all border border-transparent hover:border-[#DCE5F2] dark:hover:border-slate-700 shadow-2xs"
            title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
            aria-label="Toggle theme"
          >
            {darkMode ? <Sun size={17} /> : <Moon size={17} />}
          </button>
        )}
      </div>
    </header>
  );
}

export default Header;
