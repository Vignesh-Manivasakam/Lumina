"use client";

import React, { useState, useEffect, useRef } from 'react';
import {
  Sparkles,
  X,
  Plus,
  Trash2,
  Lock,
  Globe,
  Upload,
  Search,
  CheckCircle2,
  AlertCircle,
  Brain,
  Scale,
  Activity,
  DollarSign,
  Code2,
  FileSpreadsheet,
  FileText,
  Palette,
  Loader2,
} from 'lucide-react';
import { SkillItem } from '../lib/types';
import { fetchSkills, createCustomSkill, deleteCustomSkill } from '../lib/api';

interface SkillsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const CATEGORY_ICONS: Record<string, React.ReactNode> = {
  reasoning: <Brain size={14} className="text-amber-500" />,
  legal: <Scale size={14} className="text-blue-500" />,
  analysis: <Activity size={14} className="text-emerald-500" />,
  financial: <DollarSign size={14} className="text-emerald-600" />,
  coding: <Code2 size={14} className="text-purple-500" />,
  data: <FileSpreadsheet size={14} className="text-cyan-500" />,
  briefing: <FileText size={14} className="text-indigo-500" />,
  creative: <Palette size={14} className="text-pink-500" />,
  search: <Globe size={14} className="text-sky-500" />,
};

const STARTER_TEMPLATE = `---
name: custom-expert
category: analysis
title: "Custom Domain Specialist"
description: "Specialized analysis protocol for my domain."
triggers:
  - "analyze domain"
  - "custom check"
tags: [domain, custom, analysis]
confidence_threshold: 0.65
---
# Custom Domain Specialist Protocol

## Instructions:
1. Provide deep domain analysis.
2. Structure output into Executive Summary, Findings Table, and Action Items.
`;

