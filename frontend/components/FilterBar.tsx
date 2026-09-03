"use client";

import React, { useState } from "react";
import { FilterState } from "@/lib/api";

interface Props {
  filters: FilterState;
  onChange: (f: FilterState) => void;
  sensors?: string[];
  onTriggerDrawBbox?: () => void;
  onClearBbox?: () => void;
}

export default function FilterBar({
  filters,
  onChange,
  sensors = ["Sentinel-2", "Landsat-8"],
  onTriggerDrawBbox,
  onClearBbox,
}: Props) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="w-full bg-neutral-950 border border-neutral-800 rounded-lg p-3 font-mono text-xs space-y-2.5">
      {/* Primary Row: Date + Sensor + Filter Drawer Toggle */}
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wider text-neutral-400 font-bold flex items-center gap-1.5">
          <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
          </svg>
          FILTERS &amp; AOI
        </span>

        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-[10px] text-cyan-400 hover:text-cyan-300 transition-colors uppercase tracking-wider font-semibold"
        >
          {isExpanded ? "[ − LESS ]" : "[ + ADVANCED ]"}
        </button>
      </div>

      {/* Spatial AOI Buttons & Sensor Filter */}
      <div className="flex items-center gap-2">
        <span className="text-[9px] uppercase tracking-wider text-neutral-500 w-14 flex-shrink-0">
          SPATIAL:
        </span>
        <div className="flex flex-wrap items-center gap-1.5 flex-1">
          <button
            onClick={onTriggerDrawBbox}
            className={`px-2 py-1 rounded text-[9px] uppercase tracking-wider transition-all border ${
              filters.bbox
                ? "bg-cyan-950/60 border-cyan-500 text-cyan-300 font-bold"
                : "bg-neutral-900 border-neutral-700 text-neutral-400 hover:text-neutral-200 hover:border-neutral-500"
            }`}
          >
            {filters.bbox ? "◇ AOI ACTIVE" : "◇ DRAW AOI"}
          </button>
          {filters.bbox && onClearBbox && (
            <button
              onClick={onClearBbox}
              className="px-1.5 py-1 rounded text-[9px] bg-red-950/40 border border-red-800/60 text-red-400 hover:bg-red-900/40"
              title="Clear AOI bounding box"
            >
              ✕
            </button>
          )}
          <span className="text-[9px] text-neutral-600">|</span>
          <select
            value={filters.sensor ?? "Sentinel-2"}
            onChange={(e) => onChange({ ...filters, sensor: e.target.value || undefined })}
            className="bg-black border border-neutral-800 rounded px-2 py-1 text-[10px] text-neutral-300 outline-none uppercase cursor-pointer"
          >
            <option value="Sentinel-2">SENTINEL-2 (PRIMARY)</option>
            {sensors.filter(s => s !== "Sentinel-2").map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Expanded Advanced Filters */}
      {isExpanded && (
        <div className="pt-2 border-t border-neutral-800/80 space-y-3 font-sans">
          {/* Temporal Range */}
          <div className="space-y-1">
            <span className="font-mono text-[9px] uppercase tracking-wider text-neutral-500 block">
              TEMPORAL ACQUISITION RANGE
            </span>
            <div className="flex items-center gap-2 font-mono text-[10px]">
              <input
                type="date"
                value={filters.dateFrom ?? "2023-01-01"}
                onChange={(e) => onChange({ ...filters, dateFrom: e.target.value })}
                className="bg-black border border-neutral-800 focus:border-neutral-600 rounded px-2 py-1 text-neutral-300 flex-1 outline-none text-[10px]"
              />
              <span className="text-neutral-600">→</span>
              <input
                type="date"
                value={filters.dateTo ?? "2026-09-01"}
                onChange={(e) => onChange({ ...filters, dateTo: e.target.value })}
                className="bg-black border border-neutral-800 focus:border-neutral-600 rounded px-2 py-1 text-neutral-300 flex-1 outline-none text-[10px]"
              />
            </div>
          </div>

          {/* Quality & Cloud Cover Sliders */}
          <div className="grid grid-cols-2 gap-3 pt-1">
            <div>
              <div className="flex justify-between text-[10px] font-mono text-neutral-400 mb-1">
                <span>MAX CLOUD</span>
                <span className="text-cyan-400 font-bold">{Math.round((filters.maxCloudCover ?? 0.3) * 100)}%</span>
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={filters.maxCloudCover ?? 0.3}
                onChange={(e) => onChange({ ...filters, maxCloudCover: parseFloat(e.target.value) })}
                className="w-full accent-cyan-400 h-1 bg-neutral-800 rounded appearance-none cursor-pointer"
              />
            </div>
            <div>
              <div className="flex justify-between text-[10px] font-mono text-neutral-400 mb-1">
                <span>MIN SIMILARITY</span>
                <span className="text-emerald-400 font-bold">{(filters.minSimilarity ?? 0).toFixed(2)}</span>
              </div>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={filters.minSimilarity ?? 0}
                onChange={(e) => onChange({ ...filters, minSimilarity: parseFloat(e.target.value) })}
                className="w-full accent-emerald-400 h-1 bg-neutral-800 rounded appearance-none cursor-pointer"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
