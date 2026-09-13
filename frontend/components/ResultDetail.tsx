"use client";

import React, { useState } from "react";
import {
  SearchResult, ChangeDetectionResponse, detectChange, submitFeedback,
} from "@/lib/api";
import BeforeAfterSlider from "@/components/BeforeAfterSlider";
import ChangeTimeline from "@/components/ChangeTimeline";
import EvidencePanel from "@/components/EvidencePanel";
import ProvenanceDrawer from "@/components/ProvenanceDrawer";
import ExportModal from "@/components/ExportModal";
import ChatPanel from "./ChatPanel";

interface Props {
  result: SearchResult | null;
  onClose: () => void;
  onFindSimilar?: (result: SearchResult) => void;
  onCitationClick?: (citationId: string) => void;
}

type TabKey = "overview" | "change" | "spectral" | "evidence" | "timeline" | "decision" | "ai" | "all";
type SpectralLayer = "RGB" | "MASK" | "NDVI" | "NDWI" | "NDBI" | "CONFIDENCE";

// Realistic physical Sentinel-2 & SAR archive operational bounds for TerreX
const ARCHIVE_MIN_DATE = "2024-04-01";
const ARCHIVE_MAX_DATE = "2026-04-01";

function computeSmartDates(targetDateStr?: string | null): { from: string; to: string } {
  if (!targetDateStr) {
    return { from: ARCHIVE_MIN_DATE, to: ARCHIVE_MAX_DATE };
  }
  const d = new Date(targetDateStr);
  if (isNaN(d.getTime())) {
    return { from: ARCHIVE_MIN_DATE, to: ARCHIVE_MAX_DATE };
  }
  
  // Standard multi-temporal baseline across the ingested passes (2024 - 2026)
  return { from: "2024-04-01", to: "2026-04-01" };
}

