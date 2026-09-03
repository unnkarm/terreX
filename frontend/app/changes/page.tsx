"use client";

import React, { useState } from "react";
import Link from "next/link";
import TopNav from "@/components/TopNav";
import { ReviewQueueItem, getDemoReviewQueue } from "@/lib/api";

export default function ChangesDiscoveryPage() {
  const [dateFrom, setDateFrom] = useState("2022-01-01");
  const [dateTo, setDateTo] = useState("2026-09-01");
  const [minConfidence, setMinConfidence] = useState(0.75);
  const [selectedTypes, setSelectedTypes] = useState<string[]>([
    "construction", "clearance", "water", "roads"
  ]);
  const [isScanning, setIsScanning] = useState(false);
  const [scanComplete, setScanComplete] = useState(true);
  const [candidates, setCandidates] = useState<ReviewQueueItem[]>(getDemoReviewQueue());

  const handleScan = () => {
    setIsScanning(true);
    setTimeout(() => {
      setIsScanning(false);
      setScanComplete(true);
      setCandidates(getDemoReviewQueue());
    }, 800);
  };

  const toggleType = (t: string) => {
    setSelectedTypes((prev) =>
      prev.includes(t) ? prev.filter((item) => item !== t) : [...prev, t]
    );
  };

  return (
    <main className="min-h-screen w-screen bg-black text-neutral-300 font-sans flex flex-col select-none">
      <TopNav />

      <div className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8 space-y-8">
        
        {/* Page Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-neutral-800 pb-8">
          <div className="space-y-3">
            <div className="font-mono text-xs text-radar font-semibold tracking-widest uppercase flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-radar animate-pulse"></span>
              <span>CHANGE DISCOVERY:</span>
              <span>MULTITEMPORAL STACK</span>
            </div>
            
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-white font-sans leading-[1.1]">
              Wide-area change
              <br />
              <span className="text-neutral-400 font-light">discovery scanner.</span>
            </h1>

            <p className="text-base text-neutral-300 font-sans font-light max-w-2xl leading-relaxed">
              TerreX pairs high-resolution optical imagery with bitemporal Sentinel SAR radar data under an agentic vision-language model, returning calibrated confidence vectors and verifiable pixel evidence.
            </p>
          </div>

          <Link
            href="/workspace"
            className="px-6 py-3 bg-white text-black font-sans font-semibold text-xs tracking-widest uppercase hover:bg-neutral-200 transition-colors"
          >
            LAUNCH WORKSPACE
          </Link>
        </div>

        {/* Scanner Control Deck */}
        <div className="p-6 rounded-lg bg-neutral-950 border border-neutral-800 space-y-5 font-mono text-xs">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            
            {/* AOI Selector */}
            <div className="space-y-1.5">
              <span className="text-[10px] uppercase text-neutral-500 font-bold block">
                AREA OF INTEREST (AOI)
              </span>
              <select className="w-full bg-black border border-neutral-800 focus:border-cyan-500 rounded p-2 text-white text-xs outline-none">
                <option>Delhi NCR Corridor (18,420 km²)</option>
                <option>Yamuna Floodplain Zone (4,210 km²)</option>
                <option>Hindon River Basin (3,150 km²)</option>
                <option>Custom Polygon AOI #01</option>
              </select>
            </div>

            {/* Time Window */}
            <div className="space-y-1.5 md:col-span-2">
              <span className="text-[10px] uppercase text-neutral-500 font-bold block">
                TEMPORAL WINDOW ({dateFrom.slice(0, 4)} → {dateTo.slice(0, 4)})
              </span>
              <div className="flex items-center gap-2">
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="bg-black border border-neutral-800 rounded p-2 text-white text-xs outline-none flex-1"
                />
                <span className="text-neutral-600 font-bold">→</span>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="bg-black border border-neutral-800 rounded p-2 text-white text-xs outline-none flex-1"
                />
              </div>
            </div>

            {/* Min Confidence */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-[10px] text-neutral-500 font-bold">
                <span>MIN. CONFIDENCE</span>
                <span className="text-emerald-400 font-bold">{Math.round(minConfidence * 100)}%</span>
              </div>
              <input
                type="range"
                min={0.5}
                max={0.99}
                step={0.01}
                value={minConfidence}
                onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
                className="w-full accent-emerald-500 h-2 bg-neutral-900 rounded appearance-none cursor-pointer mt-2"
              />
            </div>
          </div>

          {/* Change Types Checklist */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-3 border-t border-neutral-800/80">
            <div className="flex flex-wrap items-center gap-2 text-[10px]">
              <span className="text-neutral-500 uppercase tracking-wider mr-2">CHANGE TYPES:</span>
              {[
                { id: "construction", label: "Construction" },
                { id: "clearance", label: "Clearance" },
                { id: "water", label: "Water Extent" },
                { id: "roads", label: "Road Network" },
              ].map((t) => {
                const checked = selectedTypes.includes(t.id);
                return (
                  <button
                    key={t.id}
                    onClick={() => toggleType(t.id)}
                    className={`px-3 py-1.5 rounded border transition-all uppercase tracking-wider ${
                      checked
                        ? "bg-neutral-900 border-cyan-500/60 text-cyan-300 font-bold"
                        : "bg-black border-neutral-800 text-neutral-500 hover:text-neutral-300"
                    }`}
                  >
                    {checked ? "☑" : "☐"} {t.label}
                  </button>
                );
              })}
            </div>

            <button
              onClick={handleScan}
              disabled={isScanning}
              className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-black font-bold uppercase tracking-widest rounded transition-all shadow-md disabled:opacity-50"
            >
              {isScanning ? "SCANNING SATELLITE STACKS..." : "[ SCAN AREA FOR CHANGES ]"}
            </button>
          </div>
        </div>

        {/* Scan Summary Banner (Requirement 13) */}
        {scanComplete && (
          <div className="space-y-4 font-mono">
            <div className="p-4 rounded-lg bg-neutral-950 border border-emerald-900/40 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="w-3 h-3 rounded-full bg-emerald-400 animate-ping" />
                <div>
                  <h2 className="text-sm font-bold text-white uppercase tracking-wider">
                    SCAN COMPLETE &mdash; 147 CANDIDATE CHANGES DETECTED
                  </h2>
                  <p className="text-[11px] text-neutral-500 font-sans mt-0.5">
                    AOI: Delhi NCR Corridor &middot; 2022 to 2026 stack &middot; False-alarm suppression applied
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3 text-xs">
                <span className="px-2.5 py-1 rounded bg-amber-950/40 border border-amber-800 text-amber-300">
                  Construction: <strong>64</strong>
                </span>
                <span className="px-2.5 py-1 rounded bg-orange-950/40 border border-orange-800 text-orange-300">
                  Clearance: <strong>31</strong>
                </span>
                <span className="px-2.5 py-1 rounded bg-cyan-950/40 border border-cyan-800 text-cyan-300">
                  Water: <strong>28</strong>
                </span>
                <span className="px-2.5 py-1 rounded bg-blue-950/40 border border-blue-800 text-blue-300">
                  Roads: <strong>24</strong>
                </span>
              </div>
            </div>

            {/* Candidate Events Table */}
            <div className="rounded-lg bg-neutral-950 border border-neutral-800 overflow-hidden">
              <div className="px-5 py-3 border-b border-neutral-800 flex items-center justify-between bg-black">
                <span className="text-xs font-bold text-white uppercase tracking-wider">
                  HIGH-PRIORITY CANDIDATE CHANGES
                </span>
                <span className="text-[10px] text-neutral-500">SORTED BY CONFIDENCE</span>
              </div>

              <div className="divide-y divide-neutral-900">
                {candidates.map((c, idx) => (
                  <div
                    key={c.id}
                    className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-neutral-900/40 transition-colors"
                  >
                    <div className="flex items-start gap-4">
                      <span className="text-cyan-400 font-bold text-sm">
                        #{String(idx + 1).padStart(2, "0")}
                      </span>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-white uppercase text-xs">
                            {c.type}
                          </span>
                          <span className="text-[10px] px-1.5 py-0.2 rounded bg-neutral-900 border border-neutral-700 text-emerald-400 font-bold">
                            {Math.round(c.confidence * 100)}% CONF
                          </span>
                          <span className="text-[10px] text-neutral-500">
                            {c.dateRange}
                          </span>
                        </div>
                        <p className="text-[11px] text-neutral-400 font-sans mt-0.5">
                          {c.location} &middot; {c.coordinates[1].toFixed(4)}°N, {c.coordinates[0].toFixed(4)}°E
                        </p>
                        <div className="flex items-center gap-3 text-[10px] text-neutral-500 mt-1">
                          <span>Area: <strong className="text-neutral-300">{c.areaM2.toLocaleString()} m²</strong></span>
                          <span>Sensor: <strong className="text-neutral-300">{c.sensor}</strong></span>
                          <span>Evidence: <strong className="text-cyan-400">{c.evidenceCount} passes</strong></span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <Link
                        href={`/workspace`}
                        className="px-3 py-1.5 rounded bg-neutral-900 hover:bg-neutral-800 border border-neutral-700 text-cyan-400 text-[10px] uppercase font-bold tracking-wider transition-all"
                      >
                        [ INSPECT IN WORKSPACE ]
                      </Link>
                      <Link
                        href={`/review`}
                        className="px-3 py-1.5 rounded bg-emerald-950/40 hover:bg-emerald-900/40 border border-emerald-700 text-emerald-400 text-[10px] uppercase font-bold tracking-wider transition-all"
                      >
                        [ TRIAGE ]
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

      </div>
    </main>
  );
}
