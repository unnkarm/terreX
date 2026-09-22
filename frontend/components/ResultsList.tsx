"use client";

import React from "react";
import { SearchResult, thumbnailUrl } from "@/lib/api";

interface Props {
  results: SearchResult[];
  selectedTileId: string | null;
  onSelect: (r: SearchResult) => void;
  onInspect?: (r: SearchResult) => void;
  onFindSimilar?: (r: SearchResult) => void;
  placeholderWarning?: boolean;
  temporalQuery?: boolean;
}

export default function ResultsList({
  results,
  selectedTileId,
  onSelect,
  onInspect,
  onFindSimilar,
  placeholderWarning,
  temporalQuery,
}: Props) {
  return (
    <div className="flex flex-col bg-neutral-950 font-mono text-xs">
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-neutral-800 flex items-center justify-between bg-black">
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-neutral-400 font-bold">
            CANDIDATE TARGETS
          </span>
          <span className="text-[10px] px-1.5 py-0.2 rounded bg-neutral-900 border border-neutral-700 text-cyan-400 font-bold">
            {results.length}
          </span>
        </div>

        {placeholderWarning && (
          <span className="text-[9px] px-2 py-0.5 rounded bg-amber-950/40 text-amber-400 border border-amber-800/50 uppercase tracking-widest font-mono">
            Deterministic Hash
          </span>
        )}
      </div>

      {/* Results Scroll List */}
      <div className="p-2.5 space-y-2.5">
        {results.length === 0 && (
          <div className="p-8 text-center text-neutral-500 text-xs space-y-2">
            <svg className="w-8 h-8 text-neutral-700 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <p className="font-bold text-neutral-400 uppercase tracking-wider">
              {temporalQuery ? "NO CHANGE-SUPPORTED CANDIDATES" : "AWAITING QUERY INPUT..."}
            </p>
            <p className="text-[10px] text-neutral-600 font-sans">
              {temporalQuery
                ? "Static visual matches were excluded because the temporal evidence did not confirm physical change."
                : "Enter a search description or select a suggested intent above to search vector embeddings."}
            </p>
          </div>
        )}

        {results.map((r, idx) => {
          const isSelected = r.tile_id === selectedTileId;
          const simPct = Math.round(r.similarity_score * 100);
          const rankPct = Math.round(r.final_score * 100);
          const changePct = r.change_score == null ? null : Math.round(r.change_score * 100);
          const qualityPct = r.quality_score == null ? null : Math.round(r.quality_score * 100);
          const cloudPct = r.cloud_fraction == null ? null : Math.round(r.cloud_fraction * 100);
          const title = r.classification_label || (r.location_name ? `${r.location_name.toUpperCase()} REGION` : "CANDIDATE TARGET");
          const sub = r.location_name ?? r.scene_id;
          const thumb = r.thumbnail_path
            ? thumbnailUrl(r.thumbnail_path)
            : "/icon.svg";

          return (
            <div
              key={r.tile_id}
              onClick={() => onSelect(r)}
              className={`rounded border transition-all cursor-pointer overflow-hidden group ${
                isSelected
                  ? "bg-neutral-900 border-cyan-500 shadow-md ring-1 ring-cyan-500/30"
                  : "bg-black/60 border-neutral-800/80 hover:border-neutral-700 hover:bg-neutral-900/30"
              }`}
            >
              {/* Card Top Pill: Index & Relevance */}
              <div className="px-3 py-1.5 bg-neutral-900/80 border-b border-neutral-800/80 flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className="font-bold text-cyan-400">
                    #{String(idx + 1).padStart(2, "0")}
                  </span>
                  <span className="text-[9px] uppercase tracking-wider font-bold text-neutral-300">
                    {rankPct >= 75 ? "HIGH RELEVANCE" : rankPct >= 50 ? "ELEVATED" : "MODERATE"}
                  </span>
                </div>
                <span className="text-[10px] font-bold text-emerald-400 bg-emerald-950/40 px-1.5 py-0.2 rounded border border-emerald-800/50">
                  {rankPct}% {changePct == null ? "RANK" : "CHANGE-AWARE"}
                </span>
              </div>

              {/* Card Body with Thumbnail & Meta */}
              <div className="p-3 space-y-2.5">
                <div className="flex gap-3">
                  {/* Thumbnail */}
                  <div className="w-20 h-20 rounded bg-neutral-950 border border-neutral-800 flex-shrink-0 overflow-hidden relative">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={thumb}
                      alt="satellite chip"
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    />
                    <div className="absolute bottom-0 inset-x-0 bg-black/70 text-[8px] text-center font-mono py-0.5 text-neutral-400">
                      10M GSD
                    </div>
                  </div>

                  {/* Title & Classification */}
                  <div className="flex-1 min-w-0 flex flex-col justify-center">
                    <p className="font-sans font-bold text-white text-xs truncate tracking-tight">
                      {title}
                    </p>
                    <p className="text-[11px] text-neutral-300 font-sans font-light truncate mt-0.5">
                      {sub}
                    </p>
                    <p className="text-[9px] text-neutral-500 font-mono mt-1">
                      {r.lat.toFixed(4)}°N, {r.lon.toFixed(4)}°E
                    </p>
                  </div>
                </div>

                {/* Tactical Metrics Grid */}
                <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-[10px] bg-neutral-900/40 p-2 rounded border border-neutral-800/60 font-mono">
                  <div className="flex justify-between">
                    <span className="text-neutral-500">SIMILARITY:</span>
                    <span className="text-emerald-400 font-bold">{simPct}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-500">QUALITY:</span>
                    <span className="text-neutral-300 font-bold">{qualityPct == null ? "N/A" : `${qualityPct}%`}</span>
                  </div>
                  {changePct != null && <div className="flex justify-between col-span-2 py-1 border-y border-neutral-800/50">
                    <span className="text-neutral-500">TEMPORAL CHANGE:</span>
                    <span className={`font-bold ${changePct >= 50 ? "text-emerald-400" : "text-amber-400"}`}>{changePct}% EVIDENCE</span>
                  </div>}
                  <div className="flex justify-between">
                    <span className="text-neutral-500">CLOUD:</span>
                    <span className="text-neutral-300 font-bold">{cloudPct == null ? "N/A" : `${cloudPct}%`}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-neutral-500">SENSOR:</span>
                    <span className="text-cyan-400 font-bold truncate max-w-[70px]">
                      {r.sensor?.split(" ")[0] ?? "S2"}
                    </span>
                  </div>
                  <div className="flex justify-between col-span-2 pt-0.5 border-t border-neutral-800/50">
                    <span className="text-neutral-500">ACQUISITION:</span>
                    <span className="text-neutral-300">
                      {r.acquisition_date?.slice(0, 10) ?? "N/A"}
                    </span>
                  </div>
                </div>

                {/* Card Action Buttons */}
                <div className="pt-0.5">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelect(r);
                      if (onInspect) onInspect(r);
                    }}
                    className="w-full py-1.5 rounded bg-neutral-900 border border-neutral-700 hover:border-white hover:bg-neutral-800 text-white font-sans font-semibold text-[11px] uppercase tracking-widest transition-all text-center"
                  >
                    INSPECT TARGET →
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