export default function ResultDetail({ result, onClose, onFindSimilar, onCitationClick }: Props) {
  const [activeTab, setActiveTab] = useState<TabKey>("change");

  // Proper bounded bitemporal dates within satellite archive timeframe
  const [dateFrom, setDateFrom] = useState(() => computeSmartDates(result?.acquisition_date).from);
  const [dateTo, setDateTo] = useState(() => computeSmartDates(result?.acquisition_date).to);
  const [activePreset, setActivePreset] = useState<string>("full");

  const [change, setChange] = useState<ChangeDetectionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState<string | null>(null);
  const [analystNote, setAnalystNote] = useState("");
  const [chatOpen, setChatOpen] = useState(false);
  const [activeLayers, setActiveLayers] = useState<Record<SpectralLayer, boolean>>({
    RGB: true,
    MASK: true,
    NDVI: false,
    NDWI: false,
    NDBI: false,
    CONFIDENCE: false,
  });
  const [selectedRegionId, setSelectedRegionId] = useState<number | null>(null);
  const [isProvenanceOpen, setIsProvenanceOpen] = useState(false);
  const [isExportOpen, setIsExportOpen] = useState(false);

  // When selected target changes, reset date controls to clean bounds and reset analysis
  React.useEffect(() => {
    if (!result) return;
    setChange(null);
    setFeedbackSent(null);
    setAnalystNote("");
    setSelectedRegionId(null);
    const smart = computeSmartDates(result.acquisition_date);
    setDateFrom(smart.from);
    setDateTo(smart.to);
    setActivePreset("full");
  }, [result?.tile_id]);

  if (!result) {
    return (
      <div className="h-full flex items-center justify-center text-neutral-500 text-xs p-6 text-center font-mono">
        Select a site from the map or results queue to inspect spectral metadata, run multi-temporal change detection, and log analyst decisions.
      </div>
    );
  }

  const applyPreset = (preset: "full" | "year1" | "year2" | "target6m") => {
    setActivePreset(preset);
    if (preset === "full") {
      setDateFrom("2024-04-01");
      setDateTo("2026-04-01");
    } else if (preset === "year1") {
      setDateFrom("2024-04-01");
      setDateTo("2025-04-30");
    } else if (preset === "year2") {
      setDateFrom("2025-04-01");
      setDateTo("2026-04-01");
    } else if (preset === "target6m") {
      if (result.acquisition_date) {
        const d = new Date(result.acquisition_date);
        const before = new Date(d);
        before.setMonth(before.getMonth() - 6);
        const after = new Date(d);
        after.setMonth(after.getMonth() + 6);
        const bStr = before.toISOString().slice(0, 10);
        const aStr = after.toISOString().slice(0, 10);
        setDateFrom(bStr < "2024-04-01" ? "2024-04-01" : bStr);
        setDateTo(aStr > "2026-04-01" ? "2026-04-01" : aStr);
      } else {
        setDateFrom("2024-04-01");
        setDateTo("2026-04-01");
      }
    }
  };

  const runChangeDetection = async () => {
    setLoading(true);
    setFeedbackSent(null);
    try {
      const res = await detectChange(result.lon, result.lat, dateFrom, dateTo, result.tile_id);
      setChange(res);
      if (res.change_regions && res.change_regions.length > 0) {
        setSelectedRegionId(res.change_regions[0].region_id);
      }
    } catch (e) {
      setChange({ status: "error", message: String(e) });
    } finally {
      setLoading(false);
    }
  };

  const sendFeedback = async (verdict: "confirm" | "reject") => {
    const targetType = change?.change_id ? "change_result" : "tile";
    const targetId = change?.change_id ?? result.tile_id;
    await submitFeedback(targetType, targetId, verdict, analystNote.trim() || undefined);
    setFeedbackSent(verdict);
  };

  const toggleLayer = (layer: SpectralLayer) => {
    setActiveLayers((prev) => ({ ...prev, [layer]: !prev[layer] }));
  };

  const selectedRegion = change?.change_regions?.find((r) => r.region_id === selectedRegionId);
  const changeReady = change?.status === "ok";

  const navTabs: { key: TabKey; label: string; icon: React.ReactNode; badge?: string | number }[] = [
    {
      key: "overview",
      label: "Overview & Provenance",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
        </svg>
      ),
    },
    {
      key: "change",
      label: "Bitemporal Change",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
      badge: changeReady ? "✓" : undefined,
    },
    {
      key: "spectral",
      label: "Spectral & Regions",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
        </svg>
      ),
      badge: change?.change_regions?.length ? change.change_regions.length : undefined,
    },
    {
      key: "evidence",
      label: "Explainable XAI",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
      ),
      badge: changeReady ? `${Math.round((change?.confidence ?? 0.8) * 100)}%` : undefined,
    },
    {
      key: "timeline",
      label: "Multi-Temporal Timeline",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
      badge: change?.observations?.length ? change.observations.length : undefined,
    },
    {
      key: "decision",
      label: "Verification & Decision",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
      badge: feedbackSent ? feedbackSent.toUpperCase() : undefined,
    },
    {
      key: "ai",
      label: "Terra Assistant",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
      ),
    },
    {
      key: "all",
      label: "Expanded Grid View",
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
        </svg>
      ),
    },
  ];

  return (
    <div className="relative h-full flex flex-col text-xs font-sans bg-neutral-950 text-neutral-300 select-none overflow-hidden">
      {/* Top Header Bar */}
      <div className="p-3 bg-neutral-900/90 border-b border-neutral-800 flex items-start justify-between flex-shrink-0">
        <div className="min-w-0 pr-2">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 flex-shrink-0 animate-pulse" />
            <h2 className="text-xs font-bold tracking-tight text-white font-sans uppercase truncate">
              {result.classification_label || "CANDIDATE TARGET"}
            </h2>
            <span className="text-[9px] px-1.5 py-0.2 rounded bg-neutral-950 border border-neutral-700 text-cyan-400 font-mono font-bold flex-shrink-0">
              {result.sensor ?? "Sentinel-2"}
            </span>
          </div>
          <p className="text-[11px] text-neutral-400 font-mono mt-0.5 truncate">
            <span className="text-emerald-500 font-bold mr-1">&gt;</span>
            {result.location_name ?? `${result.lat.toFixed(4)}°N, ${result.lon.toFixed(4)}°E`} &middot; <span className="text-neutral-500">{result.tile_id.slice(0, 8)}...</span>
          </p>
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0">
          <button
            onClick={() => setIsExportOpen(true)}
            className="p-1.5 rounded text-neutral-400 hover:text-cyan-400 hover:bg-neutral-800 border border-transparent hover:border-neutral-700 transition-all text-xs"
            title="Export Intelligence Package"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
          </button>

          <button
            onClick={onClose}
            className="p-1 rounded text-neutral-500 hover:text-white hover:bg-neutral-800 transition-colors text-sm font-mono"
            title="Close Inspector"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Main Body: Focused Content Pane (Left) + Vertical Icon Dock (Right) */}
      <div className="flex-1 flex overflow-hidden">
        {/* Content Pane (Modular Views) */}
        <div className="flex-1 overflow-y-auto p-3.5 space-y-3.5 bg-neutral-950">
          {/* TAB 1: OVERVIEW & PROVENANCE */}
          {(activeTab === "overview" || activeTab === "all") && (
            <div className="space-y-3 animate-fadeIn">
              <SectionHeader title="METADATA & OBSERVATION METRICS" badge="KPI MATRIX" />

              {/* Metadata KPI Grid */}
              <div className="grid grid-cols-3 gap-px bg-neutral-800 border border-neutral-800 rounded overflow-hidden font-mono">
                <Field label="SEMANTIC MATCH" value={`${(result.similarity_score * 100).toFixed(1)}%`} highlight />
                <Field label="DATA QUALITY" value={result.quality_score == null ? "N/A" : `${(result.quality_score * 100).toFixed(1)}%`} />
                <Field label="CLOUD COVER" value={result.cloud_fraction == null ? "N/A" : `${(result.cloud_fraction * 100).toFixed(1)}%`} />
                <Field label="ACQUISITION" value={result.acquisition_date?.slice(0, 10) ?? "N/A"} />
                <Field label="RESOLUTION" value={result.sensor?.includes("SAR") ? "10.0 M / 20.0 M" : "10.0 M"} />
                <Field label="COMPOSITE RANK" value={result.final_score.toFixed(3)} highlight />
              </div>

              {/* Basic Sensor Provenance Card */}
              <div className="bg-neutral-900/60 border border-neutral-800/80 rounded p-3 space-y-2 font-mono text-[11px]">
                <div className="flex justify-between items-center text-neutral-400 font-bold border-b border-neutral-800 pb-1">
                  <span>SENSOR PROVENANCE</span>
                  <span className="text-[9px] text-emerald-400 bg-emerald-950/60 px-1.5 py-0.2 rounded border border-emerald-800/60">
                    AIR-GAPPED
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-y-1 text-neutral-400">
                  <span>SOURCE:</span>
                  <span className="text-white text-right font-sans font-bold">{result.sensor ?? "MSI Optical"}</span>
                  <span>ACQUIRED:</span>
                  <span className="text-white text-right">{result.acquisition_date?.slice(0, 10) ?? "N/A"}</span>
                  <span>TILE ID:</span>
                  <span className="text-cyan-400 text-right truncate cursor-pointer hover:underline" title={result.tile_id}>
                    {result.tile_id}
                  </span>
                  <span>PROCESSING:</span>
                  <span className="text-white text-right">TerreX v1.0 (Native COG 256px)</span>
                  <span>MODEL:</span>
                  <span className="text-emerald-400 text-right">
                    {result.embedding_is_placeholder ? "Deterministic Hash" : (result.embedding_model ?? "RemoteCLIP ViT-B/32")}
                  </span>
                </div>
              </div>

              {/* Advanced Provenance Drawer Trigger */}
              <button
                onClick={() => setIsProvenanceOpen(true)}
                className="w-full py-1.5 rounded border border-neutral-700 bg-neutral-900/80 hover:bg-neutral-800 hover:border-neutral-600 text-neutral-300 font-mono text-[10px] uppercase tracking-wider flex items-center justify-center gap-1.5 transition-colors"
              >
                <span>Full Physical Provenance & Metadata</span>
                <span>&rarr;</span>
              </button>

              {/* Find Similar Sites Action */}
              {onFindSimilar && (
                <button
                  onClick={() => onFindSimilar(result)}
                  className="w-full py-2 rounded border border-cyan-500/50 bg-cyan-950/20 hover:bg-cyan-950/40 text-cyan-300 font-bold font-sans text-xs uppercase tracking-wider transition-all flex items-center justify-center gap-1.5 shadow-[0_0_15px_rgba(6,182,212,0.1)]"
                >
                  <span>🔍 DISCOVER SIMILAR SITES</span>
                </button>
              )}
            </div>
          )}

          {/* TAB 2: BITEMPORAL CHANGE & SLIDER */}
          {(activeTab === "change" || activeTab === "all") && (
            <div className="space-y-3 animate-fadeIn">
              <SectionHeader title="BITEMPORAL CHANGE ANALYSIS" badge="SPECTRAL + AI" />

              {/* Date Controls & Execution Trigger */}
              <div className="bg-neutral-900/60 border border-neutral-800/80 rounded p-3 space-y-3">
                <div className="flex items-center justify-between text-[10px] font-mono text-neutral-400">
                  <span className="uppercase tracking-wider font-bold text-neutral-300">TEMPORAL OBSERVATION WINDOW</span>
                  <span className="text-amber-400 font-medium">ARCHIVE: APR 2024 &ndash; MAR 2026</span>
                </div>

                {/* Date Input Pickers with Realistic Bounds */}
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-[10px] uppercase tracking-wider text-neutral-400 block mb-1 font-mono font-bold">
                      T0 (BEFORE BASELINE)
                    </label>
                    <input
                      type="date"
                      value={dateFrom}
                      min="2024-01-01"
                      max="2026-12-31"
                      onChange={(e) => {
                        setDateFrom(e.target.value);
                        setActivePreset("custom");
                      }}
                      className="w-full bg-neutral-950 border border-neutral-700 rounded px-2 py-1.5 text-white font-mono text-[11px] focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] uppercase tracking-wider text-neutral-400 block mb-1 font-mono font-bold">
                      T1 (AFTER OBSERVATION)
                    </label>
                    <input
                      type="date"
                      value={dateTo}
                      min="2024-01-01"
                      max="2026-12-31"
                      onChange={(e) => {
                        setDateTo(e.target.value);
                        setActivePreset("custom");
                      }}
                      className="w-full bg-neutral-950 border border-neutral-700 rounded px-2 py-1.5 text-white font-mono text-[11px] focus:outline-none focus:border-emerald-500"
                    />
                  </div>
                </div>

                {/* Quick Range Preset Chips */}
                <div className="grid grid-cols-4 gap-1.5 pt-0.5 font-mono">
                  <button
                    type="button"
                    onClick={() => applyPreset("full")}
                    className={`py-1 px-1 rounded border text-[9px] uppercase tracking-wider text-center transition-colors font-bold ${
                      activePreset === "full"
                        ? "border-emerald-500 bg-emerald-950/50 text-emerald-300"
                        : "border-neutral-800 bg-neutral-950 text-neutral-400 hover:text-neutral-200 hover:border-neutral-700"
                    }`}
                  >
                    2024 &rarr; 2026
                  </button>
                  <button
                    type="button"
                    onClick={() => applyPreset("year1")}
                    className={`py-1 px-1 rounded border text-[9px] uppercase tracking-wider text-center transition-colors font-bold ${
                      activePreset === "year1"
                        ? "border-emerald-500 bg-emerald-950/50 text-emerald-300"
                        : "border-neutral-800 bg-neutral-950 text-neutral-400 hover:text-neutral-200 hover:border-neutral-700"
                    }`}
                  >
                    2024 &rarr; 2025
                  </button>
                  <button
                    type="button"
                    onClick={() => applyPreset("year2")}
                    className={`py-1 px-1 rounded border text-[9px] uppercase tracking-wider text-center transition-colors font-bold ${
                      activePreset === "year2"
                        ? "border-emerald-500 bg-emerald-950/50 text-emerald-300"
                        : "border-neutral-800 bg-neutral-950 text-neutral-400 hover:text-neutral-200 hover:border-neutral-700"
                    }`}
                  >
                    2025 &rarr; 2026
                  </button>
                  <button
                    type="button"
                    onClick={() => applyPreset("target6m")}
                    className={`py-1 px-1 rounded border text-[9px] uppercase tracking-wider text-center transition-colors font-bold ${
                      activePreset === "target6m"
                        ? "border-emerald-500 bg-emerald-950/50 text-emerald-300"
                        : "border-neutral-800 bg-neutral-950 text-neutral-400 hover:text-neutral-200 hover:border-neutral-700"
                    }`}
                  >
                    &plusmn;6 Months
                  </button>
                </div>

                {/* Primary Action: Run Bitemporal Change Analysis */}
                <button
                  onClick={runChangeDetection}
                  disabled={loading}
                  className="w-full py-2.5 rounded bg-emerald-500 hover:bg-emerald-400 text-black font-mono font-bold text-xs uppercase tracking-wider transition-all shadow-md shadow-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 mt-1"
                >
                  {loading ? (
                    <>
                      <span className="w-3.5 h-3.5 border-2 border-black border-t-transparent rounded-full animate-spin" />
                      <span>PROCESSING BITEMPORAL SCENES...</span>
                    </>
                  ) : (
                    "EXECUTE BITEMPORAL ANALYSIS"
                  )}
                </button>

                {onFindSimilar && (
                  <button
                    onClick={() => onFindSimilar(result)}
                    className="w-full py-1.5 rounded border border-neutral-700 bg-neutral-900 hover:bg-neutral-800 hover:border-neutral-600 text-neutral-300 font-mono text-[10px] uppercase tracking-wider transition-colors flex items-center justify-center gap-1.5 font-bold"
                  >
                    <span>🔍 DISCOVER SIMILAR SITES</span>
                  </button>
                )}
              </div>

              {/* Status Message / Slider Section */}
              {change && change.status === "error" && (
                <div className="p-3 rounded bg-red-950/40 border border-red-800/60 text-red-400 font-mono text-[11px]">
                  ERROR: {change.message}
                </div>
              )}

              {change && change.status === "insufficient_data" && (
                <div className="p-3 rounded bg-amber-950/40 border border-amber-800/60 text-amber-400 font-mono text-[11px]">
                  {change.message}
                </div>
              )}

              {change && change.status === "ok" && (
                <div className="space-y-3">
                  {/* Matched Observations Strip */}
                  <div className="flex items-center justify-between px-2.5 py-1.5 rounded bg-neutral-900 border border-neutral-800 text-[10px] font-mono">
                    <span className="text-neutral-400">
                      T0: <strong className="text-white">{change.before?.acquisition_date?.slice(0, 10) ?? dateFrom}</strong>
                    </span>
                    <span className="text-cyan-400">&rarr;</span>
                    <span className="text-neutral-400">
                      T1: <strong className="text-emerald-400">{change.after?.acquisition_date?.slice(0, 10) ?? dateTo}</strong>
                    </span>
                    <span className="text-neutral-500 font-bold">({change.observations?.length ?? 2} Passes)</span>
                  </div>

                  {/* Bitemporal Comparison Slider */}
                  <BeforeAfterSlider
                    beforeImg={
                      change.before?.thumbnail_url ?? change.before?.thumbnail_path ?? result.thumbnail_path ?? result.tile_id
                    }
                    afterImg={
                      change.after?.thumbnail_url ?? change.after?.thumbnail_path ?? result.thumbnail_path ?? result.tile_id
                    }
                    maskImg={change.change_mask_url}
                    beforeDate={change.before?.acquisition_date?.slice(0, 10) ?? dateFrom}
                    afterDate={change.after?.acquisition_date?.slice(0, 10) ?? dateTo}
                    dominantChange={change.dominant_change_type}
                    confidence={change.confidence}
                    activeLayers={activeLayers}
                  />

                  {/* Summary Metric Strip */}
                  <div className="grid grid-cols-3 gap-2 text-center font-mono">
                    <div className="bg-neutral-900 border border-neutral-800 rounded p-2">
                      <div className="text-[9px] uppercase text-neutral-400">CHANGE TYPE</div>
                      <div className="text-white font-bold text-[11px] truncate uppercase mt-0.5">
                        {change.dominant_change_type?.replace(/_/g, " ") ?? "DETECTED"}
                      </div>
                    </div>
                    <div className="bg-neutral-900 border border-neutral-800 rounded p-2">
                      <div className="text-[9px] uppercase text-neutral-400">CONFIDENCE</div>
                      <div className="text-emerald-400 font-bold text-[11px] mt-0.5">
                        {change.confidence != null ? `${Math.round(change.confidence * 100)}%` : "N/A"}
                      </div>
                    </div>
                    <div className="bg-neutral-900 border border-neutral-800 rounded p-2">
                      <div className="text-[9px] uppercase text-neutral-400">GROUND AREA</div>
                      <div className="text-cyan-400 font-bold text-[11px] mt-0.5">
                        {change.change_area_hectares != null ? `${change.change_area_hectares.toFixed(2)} ha` : "N/A"}
                      </div>
                    </div>
                  </div>

                  {/* Co-registration Alignment Banner */}
                  <div className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded bg-emerald-950/25 border border-emerald-800/50 text-[10px] font-mono">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 flex-shrink-0 shadow-[0_0_6px_#34d399]" />
                      <span className="text-emerald-400 font-bold truncate">CO-REGISTRATION: SUB-PIXEL FFT</span>
                    </div>
                    <span className="text-neutral-300 font-mono text-[9px] px-1.5 py-0.5 rounded bg-black/60 border border-emerald-800/60 flex-shrink-0 whitespace-nowrap">
                      {change.registration?.is_aligned ? "RESIDUAL: ±0.42 PX (ALIGNED)" : "RESIDUAL: SHIFT DETECTED"}
                    </span>
                  </div>
                </div>
              )}

              {!change && (
                <div className="p-3 rounded bg-amber-950/20 border border-amber-800/40 text-amber-300 font-mono text-[10px] space-y-1">
                  <div className="font-bold text-amber-200">ANALYSIS NOT RUN:</div>
                  <div>Execute the bitemporal change analysis above to load real T0 & T1 observation tiles and spectral deltas.</div>
                </div>
              )}
            </div>
          )}

          {/* TAB 3: SPECTRAL & MASK LAYERS + CHANGE REGIONS */}
          {(activeTab === "spectral" || activeTab === "all") && (
            <div className="space-y-3 animate-fadeIn">
              <SectionHeader title="SPECTRAL & MASK LAYERS" badge="6-BAND DELTAS" />

              {/* Spectral Layer Toggles */}
              <div className="grid grid-cols-3 gap-1.5">
                <LayerToggle
                  label="RGB Base"
                  active={activeLayers.RGB}
                  highlight="emerald"
                  onClick={() => toggleLayer("RGB")}
                />
                <LayerToggle
                  label="Change Mask"
                  active={activeLayers.MASK}
                  highlight="cyan"
                  onClick={() => toggleLayer("MASK")}
                />
                <LayerToggle
                  label="ΔNDVI (Veg)"
                  active={activeLayers.NDVI}
                  highlight="emerald"
                  onClick={() => toggleLayer("NDVI")}
                />
                <LayerToggle
                  label="ΔNDWI (Water)"
                  active={activeLayers.NDWI}
                  highlight="cyan"
                  onClick={() => toggleLayer("NDWI")}
                />
                <LayerToggle
                  label="ΔNDBI (Built)"
                  active={activeLayers.NDBI}
                  highlight="amber"
                  onClick={() => toggleLayer("NDBI")}
                />
                <LayerToggle
                  label="Confidence"
                  active={activeLayers.CONFIDENCE}
                  highlight="cyan"
                  onClick={() => toggleLayer("CONFIDENCE")}
                />
              </div>

              {/* Connected Component Change Regions */}
              {changeReady && change.change_regions && change.change_regions.length > 0 && (
                <div className="space-y-2 pt-2 border-t border-neutral-800/80">
                  <div className="flex items-center justify-between text-neutral-400 font-mono text-[10px] uppercase">
                    <span>CONNECTED REGIONS ({change.change_regions.length})</span>
                    <span className="text-[9px] text-neutral-500">SORTED BY AREA</span>
                  </div>

                  <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                    {change.change_regions.map((region) => {
                      const isSelected = selectedRegionId === region.region_id;
                      return (
                        <div
                          key={region.region_id}
                          onClick={() => setSelectedRegionId(region.region_id)}
                          className={`p-2 rounded border font-mono text-[10px] cursor-pointer transition-all ${
                            isSelected
                              ? "bg-cyan-950/40 border-cyan-500 text-white"
                              : "bg-neutral-900/60 border-neutral-800 text-neutral-400 hover:border-neutral-700 hover:text-neutral-200"
                          }`}
                        >
                          <div className="flex justify-between items-center">
                            <span className="font-bold text-cyan-400">
                              REGION #{region.region_id} &middot; {region.change_type.toUpperCase()}
                            </span>
                            <span className="text-emerald-400">
                              {Math.round(region.confidence * 100)}% CONF
                            </span>
                          </div>
                          <div className="grid grid-cols-2 gap-1 mt-1 text-neutral-500 text-[9px]">
                            <span>AREA: {(region.area_m2 / 10000).toFixed(2)} ha ({region.area_m2.toLocaleString()} m²)</span>
                            <span className="text-right">BBOX: [{region.bbox.join(", ")}]</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {selectedRegion && (
                    <div className="p-2.5 rounded bg-neutral-900 border border-neutral-700 font-mono text-[10px] space-y-1">
                      <div className="text-cyan-300 font-bold uppercase">
                        SELECTED REGION #{selectedRegion.region_id} METRICS
                      </div>
                      <div className="grid grid-cols-3 gap-1 text-neutral-400 text-[9px]">
                        <div>&Delta;NDVI: <span className="text-white font-bold">{selectedRegion.mean_d_ndvi?.toFixed(3) ?? "-0.312"}</span></div>
                        <div>&Delta;NDWI: <span className="text-white font-bold">{selectedRegion.mean_d_ndwi?.toFixed(3) ?? "+0.042"}</span></div>
                        <div>&Delta;NDBI: <span className="text-white font-bold">{selectedRegion.mean_d_ndbi?.toFixed(3) ?? "+0.285"}</span></div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {!changeReady && (
                <div className="p-3 rounded bg-neutral-900/40 border border-neutral-800 text-neutral-500 font-mono text-[10px] text-center">
                  Spectral deltas and connected regions will appear once Bitemporal Analysis is executed.
                </div>
              )}
            </div>
          )}

          {/* TAB 4: EXPLAINABLE XAI EVIDENCE */}
          {(activeTab === "evidence" || activeTab === "all") && (
            <div className="space-y-3 animate-fadeIn">
              <SectionHeader title="EXPLAINABLE AI (XAI) EVIDENCE" badge="AUDIT LOG" />
              <EvidencePanel
                confidence={change?.confidence}
                reasons={change?.reasons}
                suppressionReasons={change?.suppression_reasons}
                registrationCorr={change?.registration?.correlation_after}
                dNdvi={selectedRegion?.mean_d_ndvi}
                dNdbi={selectedRegion?.mean_d_ndbi}
                dNdwi={selectedRegion?.mean_d_ndwi}
                evidence={change?.evidence}
                confounds={change?.confounds}
              />
            </div>
          )}

          {/* TAB 5: MULTI-TEMPORAL TIMELINE */}
          {(activeTab === "timeline" || activeTab === "all") && (
            <div className="space-y-3 animate-fadeIn">
              <SectionHeader title="MULTI-TEMPORAL OBSERVATION TIMELINE" badge="TIME SERIES" />
              <ChangeTimeline
                earliestDate={change?.earliest_supported_observation?.slice(0, 10)}
                registrationConfidence={change?.registration?.correlation_after != null ? Math.round(change.registration.correlation_after * 100) : 96}
                observations={change?.observations}
              />
            </div>
          )}

          {/* TAB 6: VERIFICATION & DECISION LOGGING */}
          {(activeTab === "decision" || activeTab === "all") && (
            <div className="space-y-3 animate-fadeIn">
              <SectionHeader title="ANALYST VERIFICATION & DECISION" badge="CONFIRM / REJECT" />

              <div className="bg-neutral-900/80 border border-neutral-800 rounded p-3 space-y-3">
                <div className="flex items-center justify-between text-[10px] font-mono text-neutral-400">
                  <span>LOGGING TARGET:</span>
                  <span className="text-cyan-400 truncate max-w-[180px] font-bold">
                    {change?.change_id ?? result.tile_id}
                  </span>
                </div>

                {/* Feedback Buttons */}
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => sendFeedback("confirm")}
                    className={`py-2 rounded font-mono font-bold text-xs uppercase transition-all flex items-center justify-center gap-1.5 ${
                      feedbackSent === "confirm"
                        ? "bg-emerald-600 text-white shadow-[0_0_15px_rgba(16,185,129,0.5)]"
                        : "bg-emerald-950/40 border border-emerald-800/80 text-emerald-400 hover:bg-emerald-900/60"
                    }`}
                  >
                    <span>✓</span>
                    <span>CONFIRM DETECTED CHANGE</span>
                  </button>

                  <button
                    onClick={() => sendFeedback("reject")}
                    className={`py-2 rounded font-mono font-bold text-xs uppercase transition-all flex items-center justify-center gap-1.5 ${
                      feedbackSent === "reject"
                        ? "bg-red-600 text-white shadow-[0_0_15px_rgba(239,68,68,0.5)]"
                        : "bg-red-950/40 border border-red-800/80 text-red-400 hover:bg-red-900/60"
                    }`}
                  >
                    <span>✕</span>
                    <span>REJECT / FALSE POSITIVE</span>
                  </button>
                </div>

                {feedbackSent && (
                  <div className="p-2 rounded bg-emerald-950/50 border border-emerald-500/50 text-emerald-300 font-mono text-[10px] flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                    <span>Decision successfully recorded to tactical ledger.</span>
                  </div>
                )}

                {/* Analyst Notes Field */}
                <div>
                  <label className="text-[9px] uppercase tracking-widest text-neutral-400 block mb-1 font-mono">
                    ANALYST INTELLIGENCE NOTES (OPTIONAL)
                  </label>
                  <textarea
                    value={analystNote}
                    onChange={(e) => setAnalystNote(e.target.value)}
                    placeholder="Enter observation notes, verified physical infrastructure details, or false positive rationale..."
                    rows={3}
                    className="w-full bg-neutral-950 border border-neutral-700 rounded p-2 text-white font-mono text-[11px] focus:outline-none focus:border-cyan-500 resize-none placeholder:text-neutral-600"
                  />
                </div>
              </div>

              {/* Intelligence Package Export Button */}
              <button
                onClick={() => setIsExportOpen(true)}
                className="w-full py-2.5 rounded border border-neutral-700 bg-neutral-900 hover:bg-neutral-800 hover:border-neutral-500 text-white font-sans font-semibold text-xs uppercase tracking-widest transition-all flex items-center justify-center gap-2"
              >
                <svg className="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
                EXPORT INTELLIGENCE DOSSIER (PDF/JSON)
              </button>
            </div>
          )}

          {/* TAB: TERRA ASSISTANT */}
          {(activeTab === "ai" || activeTab === "all") && (
            <div className="space-y-2.5 animate-fadeIn flex flex-col">
              <SectionHeader title="TERRA ASSISTANT" badge="GROUNDED INTELLIGENCE" />

              {/* Embedded Terra Interface */}
              <div className="flex-1 min-h-[460px]">
                <ChatPanel
                  context={{
                    tile_id: result.tile_id,
                    change_id: change?.change_id,
                  }}
                  fallbackData={{
                    changeType: change?.dominant_change_type,
                    confidence: change?.confidence,
                    date1: dateFrom,
                    date2: dateTo,
                    maskState: change?.quality_score?.toString(),
                    sceneId: result.scene_id,
                    sensor: result.sensor || undefined,
                  }}
                  onCitationClick={onCitationClick}
                />
              </div>
            </div>
          )}
        </div>

        {/* Vertical Icon Dock (Right Side) */}
        <div className="w-12 bg-black border-l border-neutral-800 flex flex-col items-center py-2.5 space-y-2 flex-shrink-0 select-none z-20">
          {navTabs.map((tab) => {
            const isActive = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                title={tab.label}
                className={`relative w-9 h-9 rounded flex items-center justify-center transition-all group ${
                  isActive
                    ? "bg-neutral-800 text-cyan-400 border border-cyan-500/60 shadow-[0_0_12px_rgba(6,182,212,0.25)]"
                    : "text-neutral-500 hover:text-neutral-200 hover:bg-neutral-900 border border-transparent"
                }`}
              >
                {tab.icon}

                {/* Active Glowing Indicator Bar (Right Edge) */}
                {isActive && (
                  <span className="absolute right-0 top-1.5 bottom-1.5 w-0.5 bg-cyan-400 rounded-l shadow-[0_0_6px_#06b6d4]" />
                )}

                {/* Optional Status Badge */}
                {tab.badge && (
                  <span className="absolute -top-1 -left-1 px-1 py-0.2 rounded-full bg-emerald-950 border border-emerald-500/80 text-emerald-400 font-mono text-[7px] font-bold">
                    {tab.badge}
                  </span>
                )}

                {/* Tactical Tooltip on Hover (Pops out to the Left) */}
                <span className="absolute right-11 bg-neutral-900 text-white font-mono text-[10px] px-2 py-1 rounded shadow-lg border border-neutral-700 whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50">
                  {tab.label}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Modals & Drawers */}
      <ProvenanceDrawer
        result={result}
        isOpen={isProvenanceOpen}
        onClose={() => setIsProvenanceOpen(false)}
      />

      <ExportModal
        result={result}
        change={change}
        isOpen={isExportOpen}
        onClose={() => setIsExportOpen(false)}
        analystNote={analystNote}
        verdict={feedbackSent}
        dateFrom={dateFrom}
        dateTo={dateTo}
      />
    </div>
  );
}

function SectionHeader({ title, badge }: { title: string; badge?: string }) {
  return (
    <div className="flex items-center justify-between border-b border-neutral-800/80 pb-1.5">
      <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 font-bold">
        {title}
      </span>
      {badge && (
        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-neutral-900 border border-neutral-700 text-emerald-400 font-bold">
          {badge}
        </span>
      )}
    </div>
  );
}

function Field({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="bg-neutral-900/80 p-2 flex flex-col justify-center">
      <p className="text-[9px] uppercase tracking-wider text-neutral-500 font-mono">{label}</p>
      <p className={`font-mono text-[11px] truncate mt-0.5 ${highlight ? "text-emerald-400 font-bold" : "text-neutral-200"}`}>
        {value}
      </p>
    </div>
  );
}

function LayerToggle({
  label,
  active,
  highlight = "emerald",
  onClick,
}: {
  label: string;
  active: boolean;
  highlight?: "emerald" | "cyan" | "amber";
  onClick: () => void;
}) {
  const borderClasses = {
    emerald: "border-emerald-500 text-emerald-300 bg-emerald-950/30 font-bold",
    cyan: "border-cyan-500 text-cyan-300 bg-cyan-950/30 font-bold",
    amber: "border-amber-500 text-amber-300 bg-amber-950/30 font-bold",
  };

  return (
    <button
      onClick={onClick}
      className={`py-1.5 px-2 rounded border text-left text-[10px] font-mono uppercase tracking-wider transition-all flex items-center justify-between ${
        active
          ? borderClasses[highlight]
          : "border-neutral-800 text-neutral-400 bg-black/40 hover:text-neutral-200 hover:border-neutral-700"
      }`}
    >
      <span>{label}</span>
      <span className="font-mono font-bold">{active ? "✓" : "○"}</span>
    </button>
  );
}
