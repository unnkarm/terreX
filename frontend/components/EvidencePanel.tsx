"use client";

import React from "react";

interface EvidencePanelProps {
  confidence?: number;
  dNdvi?: number;
  dNdbi?: number;
  dNdwi?: number;
  registrationCorr?: number;
  cloudFraction?: number;
  validPixelRatio?: number;
  reasons?: string[];
  suppressionReasons?: string[];
}

export default function EvidencePanel({
  confidence = 0.91,
  dNdvi = -0.38,
  dNdbi = 0.42,
  dNdwi = -0.05,
  registrationCorr = 0.96,
  cloudFraction = 0.03,
  validPixelRatio = 0.98,
  reasons,
  suppressionReasons,
}: EvidencePanelProps) {
  const confPercent = Math.round(confidence * 100);

  return (
    <div className="space-y-3 p-3.5 bg-neutral-950 border border-neutral-800 rounded font-sans text-xs">
      {/* Header Banner */}
      <div className="flex items-center justify-between border-b border-neutral-800 pb-2">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="font-sans font-bold text-white tracking-tight uppercase text-xs">
            Change Detected
          </span>
        </div>
        <span className="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-800 text-emerald-400 font-mono font-bold text-xs">
          CONFIDENCE: {confPercent}%
        </span>
      </div>

      {/* Evidence Section */}
      <div className="space-y-1.5">
        <span className="text-[10px] font-mono uppercase tracking-widest text-neutral-400 font-semibold block">
          PHYSICAL EVIDENCE (SPECTRAL &amp; SPATIAL)
        </span>
        <div className="space-y-1.5 bg-neutral-900/50 p-2.5 rounded border border-neutral-800/80">
          <div className="flex items-center justify-between text-[11px] text-neutral-200">
            <span className="flex items-center gap-2">
              <span className="text-emerald-400 font-bold font-mono">✓</span>
              <span>Built-up index increased</span>
            </span>
            <span className="font-mono text-emerald-400 text-[10px]">
              ΔNDBI: +{Math.abs(dNdbi).toFixed(2)}
            </span>
          </div>

          <div className="flex items-center justify-between text-[11px] text-neutral-200">
            <span className="flex items-center gap-2">
              <span className="text-emerald-400 font-bold font-mono">✓</span>
              <span>Vegetation decreased</span>
            </span>
            <span className="font-mono text-amber-400 text-[10px]">
              ΔNDVI: -{Math.abs(dNdvi).toFixed(2)}
            </span>
          </div>

          <div className="flex items-center justify-between text-[11px] text-neutral-200">
            <span className="flex items-center gap-2">
              <span className="text-emerald-400 font-bold font-mono">✓</span>
              <span>Persistent across observations</span>
            </span>
            <span className="font-mono text-cyan-400 text-[10px]">
              3 passes
            </span>
          </div>

          <div className="flex items-center justify-between text-[11px] text-neutral-200">
            <span className="flex items-center gap-2">
              <span className="text-emerald-400 font-bold font-mono">✓</span>
              <span>Good sub-pixel registration</span>
            </span>
            <span className="font-mono text-emerald-400 text-[10px]">
              {Math.round(registrationCorr * 100)}% corr
            </span>
          </div>
        </div>
      </div>

      {/* Quality Section */}
      <div className="space-y-1.5">
        <span className="text-[10px] font-mono uppercase tracking-widest text-neutral-400 font-semibold block">
          OBSERVATION DATA QUALITY
        </span>
        <div className="space-y-1.5 bg-neutral-900/30 p-2.5 rounded border border-neutral-800/60 font-sans">
          <div className="flex items-center justify-between text-[11px] text-neutral-300">
            <span className="flex items-center gap-2">
              <span className="text-emerald-400 font-bold font-mono">✓</span>
              <span>Low cloud cover</span>
            </span>
            <span className="font-mono text-neutral-400 text-[10px]">
              {Math.round(cloudFraction * 100)}%
            </span>
          </div>

          <div className="flex items-center justify-between text-[11px] text-neutral-300">
            <span className="flex items-center gap-2">
              <span className="text-emerald-400 font-bold font-mono">✓</span>
              <span>High valid-pixel ratio</span>
            </span>
            <span className="font-mono text-neutral-400 text-[10px]">
              {Math.round(validPixelRatio * 100)}%
            </span>
          </div>

          <div className="flex items-center justify-between text-[11px] text-neutral-300">
            <span className="flex items-center gap-2">
              <span className="text-emerald-400 font-bold font-mono">✓</span>
              <span>Good temporal alignment</span>
            </span>
            <span className="font-mono text-neutral-400 text-[10px]">
              Sentinel-2 stack
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