export function SkillsModal({ isOpen, onClose }: SkillsModalProps) {
  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'browse' | 'add'>('browse');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  
  // Custom skill creation state
  const [customMarkdown, setCustomMarkdown] = useState(STARTER_TEMPLATE);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadSkills = async () => {
    setLoading(true);
    try {
      const data = await fetchSkills();
      setSkills(data);
    } catch (err: any) {
      console.error('Failed to load skills:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadSkills();
      setStatusMsg(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      if (text) {
        setCustomMarkdown(text);
        setActiveTab('add');
      }
    };
    reader.readAsText(file);
  };

  const handleCreateSkill = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setStatusMsg(null);
    try {
      const res = await createCustomSkill(customMarkdown);
      setStatusMsg({ type: 'success', text: res.message || 'Custom skill registered for your session!' });
      await loadSkills();
      setTimeout(() => {
        setActiveTab('browse');
        setStatusMsg(null);
      }, 1500);
    } catch (err: any) {
      setStatusMsg({ type: 'error', text: err.message || 'Failed to create skill.' });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteSkill = async (skillName: string) => {
    if (!confirm(`Are you sure you want to delete custom skill "${skillName}"?`)) return;
    try {
      await deleteCustomSkill(skillName);
      await loadSkills();
    } catch (err: any) {
      alert(err.message || 'Failed to delete skill');
    }
  };

  const categories = ['all', ...Array.from(new Set(skills.map((s) => s.category)))];

  const filteredSkills = skills.filter((skill) => {
    const matchesCategory = selectedCategory === 'all' || skill.category === selectedCategory;
    const matchesSearch =
      skill.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (skill.title && skill.title.toLowerCase().includes(searchQuery.toLowerCase())) ||
      skill.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (skill.tags && skill.tags.some((t) => t.toLowerCase().includes(searchQuery.toLowerCase())));
    return matchesCategory && matchesSearch;
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-200">
      <div
        className="w-full max-w-3xl max-h-[85vh] flex flex-col rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800/80 flex items-center justify-between bg-slate-50/50 dark:bg-slate-900/50">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-lumina-500/10 text-lumina-600 dark:text-lumina-400">
              <Sparkles size={18} />
            </div>
            <div>
              <h3 className="font-semibold text-slate-900 dark:text-white text-base">
                Lumina Cognitive Skills Hub
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Dynamic Markdown reasoning protocols & domain specialists
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Tabs */}
            <div className="flex p-0.5 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60">
              <button
                onClick={() => setActiveTab('browse')}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-all ${
                  activeTab === 'browse'
                    ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-2xs'
                    : 'text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
                }`}
              >
                Browse ({skills.length})
              </button>
              <button
                onClick={() => setActiveTab('add')}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-all flex items-center gap-1 ${
                  activeTab === 'add'
                    ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-2xs'
                    : 'text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'
                }`}
              >
                <Plus size={12} /> Add Custom Skill
              </button>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === 'browse' ? (
            <div className="space-y-4">
              {/* Search & Category Filter */}
              <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center justify-between">
                <div className="relative flex-1">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search by skill name, trigger, or tag..."
                    className="w-full pl-9 pr-3 py-1.5 text-xs rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 text-slate-900 dark:text-white placeholder-slate-400 focus:outline-hidden focus:ring-2 focus:ring-lumina-500/20"
                  />
                </div>

                <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
                  {categories.map((cat) => (
                    <button
                      key={cat}
                      onClick={() => setSelectedCategory(cat)}
                      className={`px-2.5 py-1 text-[11px] font-medium rounded-lg capitalize shrink-0 transition-colors ${
                        selectedCategory === cat
                          ? 'bg-lumina-600 text-white'
                          : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
                      }`}
                    >
                      {cat}
                    </button>
                  ))}
                </div>
              </div>

              {/* Skills Grid */}
              {loading ? (
                <div className="flex flex-col items-center justify-center py-12 text-slate-400">
                  <Loader2 size={24} className="animate-spin mb-2 text-lumina-500" />
                  <p className="text-xs">Loading registered skills...</p>
                </div>
              ) : filteredSkills.length === 0 ? (
                <div className="text-center py-12 text-slate-400">
                  <Brain size={32} className="mx-auto mb-2 opacity-40" />
                  <p className="text-sm font-medium">No matching skills found</p>
                  <p className="text-xs text-slate-500 mt-1">Try another search or add a custom skill.</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {filteredSkills.map((skill) => (
                    <div
                      key={skill.name}
                      className="p-4 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-800/40 hover:border-lumina-500/40 dark:hover:border-lumina-500/40 transition-all flex flex-col justify-between group shadow-2xs"
                    >
                      <div>
                        <div className="flex items-start justify-between gap-2 mb-1.5">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="p-1 rounded-md bg-slate-100 dark:bg-slate-700/60 text-slate-600 dark:text-slate-300">
                              {CATEGORY_ICONS[skill.category] || <Brain size={13} />}
                            </span>
                            <span className="font-semibold text-xs text-slate-900 dark:text-white">
                              {skill.title || skill.name}
                            </span>
                          </div>

                          <div className="flex items-center gap-1">
                            {skill.is_custom ? (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
                                <Lock size={9} /> Session
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[10px] font-medium bg-lumina-500/10 text-lumina-600 dark:text-lumina-400 border border-lumina-500/20">
                                <Globe size={9} /> System
                              </span>
                            )}

                            {skill.is_custom && (
                              <button
                                onClick={() => handleDeleteSkill(skill.name)}
                                className="p-1 text-slate-400 hover:text-red-500 transition-colors"
                                title="Delete session skill"
                              >
                                <Trash2 size={12} />
                              </button>
                            )}
                          </div>
                        </div>

                        <p className="text-xs text-slate-600 dark:text-slate-300 line-clamp-2 mb-2 leading-relaxed">
                          {skill.description}
                        </p>
                      </div>

                      {/* Triggers / Tags */}
                      <div className="pt-2 border-t border-slate-100 dark:border-slate-800/60 flex items-center justify-between text-[10px] text-slate-400">
                        <span className="capitalize font-medium text-slate-500 dark:text-slate-400">
                          {skill.category}
                        </span>
                        {skill.triggers && skill.triggers.length > 0 && (
                          <span className="truncate max-w-[180px]" title={skill.triggers.join(', ')}>
                            Triggers: {skill.triggers.slice(0, 2).join(', ')}
                            {skill.triggers.length > 2 && '...'}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            /* Add Custom Skill Form */
            <form onSubmit={handleCreateSkill} className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-semibold text-slate-900 dark:text-white">
                    Add Session-Scoped Custom Skill
                  </h4>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Custom Markdown skills are private to your active session (<Lock size={10} className="inline" />{' '}
                    Isolated).
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".md,.markdown"
                    onChange={handleFileUpload}
                    className="hidden"
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    className="px-2.5 py-1 text-xs font-medium rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 flex items-center gap-1.5 transition-colors"
                  >
                    <Upload size={12} /> Upload .md
                  </button>
                </div>
              </div>

              {statusMsg && (
                <div
                  className={`p-3 rounded-xl text-xs flex items-center gap-2 ${
                    statusMsg.type === 'success'
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                      : 'bg-red-500/10 text-red-600 dark:text-red-400 border border-red-500/20'
                  }`}
                >
                  {statusMsg.type === 'success' ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                  {statusMsg.text}
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Markdown Skill Definition (YAML Frontmatter + Prompt Protocol)
                </label>
                <textarea
                  value={customMarkdown}
                  onChange={(e) => setCustomMarkdown(e.target.value)}
                  rows={14}
                  required
                  placeholder="---&#10;name: my-skill&#10;category: analysis&#10;title: 'My Custom Skill'&#10;triggers:&#10;  - 'my trigger'&#10;---&#10;# Protocol..."
                  className="w-full p-3 font-mono text-xs rounded-xl bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden focus:ring-2 focus:ring-lumina-500/20 leading-relaxed resize-y"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setActiveTab('browse')}
                  className="px-4 py-1.5 text-xs font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting || !customMarkdown.trim()}
                  className="px-4 py-1.5 text-xs font-medium text-white bg-lumina-600 hover:bg-lumina-700 disabled:opacity-50 rounded-xl transition-colors flex items-center gap-1.5 shadow-sm"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 size={13} className="animate-spin" /> Registering...
                    </>
                  ) : (
                    <>
                      <Plus size={13} /> Save Custom Skill
                    </>
                  )}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

export default SkillsModal;
