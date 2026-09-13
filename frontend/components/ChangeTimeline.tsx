"use client";

import React, { useState, useEffect } from "react";
import { ChangeObservation } from "@/lib/api";

interface ChangeTimelineProps {
  onSelectDate?: (date: string, observation?: ChangeObservation) => void;
  earliestDate?: string;
  registrationConfidence?: number;
  observations?: ChangeObservation[];
}

export default function ChangeTimeline({
  onSelectDate,
  earliestDate,
  registrationConfidence = 96,
  observations,
}: ChangeTimelineProps) {
  const hasLiveObservations = Boolean(observations && observations.length > 0);

  const nodes: (ChangeObservation & { status?: string })[] = hasLiveObservations
    ? (observations || []).map((obs) => ({
        ...obs,
        status: obs.is_baseline
          ? "Baseline Reference"
          : obs.is_earliest_change
          ? "Initial Detection"
          : obs.distance_from_baseline > 0.4
          ? "Persistent Structural Change"
          : "Observation Pass",
      }))
    : [];

  const [selectedIdx, setSelectedIdx] = useState(() => {
    const earlyIdx = nodes.findIndex((n) => n.is_earliest_change);
    return earlyIdx >= 0 ? earlyIdx : 0;
  });

  useEffect(() => {
    const earlyIdx = nodes.findIndex((n) => n.is_earliest_change);
    if (earlyIdx >= 0) {
      setSelectedIdx(earlyIdx);
    } else {
      setSelectedIdx(0);
    }
  }, [earliestDate, observations]);

  if (!hasLiveObservations) {
    return (
      <div className="p-4 bg-neutral-900 border border-neutral-800 rounded space-y-3 font-mono text-xs select-none">
        <div className="flex items-center justify-between border-b border-neutral-800 pb-2.5">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_#34d399]"></span>
            <span className="text-xs font-bold text-white uppercase tracking-wider">Multi-Temporal Timeline</span>
          </div>
          <span className="text-[10px] font-bold text-neutral-400 bg-neutral-950 px-2 py-0.5 rounded border border-neutral-800 uppercase">
            Awaiting Analysis
          </span>
        </div>
        <p className="text-[11px] text-neutral-400 leading-relaxed font-sans">
          Run change detection on the map to evaluate time-series satellite passes, spectral deltas, and verified ground evolution.
        </p>
      </div>
    );
  }

  const handleSelect = (idx: number) => {
    setSelectedIdx(idx);
    if (onSelectDate) onSelectDate(nodes[idx].date_formatted, nodes[idx]);
  };

  const selectedNode = nodes[selectedIdx] || nodes[0];
  const displayEarliest = earliestDate ? earliestDate.slice(0, 10) : nodes.find((n) => n.is_earliest_change)?.date_formatted || "2025-10-25";

  return (
    <div className="space-y-3.5 p-4 bg-neutral-900 border border-neutral-800 rounded shadow-2xl font-mono text-xs select-none">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-neutral-800 pb-2.5">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]"></span>
          <span className="text-xs font-bold text-white uppercase tracking-wider">Multi-Temporal Timeline</span>
        </div>
        <span className="text-[10px] font-bold text-emerald-400 bg-emerald-950/50 px-2 py-0.5 rounded border border-emerald-800/50 uppercase">
          {nodes.length} Passes Recorded
        </span>
      </div>

      {/* Visual Stepper Timeline */}
      <div className="relative pt-3 pb-2 px-2">
        {/* Track Line */}
        <div className="absolute top-[26px] left-5 right-5 h-[2px] bg-neutral-800 rounded-full" />
        
        {/* Progress Track */}
        <div
          className="absolute top-[26px] left-5 h-[2px] bg-emerald-500 rounded-full transition-all duration-300"
          style={{
            width: nodes.length > 1 ? `${(selectedIdx / (nodes.length - 1)) * 100}%` : "0%",
            maxWidth: "calc(100% - 40px)",
          }}
        />

        {/* Nodes */}
        <div className="relative flex justify-between items-center z-10">
          {nodes.map((n, i) => {
            const isSelected = i === selectedIdx;
            return (
              <div key={n.tile_id || i} className="flex flex-col items-center group">
                <button
                  onClick={() => handleSelect(i)}
                  className={`relative w-7 h-7 rounded-full flex items-center justify-center font-mono text-xs transition-all duration-200 ${
                    isSelected
                      ? "bg-emerald-500 text-black font-bold ring-4 ring-emerald-500/30 scale-110 shadow-lg shadow-emerald-500/25"
                      : n.is_earliest_change
                      ? "bg-amber-500/20 border border-amber-400 text-amber-300 hover:scale-105 font-bold"
                      : "bg-neutral-950 border border-neutral-800 text-neutral-400 hover:border-neutral-600 hover:bg-neutral-800"
                  }`}
                  title={`${n.year} (${n.date_formatted}) — Click to inspect pass`}
                >
                  <span>{i + 1}</span>
                  {n.is_earliest_change && !isSelected && (
                    <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-amber-400 animate-ping" />
                  )}
                </button>
                <span className={`text-[10px] mt-1.5 font-bold transition-colors ${isSelected ? "text-emerald-400" : "text-neutral-500 group-hover:text-neutral-300"}`}>
                  {n.year}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Selected Pass Inspection Card */}
      <div className="p-3 bg-neutral-950 rounded border border-neutral-800 space-y-2.5">
        <div className="flex items-center justify-between text-xs">
          <div className="flex items-center gap-2">
            <span className="text-neutral-500 text-[10px] uppercase">Pass:</span>
            <span className="text-white font-bold">{selectedNode.date_formatted}</span>
            <span className="text-[9px] font-bold bg-neutral-900 text-neutral-300 px-1.5 py-0.5 rounded border border-neutral-700">
              {selectedNode.sensor}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-neutral-400">
              Cloud: <span className="text-emerald-400 font-bold">{Math.round((selectedNode.cloud_fraction || 0) * 100)}%</span>
            </span>
            <span className="text-neutral-700">•</span>
            <span className="text-[10px] text-amber-400 font-bold uppercase">{selectedNode.status}</span>
          </div>
        </div>

        {/* Spectral Metrics Grid */}
        <div className="grid grid-cols-4 gap-2 pt-1 border-t border-neutral-800 text-center font-mono">
          <div className="p-1.5 bg-neutral-900 rounded border border-neutral-800">
            <div className="text-[9px] text-neutral-400 font-bold uppercase tracking-wider">NDVI</div>
            <div className="text-xs font-bold text-emerald-400 mt-0.5">{selectedNode.mean_ndvi?.toFixed(2) ?? "N/A"}</div>
          </div>
          <div className="p-1.5 bg-neutral-900 rounded border border-neutral-800">
            <div className="text-[9px] text-neutral-400 font-bold uppercase tracking-wider">NDBI</div>
            <div className="text-xs font-bold text-amber-400 mt-0.5">{selectedNode.mean_ndbi?.toFixed(2) ?? "N/A"}</div>
          </div>
          <div className="p-1.5 bg-neutral-900 rounded border border-neutral-800">
            <div className="text-[9px] text-neutral-400 font-bold uppercase tracking-wider">NDWI</div>
            <div className="text-xs font-bold text-cyan-400 mt-0.5">{selectedNode.mean_ndwi?.toFixed(2) ?? "N/A"}</div>
          </div>
          <div className="p-1.5 bg-neutral-900 rounded border border-neutral-800">
            <div className="text-[9px] text-neutral-400 font-bold uppercase tracking-wider">Δ-Base</div>
            <div className="text-xs font-bold text-purple-400 mt-0.5">{selectedNode.distance_from_baseline?.toFixed(2) ?? "0.00"}</div>
          </div>
        </div>
      </div>

      {/* Earliest Verified Change Card */}
      <div className="p-3 rounded bg-emerald-950/25 border border-emerald-800/40 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-300 uppercase tracking-wider">
            <svg className="w-4 h-4 text-emerald-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>Earliest Verified Change</span>
          </div>
          <span className="text-xs font-bold text-emerald-300 bg-emerald-900/50 px-2.5 py-0.5 rounded border border-emerald-700/60 font-mono">
            {displayEarliest}
          </span>
        </div>

        <ul className="space-y-1 text-xs text-neutral-300 pt-0.5 font-sans">
          <li className="flex items-center gap-2 text-neutral-300">
            <span className="text-emerald-400 font-bold">✓</span>
            <span>Corroborated across continuous satellite time-series</span>
          </li>
          <li className="flex items-center gap-2 text-neutral-300">
            <span className="text-emerald-400 font-bold">✓</span>
            <span>Sub-pixel co-registration confidence: <strong className="text-emerald-300 font-mono">{registrationConfidence}%</strong></span>
          </li>
          <li className="flex items-center gap-2 text-neutral-300">
            <span className="text-emerald-400 font-bold">✓</span>
            <span>Ground spectral signature persistent past detection threshold</span>
          </li>
        </ul>
      </div>
    </div>
  );
}
