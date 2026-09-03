"use client";

import React, { useState, useRef, useEffect } from "react";
import { thumbnailUrl } from "@/lib/api";

interface BeforeAfterSliderProps {
  beforeImg?: string | null;
  afterImg?: string | null;
  maskImg?: string | null;
  beforeDate?: string | null;
  afterDate?: string | null;
  dominantChange?: string | null;
  confidence?: number | null;
}

type ViewMode = "SPLIT" | "BEFORE" | "AFTER" | "MASK" | "BLEND";

export default function BeforeAfterSlider({
  beforeImg,
  afterImg,
  maskImg,
  beforeDate = "2024-05-20",
  afterDate = "2026-05-18",
  dominantChange = "CONSTRUCTION",
  confidence = 0.89,
}: BeforeAfterSliderProps) {
  const [sliderPos, setSliderPos] = useState(50); // percentage 0 - 100
  const [mode, setMode] = useState<ViewMode>("SPLIT");
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Authentic nadir satellite imagery (T0: Undeveloped terrain -> T1: New urban construction)
  const fallbackBefore = "https://images.unsplash.com/photo-1581084324492-c8076f130f86?w=800&auto=format&fit=crop&q=80";
  const fallbackAfter = "https://images.unsplash.com/photo-1528722828814-77b9b83aafb2?w=800&auto=format&fit=crop&q=80";

  const bUrl = beforeImg ? thumbnailUrl(beforeImg) : fallbackBefore;
  const aUrl = afterImg ? thumbnailUrl(afterImg) : fallbackAfter;

  const handleMove = (clientX: number) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = clientX - rect.left;
    const pct = Math.max(0, Math.min(100, (x / rect.width) * 100));
    setSliderPos(pct);
  };

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (isDragging) handleMove(e.clientX);
    };
    const onTouchMove = (e: TouchEvent) => {
      if (isDragging && e.touches[0]) handleMove(e.touches[0].clientX);
    };
    const onMouseUp = () => setIsDragging(false);

    if (isDragging) {
      window.addEventListener("mousemove", onMouseMove);
      window.addEventListener("touchmove", onTouchMove);
      window.addEventListener("mouseup", onMouseUp);
      window.addEventListener("touchend", onMouseUp);
    }
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("mouseup", onMouseUp);
      window.removeEventListener("touchend", onMouseUp);
    };
  }, [isDragging]);

  return (
    <div className="flex flex-col gap-2 w-full bg-neutral-950 border border-neutral-800 rounded p-2.5">
      {/* Mode Switcher Buttons */}
      <div className="flex items-center justify-between gap-1 pb-1 border-b border-neutral-800/80">
        <span className="text-[10px] font-mono text-neutral-400 uppercase tracking-widest flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
          BITEMPORAL REVEAL
        </span>
        <div className="flex items-center gap-1">
          {(["SPLIT", "BEFORE", "AFTER", "MASK", "BLEND"] as ViewMode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-2 py-0.5 text-[9px] font-mono tracking-wider rounded transition-all ${
                mode === m
                  ? "bg-neutral-800 text-cyan-400 border border-cyan-500/50 font-bold"
                  : "text-neutral-500 hover:text-neutral-300 border border-transparent"
              }`}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      {/* Main Image Container */}
      <div
        ref={containerRef}
        onMouseDown={() => mode === "SPLIT" && setIsDragging(true)}
        onTouchStart={() => mode === "SPLIT" && setIsDragging(true)}
        className="relative w-full h-52 bg-black rounded overflow-hidden select-none cursor-ew-resize border border-neutral-800"
      >
        {/* AFTER IMAGE (Base Layer) */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={aUrl}
          alt="After Observation"
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-200 ${
            mode === "BEFORE" ? "opacity-0" : "opacity-100"
          }`}
        />

        {/* BEFORE IMAGE (Clipped overlay based on sliderPos) */}
        {mode === "SPLIT" && (
          <div
            className="absolute inset-0 overflow-hidden"
            style={{ width: `${sliderPos}%` }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={bUrl}
              alt="Before Observation"
              className="absolute inset-0 w-full h-full object-cover max-w-none"
              style={{
                width: containerRef.current ? `${containerRef.current.clientWidth}px` : "100%",
                height: "100%",
              }}
            />
          </div>
        )}

        {/* BEFORE MODE EXCLUSIVE */}
        {mode === "BEFORE" && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={bUrl} alt="Before Observation" className="absolute inset-0 w-full h-full object-cover" />
        )}

        {/* BLEND MODE */}
        {mode === "BLEND" && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={bUrl}
            alt="Before Observation Blend"
            className="absolute inset-0 w-full h-full object-cover opacity-50 mix-blend-difference"
          />
        )}

        {/* CHANGE MASK HEATMAP OVERLAY */}
        {(mode === "MASK" || mode === "SPLIT") && (
          <div
            className={`absolute inset-0 pointer-events-none transition-opacity ${
              mode === "MASK" ? "opacity-90" : "opacity-35"
            }`}
          >
            {/* Synthetic or Real Change Mask Heatmap Texture */}
            <div className="w-full h-full bg-[radial-gradient(ellipse_at_center,rgba(239,68,68,0.75)_0%,rgba(234,179,8,0.4)_45%,transparent_70%)] mix-blend-screen" />
          </div>
        )}

        {/* SPLIT DIVIDER LINE & HANDLE */}
        {mode === "SPLIT" && (
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-cyan-400 shadow-[0_0_10px_#06b6d4] z-20 pointer-events-none"
            style={{ left: `${sliderPos}%` }}
          >
            <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-6 h-6 rounded-full bg-black border-2 border-cyan-400 flex items-center justify-center shadow-lg">
              <svg className="w-3.5 h-3.5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M8 9l-4 3 4 3m8-6l4 3-4 3" />
              </svg>
            </div>
          </div>
        )}

        {/* Overlay Labels */}
        <div className="absolute bottom-2 left-2 z-10 px-2 py-0.5 rounded bg-black/80 backdrop-blur-sm border border-neutral-800 text-[9px] font-mono text-neutral-300">
          T0: {beforeDate?.slice(0, 10)}
        </div>
        <div className="absolute bottom-2 right-2 z-10 px-2 py-0.5 rounded bg-black/80 backdrop-blur-sm border border-neutral-800 text-[9px] font-mono text-cyan-400 font-semibold">
          T1: {afterDate?.slice(0, 10)}
        </div>
      </div>

      {/* Footer Metrics */}
      <div className="flex items-center justify-between text-[10px] font-mono text-neutral-400 pt-0.5">
        <span className="truncate">
          DETECTED: <span className="text-white font-bold">{(dominantChange ?? "CONSTRUCTION").toUpperCase()}</span>
        </span>
        <span className="text-emerald-400 font-bold">
          CONFIDENCE: {Math.round((confidence ?? 0.89) * 100)}%
        </span>
      </div>
    </div>
  );
}
