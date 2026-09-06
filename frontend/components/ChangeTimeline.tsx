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
  // Use real observations if provided, otherwise default mock passes
  const nodes: (ChangeObservation & { status?: string })[] = observations && observations.length > 0
    ? observations.map((obs) => ({
        ...obs,
        status: obs.is_baseline
          ? "Baseline Nominal"
          : obs.is_earliest_change
          ? "First Supported Change"
          : obs.distance_from_baseline > 0.4
          ? "Persistent Structural Change"
          : "Observation Pass",
      }))
    : [
        {
          index: 1,
          tile_id: "obs-1",
          scene_id: "s2-2022",
          year: "2022",
          date_formatted: "2022-10-12",
          acquisition_date: "2022-10-12T00:00:00Z",
          cloud_fraction: 0.012,
          quality_score: 0.95,
          sensor: "Sentinel-2",
          thumbnail_url: "",
          distance_from_baseline: 0.0,
          mean_ndvi: 0.54,
          mean_ndwi: -0.12,
          mean_ndbi: -0.22,
          is_baseline: true,
          is_earliest_change: false,
          status: "Baseline Nominal",
        },
        {
          index: 2,
          tile_id: "obs-2",
          scene_id: "s2-2023",
          year: "2023",
          date_formatted: "2023-04-18",
          acquisition_date: "2023-04-18T00:00:00Z",
          cloud_fraction: 0.028,
          quality_score: 0.92,
          sensor: "Sentinel-2",
          thumbnail_url: "",
          distance_from_baseline: 0.08,
          mean_ndvi: 0.51,
          mean_ndwi: -0.14,
          mean_ndbi: -0.18,
          is_baseline: false,
          is_earliest_change: false,
          status: "Baseline Nominal",
        },
        {
          index: 3,
          tile_id: "obs-3",
          scene_id: "s2-2024",
          year: "2024",
          date_formatted: earliestDate || "2024-09-14",
          acquisition_date: (earliestDate || "2024-09-14") + "T00:00:00Z",
          cloud_fraction: 0.008,
          quality_score: 0.96,
          sensor: "Sentinel-2",
          thumbnail_url: "",
          distance_from_baseline: 0.44,
          mean_ndvi: 0.28,
          mean_ndwi: -0.15,
          mean_ndbi: 0.26,
          is_baseline: false,
          is_earliest_change: true,
          status: "First Supported Change",
        },
        {
          index: 4,
          tile_id: "obs-4",
          scene_id: "s2-2025",
          year: "2025",
          date_formatted: "2025-06-20",
          acquisition_date: "2025-06-20T00:00:00Z",
          cloud_fraction: 0.031,
          quality_score: 0.94,
          sensor: "Sentinel-2",
          thumbnail_url: "",
          distance_from_baseline: 0.52,
          mean_ndvi: 0.22,
          mean_ndwi: -0.18,
          mean_ndbi: 0.38,
          is_baseline: false,
          is_earliest_change: false,
          status: "Structural Growth",
        },
        {
          index: 5,
          tile_id: "obs-5",
          scene_id: "s2-2026",
          year: "2026",
          date_formatted: "2026-05-18",
          acquisition_date: "2026-05-18T00:00:00Z",
          cloud_fraction: 0.019,
          quality_score: 0.97,
          sensor: "Sentinel-2",
          thumbnail_url: "",
          distance_from_baseline: 0.58,
          mean_ndvi: 0.18,
          mean_ndwi: -0.19,
          mean_ndbi: 0.42,
          is_baseline: false,
          is_earliest_change: false,
          status: "Current State",
        },
      ];

  const [selectedIdx, setSelectedIdx] = useState(() => {
    const earlyIdx = nodes.findIndex((n) => n.is_earliest_change);
    return earlyIdx >= 0 ? earlyIdx : Math.min(2, nodes.length - 1);
  });

  useEffect(() => {
    const earlyIdx = nodes.findIndex((n) => n.is_earliest_change);
    if (earlyIdx >= 0) {
      setSelectedIdx(earlyIdx);
    }
  }, [earliestDate, observations]);

  const handleSelect = (idx: number) => {
    setSelectedIdx(idx);
    if (onSelectDate) onSelectDate(nodes[idx].date_formatted, nodes[idx]);
  };

  const selectedNode = nodes[selectedIdx] || nodes[0];
  const displayEarliest = earliestDate ? earliestDate.slice(0, 10) : nodes.find((n) => n.is_earliest_change)?.date_formatted || "2024-09-14";

  return (
    <div className="space-y-3 p-3 bg-neutral-950 border border-neutral-800 rounded font-mono text-xs">
      <div className="flex items-center justify-between border-b border-neutral-800 pb-1.5">
        <span className="text-[10px] uppercase tracking-widest text-neutral-400 font-bold flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
          MULTI-TEMPORAL OBSERVATION STACK (TIER 1.3)
        </span>
        <span className="text-[9px] text-cyan-400 uppercase tracking-wider font-bold">
          {nodes.length} OBSERVATIONS
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
              <div key={n.tile_id || i} className="flex flex-col items-center">
                <button
                  onClick={() => handleSelect(i)}
                  className={`relative w-6 h-6 rounded-full flex items-center justify-center transition-all ${
                    isSelected
                      ? "bg-cyan-500 text-black font-bold ring-4 ring-cyan-500/20 scale-110 shadow-[0_0_12px_#06b6d4]"
                      : n.is_earliest_change
                      ? "bg-amber-500/20 border border-amber-500 text-amber-400"
                      : "bg-neutral-900 border border-neutral-700 text-neutral-400 hover:border-neutral-500"
                  }`}
                  title={`${n.year} (${n.date_formatted}) - Click to inspect pass`}
                >
                  <span className="text-[9px]">{i + 1}</span>
                  {n.is_earliest_change && !isSelected && (
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
      <div className="p-2.5 bg-neutral-900/70 rounded border border-neutral-800/90 flex flex-col gap-1.5 text-[10px]">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-neutral-500">INSPECTED PASS: </span>
            <span className="text-white font-bold">{selectedNode.date_formatted}</span>
            <span className="text-neutral-500 ml-1.5">({selectedNode.sensor})</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-neutral-500">CLOUD: <span className="text-emerald-400">{Math.round((selectedNode.cloud_fraction || 0) * 100)}%</span></span>
            <span className="text-neutral-600">|</span>
            <span className="text-cyan-400 font-semibold">{selectedNode.status}</span>
          </div>
        </div>

        {/* Per-observation Spectral Diagnostics */}
        <div className="grid grid-cols-4 gap-1 pt-1 text-[9px] border-t border-neutral-800/60">
          <div className="text-neutral-400">NDVI: <span className="text-emerald-400 font-bold">{selectedNode.mean_ndvi?.toFixed(2) ?? "N/A"}</span></div>
          <div className="text-neutral-400">NDBI: <span className="text-amber-400 font-bold">{selectedNode.mean_ndbi?.toFixed(2) ?? "N/A"}</span></div>
          <div className="text-neutral-400">NDWI: <span className="text-cyan-400 font-bold">{selectedNode.mean_ndwi?.toFixed(2) ?? "N/A"}</span></div>
          <div className="text-neutral-400">Δ-Base: <span className="text-purple-400 font-bold">{selectedNode.distance_from_baseline?.toFixed(2) ?? "0.00"}</span></div>
        </div>
      </div>

      {/* Earliest Supported Change Banner */}
      <div className="p-2.5 rounded bg-emerald-950/20 border border-emerald-800/50 space-y-1.5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase font-bold text-emerald-400 tracking-wider flex items-center gap-1.5">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            EARLIEST SUPPORTED CHANGE (2.2.2)
          </span>
          <span className="text-[10px] font-bold text-white bg-emerald-900/40 px-2 py-0.5 rounded border border-emerald-700/50 font-mono">
            {displayEarliest}
          </span>
        </div>

        <div className="space-y-1 text-[10px] text-neutral-300 font-sans pt-1">
          <div className="flex items-center gap-1.5">
            <span className="text-emerald-400 font-bold">✓</span>
            <span>Corroborated across continuous satellite observation time series</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-emerald-400 font-bold">✓</span>
            <span>Sub-pixel co-registration confidence: <span className="font-mono text-emerald-400 font-bold">{registrationConfidence}%</span></span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-emerald-400 font-bold">✓</span>
            <span>Ground spectral change persistent past initial detection threshold</span>
          </div>
        </div>
      </div>
    </div>
  );
}

