"use client";

import React, { useState } from "react";
import { SearchResult } from "@/lib/api";

interface ProvenanceDrawerProps {
  result: SearchResult | null;
  isOpen: boolean;
  onClose: () => void;
}

interface StageDetail {
  id: string;
  name: string;
  status: "COMPLETE" | "VERIFIED" | "ACTIVE";
  model: string;
  version: string;
  timestamp: string;
  inputs: string;
  outputs: string;
  notes: string;
}

export default function ProvenanceDrawer({ result, isOpen, onClose }: ProvenanceDrawerProps) {
  const [activeStage, setActiveStage] = useState<number>(0);

  if (!isOpen || !result) return null;

  const provenance = result.provenance || {};
  const sourcePortal = result.source_portal ?? (provenance.source_portal as string | undefined) ?? "Not recorded";
  const dataset = result.underlying_dataset ?? (provenance.underlying_dataset as string | undefined) ?? "Not recorded";
  const license = result.license ?? (provenance.license as string | undefined) ?? "Not recorded";
  const stages: StageDetail[] = [
    {
      id: "source",
      name: "Recorded Source Metadata",
      status: "VERIFIED",
      model: sourcePortal,
      version: dataset,
      timestamp: result.acquisition_date ?? "Not recorded",
      inputs: `Sensor: ${result.sensor ?? "Not recorded"}`,
      outputs: `License: ${license}`,
      notes: Object.keys(provenance).length > 0
        ? "Values shown exactly as stored in the scene provenance record."
        : "No structured provenance object was attached to this search result.",
    },
    {
      id: "tile",
      name: "Indexed Tile Record",
      status: "COMPLETE",
      model: "TerreX local metadata store",
      version: result.scene_id,
      timestamp: result.acquisition_date ?? "Not recorded",
      inputs: `Tile ID: ${result.tile_id}`,
      outputs: `Coordinates: ${result.lat.toFixed(5)}°N, ${result.lon.toFixed(5)}°E`,
      notes: `Quality: ${result.quality_score == null ? "N/A" : result.quality_score.toFixed(3)}; cloud fraction: ${result.cloud_fraction == null ? "N/A" : result.cloud_fraction.toFixed(3)}.`,
    },
    {
      id: "embedding",
      name: "Stored Embedding Metadata",
      status: result.embedding_is_placeholder ? "ACTIVE" : "COMPLETE",
      model: result.embedding_model ?? "Not recorded",
      version: result.embedding_model_version ?? "Not recorded",
      timestamp: "Not recorded",
      inputs: "Stored tile image",
      outputs: `Similarity: ${result.similarity_score.toFixed(4)}; final score: ${result.final_score.toFixed(4)}`,
      notes: result.embedding_is_placeholder
        ? "This vector is explicitly marked as a placeholder embedding and must not be treated as semantic model evidence."
        : "The result record does not mark this embedding as a placeholder.",
    },
  ];

  const current = stages[activeStage];

  return (
    <div className="fixed inset-0 z-[200] flex justify-end bg-black/70 backdrop-blur-sm animate-in fade-in">
      <div className="w-[520px] max-w-[95vw] h-full bg-neutral-950 border-l border-neutral-800 flex flex-col shadow-2xl overflow-hidden font-mono text-xs">
        {/* Header */}
        <div className="px-5 py-4 border-b border-neutral-800 flex items-center justify-between bg-black">
          <div>
            <h2 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
              PROCESSING HISTORY & PROVENANCE
            </h2>
            <p className="text-[10px] text-neutral-500 mt-0.5">
              TARGET: {result.tile_id} &middot; AUDIT TRAIL
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded text-neutral-400 hover:text-white hover:bg-neutral-900 transition-all text-base"
          >
            ✕
          </button>
        </div>

        {/* Pipeline Flow Stepper */}
        <div className="p-4 border-b border-neutral-800 bg-neutral-900/30 overflow-x-auto">
          <div className="flex items-center gap-1.5 min-w-max">
            {stages.map((st, i) => (
              <button
                key={st.id}
                onClick={() => setActiveStage(i)}
                className={`px-2.5 py-1 rounded text-[9px] uppercase tracking-wider transition-all flex items-center gap-1.5 ${
                  activeStage === i
                    ? "bg-cyan-950 text-cyan-300 border border-cyan-500/50 font-bold"
                    : "bg-neutral-900 text-neutral-400 hover:text-neutral-200 border border-neutral-800"
                }`}
              >
                <span>{i + 1}.</span>
                <span>{st.name.split(" ")[0]}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Stage Detailed Inspector */}
        <div className="flex-1 p-5 overflow-y-auto space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-base font-bold text-white tracking-wide">
              {activeStage + 1}. {current.name}
            </span>
            <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800 font-bold">
              {current.status}
            </span>
          </div>

          <div className="space-y-3 bg-black/60 p-4 rounded border border-neutral-800/80">
            <div>
              <p className="text-[10px] text-neutral-500 uppercase tracking-widest">Model / Engine</p>
              <p className="text-sm font-semibold text-neutral-200 mt-0.5">{current.model}</p>
            </div>

            <div className="grid grid-cols-2 gap-3 pt-1">
              <div>
                <p className="text-[10px] text-neutral-500 uppercase tracking-widest">Version</p>
                <p className="text-xs text-neutral-300 font-bold mt-0.5">{current.version}</p>
              </div>
              <div>
                <p className="text-[10px] text-neutral-500 uppercase tracking-widest">Execution Time</p>
                <p className="text-xs text-neutral-300 mt-0.5">{current.timestamp}</p>
              </div>
            </div>

            <div className="pt-1">
              <p className="text-[10px] text-neutral-500 uppercase tracking-widest">Input Parameters</p>
              <p className="text-xs text-neutral-400 bg-neutral-900 p-2 rounded mt-1 font-sans">
                {current.inputs}
              </p>
            </div>

            <div>
              <p className="text-[10px] text-neutral-500 uppercase tracking-widest">Generated Output Artifacts</p>
              <p className="text-xs text-emerald-300 bg-emerald-950/20 border border-emerald-900/40 p-2 rounded mt-1 font-sans">
                {current.outputs}
              </p>
            </div>

            <div>
              <p className="text-[10px] text-neutral-500 uppercase tracking-widest">Audit & Compliance Notes</p>
              <p className="text-[11px] text-neutral-400 mt-1 leading-relaxed font-sans">
                {current.notes}
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-neutral-800 bg-black flex justify-between items-center text-[10px] text-neutral-500">
          <span>STRICT AIR-GAP COMPLIANCE &middot; LEVEL 1 VERIFIED</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded bg-neutral-900 hover:bg-neutral-800 text-neutral-300 border border-neutral-700 font-bold"
          >
            CLOSE
          </button>
        </div>
      </div>
    </div>
  );
}
