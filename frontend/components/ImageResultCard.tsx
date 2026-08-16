"use client";

import React, { useState } from 'react';
import { Download, Eye, Sparkles, X } from 'lucide-react';
import { ImageResult } from '../lib/types';

interface ImageResultCardProps {
  imageResult: ImageResult;
}

export function ImageResultCard({ imageResult }: ImageResultCardProps) {
  const [modalOpen, setModalOpen] = useState(false);

  if (!imageResult || !imageResult.image_b64) return null;

  const imageUrl =
    imageResult.image_b64.startsWith('http') || imageResult.image_b64.startsWith('data:')
      ? imageResult.image_b64
      : `data:image/png;base64,${imageResult.image_b64}`;

  const handleDownload = () => {
    const link = document.createElement('a');
    link.href = imageUrl;
    link.download = `lumina-gen-${Date.now()}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <>
      <div className="mt-5 border border-[#DCE5F2] dark:border-slate-800 bg-white dark:bg-slate-900 p-4 rounded-2xl shadow-sm animate-fade-up">
        <div className="flex items-center justify-between pb-3 mb-3 border-b border-[#EDF3FA] dark:border-slate-800">
          <div className="flex items-center gap-2">
            <Sparkles size={15} className="text-lumina-600" />
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-800 dark:text-slate-200">
              Visual Generation
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setModalOpen(true)}
              className="p-1.5 text-slate-400 hover:text-lumina-600 transition-colors rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
              title="View full image"
            >
              <Eye size={15} />
            </button>
            <button
              onClick={handleDownload}
              className="p-1.5 text-slate-400 hover:text-lumina-600 transition-colors rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
              title="Download image"
            >
              <Download size={15} />
            </button>
          </div>
        </div>

        <div className="relative group cursor-pointer overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 flex items-center justify-center max-h-80">
          <img
            src={imageUrl}
            alt={imageResult.prompt || 'Generated visualization'}
            onClick={() => setModalOpen(true)}
            className="w-full h-auto max-h-80 object-contain transition-transform duration-300 group-hover:scale-[1.01]"
          />
        </div>

        <div className="mt-3 space-y-1">
          {imageResult.refined_prompt && (
            <p className="text-xs font-mono text-slate-700 dark:text-slate-300 leading-relaxed">
              <span className="text-lumina-600 font-semibold mr-1.5">Prompt:</span>
              <span className="italic">{imageResult.refined_prompt}</span>
            </p>
          )}
          {imageResult.prompt && imageResult.prompt !== imageResult.refined_prompt && (
            <p className="text-[11px] font-mono text-slate-400">
              <span className="mr-1">Original:</span>
              <span>{imageResult.prompt}</span>
            </p>
          )}
        </div>
      </div>

      {/* Fullscreen Modal View */}
      {modalOpen && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/80 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setModalOpen(false)}
        >
          <div
            className="relative max-w-4xl max-h-[90vh] bg-white dark:bg-slate-900 border border-[#DCE5F2] dark:border-slate-800 rounded-2xl shadow-2xl p-5 flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-3 border-b border-[#EDF3FA] dark:border-slate-800">
              <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                Lumina Generated Artwork
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleDownload}
                  className="p-1.5 text-slate-400 hover:text-lumina-600 transition-colors rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
                  title="Download image"
                >
                  <Download size={16} />
                </button>
                <button
                  onClick={() => setModalOpen(false)}
                  className="p-1.5 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
                  title="Close preview"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-auto py-4 flex items-center justify-center">
              <img
                src={imageUrl}
                alt={imageResult.prompt || 'Generated visualization'}
                className="max-w-full max-h-[70vh] object-contain rounded-xl shadow"
              />
            </div>
            {imageResult.refined_prompt && (
              <p className="text-xs font-mono text-slate-500 dark:text-slate-400 pt-2 border-t border-[#EDF3FA] dark:border-slate-800">
                {imageResult.refined_prompt}
              </p>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export default ImageResultCard;
