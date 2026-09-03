"use client";

import React, { useState } from "react";

interface ObservationNode {
  year: string;
  date: string;
  isEarliestChange?: boolean;
  cloudCover: string;
  sensor: string;
  status: string;
}

interface ChangeTimelineProps {
  onSelectDate?: (date: string) => void;
  earliestDate?: string;
  registrationConfidence?: number;
}

export default function ChangeTimeline({
  onSelectDate,
  earliestDate = "2024-09-14",
  registrationConfidence = 96,
}: ChangeTimelineProps) {
  const [selectedIdx, setSelectedIdx] = useState(2); // default on 2024 (Earliest change)

  const nodes: ObservationNode[] = [
    { year: "2022", date: "2022-10-12", cloudCover: "1.2%", sensor: "Sentinel-2", status: "Baseline Nominal" },
    { year: "2023", date: "2023-04-18", cloudCover: "2.8%", sensor: "Sentinel-2", status: "Baseline Nominal" },
    { year: "2024", date: earliestDate, isEarliestChange: true, cloudCover: "0.8%", sensor: "Sentinel-2", status: "First Supported Change" },
    { year: "2025", date: "2025-06-20", cloudCover: "3.1%", sensor: "Sentinel-2", status: "Structural Growth" },
    { year: "2026", date: "2026-05-18", cloudCover: "1.9%", sensor: "Sentinel-2", status: "Current State" },
  ];

  const handleSelect = (idx: number) => {
    setSelectedIdx(idx);
    if (onSelectDate) onSelectDate(nodes[idx].date);
  };

  const selectedNode = nodes[selectedIdx];

  return (
    <div className="space-y-3 p-3 bg-neutral-950 border border-neutral-800 rounded font-mono text-xs">
      <div className="flex items-center justify-between border-b border-neutral-800 pb-1.5">
        <span className="text-[10px] uppercase tracking-widest text-neutral-400 font-bold flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
          MULTI-TEMPORAL STACK
        </span>
        <span className="text-[9px] text-neutral-500 uppercase tracking-wider">
          5 OBSERVATIONS
        </span>
      </div>

      {/* Visual Timeline Axis */}
      <div className="relative pt-4 pb-2 px-3">
        {/* Track line */}
        <div className="absolute top-7 left-4 right-4 h-0.5 bg-neutral-800" />

        {/* Nodes */}
        <div className="relative flex justify-between items-center z-10">
          {nodes.map((n, i) => {
            const isSelected = i === selectedIdx;
            return (
              <div key={n.year} className="flex flex-col items-center">
                <button
                  onClick={() => handleSelect(i)}
                  className={`relative w-6 h-6 rounded-full flex items-center justify-center transition-all ${
                    isSelected
                      ? "bg-cyan-500 text-black font-bold ring-4 ring-cyan-500/20 scale-110"
                      : n.isEarliestChange
                      ? "bg-amber-500/20 border border-amber-500 text-amber-400"
                      : "bg-neutral-900 border border-neutral-700 text-neutral-400 hover:border-neutral-500"
                  }`}
                  title={`${n.year} (${n.date})`}
                >
                  <span className="text-[9px]">{i + 1}</span>
                  {n.isEarliestChange && !isSelected && (
                    <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-amber-400 animate-ping" />
                  )}
                </button>
                <span className={`text-[10px] mt-1.5 font-bold ${isSelected ? "text-cyan-400" : "text-neutral-500"}`}>
                  {n.year}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Selected Observation Quick Card */}
      <div className="p-2 bg-neutral-900/60 rounded border border-neutral-800/80 flex items-center justify-between text-[10px]">
        <div>
          <span className="text-neutral-500">SELECTED PASS: </span>
          <span className="text-white font-bold">{selectedNode.date}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-neutral-500">CLOUD: <span className="text-emerald-400">{selectedNode.cloudCover}</span></span>
          <span className="text-neutral-600">|</span>
          <span className="text-cyan-400 font-semibold">{selectedNode.status}</span>
        </div>
      </div>

      {/* Earliest Supported Change Banner */}
      <div className="p-2.5 rounded bg-emerald-950/20 border border-emerald-800/50 space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase font-bold text-emerald-400 tracking-wider flex items-center gap-1.5">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            EARLIEST SUPPORTED CHANGE
          </span>
          <span className="text-[10px] font-bold text-white bg-emerald-900/40 px-2 py-0.5 rounded border border-emerald-700/50">
            {earliestDate.slice(0, 7)}
          </span>
        </div>

        <div className="space-y-1 text-[10px] text-neutral-300 font-sans pt-1">
          <div className="flex items-center gap-1.5">
            <span className="text-emerald-400 font-bold">✓</span>
            <span>Verified in 2+ consecutive cloud-free passes</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-emerald-400 font-bold">✓</span>
            <span>Registration confidence: <span className="font-mono text-emerald-400 font-bold">{registrationConfidence}%</span></span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-emerald-400 font-bold">✓</span>
            <span>Spectral consistency: <span className="font-mono text-emerald-400 font-bold">HIGH (ΔNDBI: +0.42)</span></span>
          </div>
        </div>
      </div>
    </div>
  );
}
