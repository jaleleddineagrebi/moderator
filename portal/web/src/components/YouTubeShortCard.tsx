"use client";

import React, { useState } from "react";
import { Play, ExternalLink, Sparkles, Youtube } from "lucide-react";
import { trackEvent } from "@/lib/analytics";

interface YouTubeShortCardProps {
  short: {
    id: string;
    title: string;
    youtubeUrl: string;
    embedUrl: string;
    topic?: string | null;
    hookAngle?: string | null;
  };
  postTitle: string;
}

export function YouTubeShortCard({ short, postTitle }: YouTubeShortCardProps) {
  const [isPlaying, setIsPlaying] = useState(false);

  const handleClick = (action: string) => {
    trackEvent("youtube_short_click", {
      shortId: short.id,
      postTitle,
      action,
    });
  };

  return (
    <aside className="my-8 rounded-2xl border border-sky-100 bg-gradient-to-br from-sky-50/50 via-white to-indigo-50/30 p-6 shadow-sm transition-all hover:shadow-md dark:border-slate-800 dark:from-slate-900/60 dark:to-slate-800/40">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-sky-600 dark:text-sky-400">
        <Sparkles className="h-4 w-4" />
        <span>Companion 45s YouTube Short</span>
      </div>

      <h3 className="mt-2 text-lg font-bold text-slate-900 dark:text-slate-100">
        {short.title || "Daily Brain Bias Check"}
      </h3>
      
      {short.hookAngle && (
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
          {short.hookAngle}
        </p>
      )}

      {/* 9:16 Vertical Short Container */}
      <div className="relative mx-auto mt-4 aspect-[9/16] w-full max-w-[280px] overflow-hidden rounded-2xl bg-black shadow-lg">
        {isPlaying ? (
          <iframe
            src={`${short.embedUrl}?autoplay=1&mute=0&rel=0&loop=1`}
            title={short.title}
            className="h-full w-full border-0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        ) : (
          <div className="group relative h-full w-full cursor-pointer bg-slate-900">
            {/* Fallback YouTube Poster Frame */}
            <img
              src={`https://img.youtube.com/vi/${short.id}/hqdefault.jpg`}
              alt={short.title}
              className="h-full w-full object-cover opacity-85 transition-opacity group-hover:opacity-100"
              loading="lazy"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-black/30" />
            
            {/* Overlay CTA Pill */}
            <div className="absolute top-4 left-4 right-4 rounded-full bg-red-600/90 px-3 py-1 text-center text-xs font-bold text-white shadow-md backdrop-blur-sm">
              🧠 DAILY BRAIN BIAS CHECK
            </div>

            {/* Play Button */}
            <button
              onClick={() => {
                setIsPlaying(true);
                handleClick("play_inline");
              }}
              aria-label="Play Short"
              className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/95 p-4 text-red-600 shadow-xl transition-transform hover:scale-110 active:scale-95"
            >
              <Play className="h-8 w-8 fill-red-600" />
            </button>
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <a
          href={short.youtubeUrl}
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => handleClick("open_youtube_external")}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-red-700 active:scale-[0.98]"
        >
          <Youtube className="h-4 w-4" />
          <span>Watch & Subscribe on YouTube</span>
          <ExternalLink className="h-3.5 w-3.5 opacity-70" />
        </a>

        <span className="text-center text-xs text-slate-500 dark:text-slate-400">
          ⚡ Follow for your daily brain bias check
        </span>
      </div>
    </aside>
  );
}
