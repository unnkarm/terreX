"use client";

import React, { useState } from "react";
import Link from "next/link";
import TopNav from "@/components/TopNav";
import { ReviewQueueItem, getDemoReviewQueue, submitFeedback } from "@/lib/api";

export default function ReviewQueuePage() {
  const [queue, setQueue] = useState<ReviewQueueItem[]>(getDemoReviewQueue());
  const [selectedItem, setSelectedItem] = useState<ReviewQueueItem | null>(queue[0] || null);
  const [analystNote, setAnalystNote] = useState("");
  const [analystName, setAnalystName] = useState("ANALYST-ISRO-042");
  const [auditLog, setAuditLog] = useState<Array<{ id: string; target: string; verdict: string; time: string; note?: string }>>([
    { id: "aud-01", target: "Yamuna Embankment Link #03", verdict: "CONFIRMED", time: "10:14:20", note: "Structural foundation verified in 2 consecutive passes" },
    { id: "aud-02", target: "Hindon Canal Sector 12", verdict: "REJECTED", time: "09:45:10", note: "Seasonal water table oscillation, suppressed" },
  ]);
  const [submitting, setSubmitting] = useState(false);

  const handleDecision = async (verdict: "confirm" | "reject") => {
    if (!selectedItem) return;
    setSubmitting(true);
    try {
      await submitFeedback("change_result", selectedItem.targetId, verdict, analystNote.trim() || undefined);

      // Record in audit trail
      setAuditLog((prev) => [
        {
          id: `aud-${Date.now()}`,
          target: selectedItem.location,
          verdict: verdict.toUpperCase(),
          time: new Date().toLocaleTimeString(),
          note: analystNote.trim() || "Verified against multi-temporal imagery",
        },
        ...prev,
      ]);

      // Update queue item status
      setQueue((prev) =>
        prev.map((item) =>
          item.id === selectedItem.id
            ? { ...item, status: verdict === "confirm" ? "confirmed" : "rejected" }
            : item
        )
      );

      // Advance to next pending item if available
      const nextPending = queue.find((item) => item.id !== selectedItem.id && item.status === "pending");
      setSelectedItem(nextPending || null);
      setAnalystNote("");
    } catch (e) {
      console.error("Decision recording error:", e);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="min-h-screen w-screen bg-black text-neutral-300 font-sans flex flex-col select-none">
      <TopNav />

      <div className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8 space-y-6 font-mono">
        {/* Page Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-neutral-800 pb-8">
          <div className="space-y-3">
            <div className="font-mono text-xs text-radar font-semibold tracking-widest uppercase flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-radar animate-pulse"></span>
              <span>HUMAN-IN-THE-LOOP:</span>
              <span>DECISION TRIAGE</span>
            </div>
            
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-white font-sans leading-[1.1]">
              Ranked analyst
              <br />
              <span className="text-neutral-400 font-light">review queue.</span>
            </h1>

            <p className="text-base text-neutral-300 font-sans font-light max-w-2xl leading-relaxed">
              TerreX pairs high-resolution optical imagery with bitemporal Sentinel SAR radar data under an agentic vision-language model, returning calibrated confidence vectors and verifiable pixel evidence.
            </p>
          </div>

          <div className="flex items-center gap-4 text-xs font-mono">
            <div>
              <span className="text-neutral-500 uppercase tracking-widest block text-[9px]">OPERATOR STATION</span>
              <span className="text-cyan-400 font-bold text-xs">{analystName}</span>
            </div>
            <Link
              href="/workspace"
              className="px-6 py-3 bg-white text-black font-sans font-semibold text-xs tracking-widest uppercase hover:bg-neutral-200 transition-colors"
            >
              WORKSPACE
            </Link>
          </div>
        </div>

        {/* Main Triage View: Left Queue + Right Verification Panel */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-[560px]">
          
          {/* LEFT LIST: Ranked Candidates (5 Cols) */}
          <div className="lg:col-span-5 rounded-lg bg-neutral-950 border border-neutral-800 overflow-hidden flex flex-col">
            <div className="px-4 py-3 border-b border-neutral-800 flex items-center justify-between bg-black">
              <span className="text-xs font-bold text-white uppercase tracking-wider">
                PENDING QUEUE ({queue.filter((q) => q.status === "pending").length})
              </span>
              <span className="text-[10px] text-neutral-500 uppercase">SORTED BY URGENCY</span>
            </div>

            <div className="flex-1 overflow-y-auto divide-y divide-neutral-900">
              {queue.map((item, idx) => {
                const isSelected = selectedItem?.id === item.id;
                return (
                  <div
                    key={item.id}
                    onClick={() => setSelectedItem(item)}
                    className={`p-3.5 cursor-pointer transition-all ${
                      isSelected
                        ? "bg-neutral-900 border-l-4 border-cyan-500"
                        : "hover:bg-neutral-900/40 border-l-4 border-transparent"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-cyan-400 font-bold text-xs">
                          #{String(idx + 1).padStart(2, "0")}
                        </span>
                        <span className="font-bold text-white uppercase text-xs">
                          {item.type}
                        </span>
                      </div>
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                        item.status === "confirmed"
                          ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                          : item.status === "rejected"
                          ? "bg-red-950 text-red-400 border border-red-800"
                          : "bg-cyan-950 text-cyan-300 border border-cyan-800"
                      }`}>
                        {Math.round(item.confidence * 100)}% CONF
                      </span>
                    </div>

                    <p className="text-[11px] text-neutral-400 font-sans mt-1">
                      {item.location}
                    </p>

                    <div className="flex items-center justify-between text-[10px] text-neutral-500 mt-2 font-mono">
                      <span>{item.dateRange}</span>
                      <span>{item.areaM2.toLocaleString()} m²</span>
                      <span className="text-neutral-400 uppercase font-semibold">
                        {item.status}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* RIGHT PANEL: Verification Dossier & Decision (7 Cols) */}
          <div className="lg:col-span-7 rounded-lg bg-neutral-950 border border-neutral-800 p-6 flex flex-col justify-between space-y-6">
            {selectedItem ? (
              <div className="space-y-5">
                {/* Dossier Header */}
                <div className="border-b border-neutral-800 pb-3 flex items-start justify-between">
                  <div>
                    <span className="text-[10px] text-cyan-400 uppercase tracking-widest font-bold">
                      CANDIDATE DOSSIER &middot; {selectedItem.targetId}
                    </span>
                    <h2 className="text-base font-bold text-white uppercase tracking-wide mt-1">
                      {selectedItem.type}: {selectedItem.location}
                    </h2>
                    <p className="text-xs text-neutral-400 mt-0.5 font-sans">
                      Coordinates: {selectedItem.coordinates[1].toFixed(4)}°N, {selectedItem.coordinates[0].toFixed(4)}°E &middot; {selectedItem.sensor}
                    </p>
                  </div>

                  <Link
                    href="/workspace"
                    className="px-3 py-1.5 rounded bg-neutral-900 hover:bg-neutral-800 border border-neutral-700 text-cyan-400 text-[10px] uppercase font-bold tracking-wider"
                  >
                    INSPECT ON MAP ↗
                  </Link>
                </div>

                {/* Satellite Observation Preview Grid */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-2.5 rounded bg-black border border-neutral-800 space-y-1">
                    <span className="text-[10px] text-neutral-500 block uppercase">
                      T0 BASELINE OBSERVATION (2024)
                    </span>
                    <div className="w-full h-32 rounded bg-neutral-900 border border-neutral-800 overflow-hidden relative">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src="https://images.unsplash.com/photo-1581084324492-c8076f130f86?w=600&auto=format&fit=crop&q=80"
                        alt="baseline"
                        className="w-full h-full object-cover"
                      />
                    </div>
                  </div>

                  <div className="p-2.5 rounded bg-black border border-neutral-800 space-y-1">
                    <span className="text-[10px] text-cyan-400 block uppercase font-bold">
                      T1 RECENT OBSERVATION (2026)
                    </span>
                    <div className="w-full h-32 rounded bg-neutral-900 border border-neutral-800 overflow-hidden relative">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src="https://images.unsplash.com/photo-1528722828814-77b9b83aafb2?w=600&auto=format&fit=crop&q=80"
                        alt="current"
                        className="w-full h-full object-cover"
                      />
                    </div>
                  </div>
                </div>

                {/* Evidence Metrics */}
                <div className="grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="p-2.5 rounded bg-neutral-900/60 border border-neutral-800">
                    <span className="text-[9px] text-neutral-500 uppercase block">Calculated Area</span>
                    <span className="font-bold text-white text-sm">{selectedItem.areaM2.toLocaleString()} m²</span>
                  </div>
                  <div className="p-2.5 rounded bg-neutral-900/60 border border-neutral-800">
                    <span className="text-[9px] text-neutral-500 uppercase block">Model Confidence</span>
                    <span className="font-bold text-emerald-400 text-sm">{Math.round(selectedItem.confidence * 100)}%</span>
                  </div>
                  <div className="p-2.5 rounded bg-neutral-900/60 border border-neutral-800">
                    <span className="text-[9px] text-neutral-500 uppercase block">Registration Coherence</span>
                    <span className="font-bold text-cyan-400 text-sm">0.96 (ORB Warp)</span>
                  </div>
                </div>

                {/* Analyst Verification Decision Controls */}
                <div className="space-y-3 pt-2">
                  <span className="text-[10px] uppercase text-neutral-400 font-bold block">
                    ANALYST AUDIT REMARK
                  </span>
                  <textarea
                    value={analystNote}
                    onChange={(e) => setAnalystNote(e.target.value)}
                    placeholder="Enter formal justification (e.g. 'Structural foundation verified against consecutive passes without cloud artifact')..."
                    rows={2}
                    className="w-full bg-black border border-neutral-800 focus:border-neutral-600 rounded p-2.5 text-xs text-white outline-none font-sans"
                  />

                  <div className="flex gap-3">
                    <button
                      onClick={() => handleDecision("confirm")}
                      disabled={submitting}
                      className="flex-1 py-3 rounded bg-emerald-600 hover:bg-emerald-500 text-black font-bold uppercase tracking-widest text-xs transition-all shadow-md flex items-center justify-center gap-2"
                    >
                      [ ✓ CONFIRM DETECTION ]
                    </button>
                    <button
                      onClick={() => handleDecision("reject")}
                      disabled={submitting}
                      className="flex-1 py-3 rounded bg-neutral-900 hover:bg-red-950/40 border border-neutral-700 hover:border-red-500 text-neutral-300 hover:text-red-400 font-bold uppercase tracking-widest text-xs transition-all flex items-center justify-center gap-2"
                    >
                      [ ✕ REJECT / SUPPRESS ]
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="h-full flex items-center justify-center text-neutral-500 text-xs">
                Select a candidate from the review queue on the left.
              </div>
            )}

            {/* Audit History Log */}
            <div className="pt-4 border-t border-neutral-800 space-y-2">
              <span className="text-[10px] uppercase text-neutral-500 font-bold block">
                RECENT AUDIT COMMITS (IMMUTABLE LOG)
              </span>
              <div className="space-y-1 max-h-28 overflow-y-auto pr-1">
                {auditLog.map((log) => (
                  <div key={log.id} className="p-2 rounded bg-black/40 border border-neutral-800/80 flex items-center justify-between text-[10px]">
                    <div className="truncate max-w-[340px]">
                      <span className="text-neutral-300 font-bold">{log.target}:</span>{" "}
                      <span className="text-neutral-500 font-sans">{log.note}</span>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className={`font-bold px-1.5 py-0.2 rounded ${log.verdict === "CONFIRMED" ? "text-emerald-400 bg-emerald-950/40" : "text-red-400 bg-red-950/40"}`}>
                        {log.verdict}
                      </span>
                      <span className="text-neutral-600">{log.time}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

          </div>

        </div>

      </div>
    </main>
  );
}
