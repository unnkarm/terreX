"use client";

import React, { useState } from "react";
import {
  SearchResult, ChangeDetectionResponse, detectChange, submitFeedback, thumbnailUrl,
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

type SpectralLayer = "RGB" | "MASK" | "NDVI" | "NDWI" | "NDBI" | "CONFIDENCE";

export default function ResultDetail({ result, onClose, onFindSimilar, onCitationClick }: Props) {
  // Dynamic date defaults: start 18 months before acquisition_date (min 2023-01-01), end today+6m
  const [dateFrom, setDateFrom] = useState(() => {
    if (result?.acquisition_date) {
      const acq = new Date(result.acquisition_date);
      acq.setMonth(acq.getMonth() - 18);
      if (acq < new Date("2023-01-01")) return "2023-01-01";
      return acq.toISOString().slice(0, 10);
    }
    return "2023-01-01";
  });
  const [dateTo, setDateTo] = useState(() => {
    const future = new Date();
    future.setMonth(future.getMonth() + 6);
    return future.toISOString().slice(0, 10);
  });
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

  // When selected target changes, reset date controls and previous change analysis to fresh state
  React.useEffect(() => {
    if (!result) return;
    setChange(null);
    setFeedbackSent(null);
    setAnalystNote("");
    setSelectedRegionId(null);
    if (result.acquisition_date) {
      const acq = new Date(result.acquisition_date);
      acq.setMonth(acq.getMonth() - 18);
      setDateFrom(acq < new Date("2023-01-01") ? "2023-01-01" : acq.toISOString().slice(0, 10));
    } else {
      setDateFrom("2023-01-01");
    }
    const future = new Date();
    future.setMonth(future.getMonth() + 6);
    setDateTo(future.toISOString().slice(0, 10));
  }, [result?.tile_id]);

  if (!result) {
    return (
      <div className="h-full flex items-center justify-center text-neutral-500 text-xs p-6 text-center font-mono">
        Select a site from the map or results queue to inspect spectral metadata, run multi-temporal change detection, and log analyst decisions.
      </div>
    );
  }

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

  return (
    <div className="relative h-full overflow-y-auto p-4 space-y-4 text-xs font-sans bg-neutral-950 text-neutral-300">
      {/* Header Bar */}
      <div className="flex items-start justify-between border-b border-neutral-800 pb-2.5">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
            <h2 className="text-sm font-bold tracking-tight text-white font-sans uppercase">
              Target Site <span className="text-cyan-400 font-medium">[{result.classification_label ?? "NEW STRUCTURES"}]</span>
            </h2>
            <span className="text-[9px] px-1.5 py-0.5 rounded bg-neutral-900 border border-neutral-700 text-cyan-400 font-mono font-bold">
              {result.sensor ?? "Sentinel-2"}
            </span>
          </div>
          <p className="text-[11px] text-neutral-400 font-mono mt-1">
            <span className="text-emerald-500 font-bold mr-1">&gt;</span>
            {result.lat.toFixed(4)}°N, {result.lon.toFixed(4)}°E &middot; <span className="text-neutral-500">{result.tile_id.slice(0, 8)}...</span>
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* Ask AI Chat Toggle Button */}
          <button
            type="button"
            onClick={() => setChatOpen((open) => !open)}
            aria-expanded={chatOpen}
            title={chatOpen ? "Hide chat" : "Ask about this evidence"}
            className={`px-2 py-1 rounded border font-mono text-[10px] uppercase tracking-wider transition-colors ${
              chatOpen
                ? "border-blue-500/70 bg-blue-950/40 text-blue-300"
                : "border-neutral-700 bg-neutral-900 text-blue-400 hover:border-blue-500 hover:bg-blue-950/40"
            }`}
          >
            {chatOpen ? "Hide Chat" : "Ask AI"}
          </button>

          <button
            onClick={() => setIsExportOpen(true)}
            className="p-1 rounded text-neutral-400 hover:text-cyan-400 hover:bg-neutral-900 transition-all text-xs"
            title="Export Intelligence Package"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
          </button>
          <button
            onClick={onClose}
            className="text-neutral-500 hover:text-white transition-colors text-base font-mono p-1"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Floating AI Evidence Assistant Chat Panel */}
      {chatOpen && (
        <div className="rounded-md border border-blue-500/40 bg-neutral-950/95 shadow-[0_18px_45px_rgba(0,0,0,0.75)] backdrop-blur-xl mb-4">
          <div className="flex items-center justify-between border-b border-neutral-800 px-3 py-2">
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-400 shadow-[0_0_8px_rgba(96,165,250,0.8)]" />
              <h3 className="text-[10px] font-bold uppercase tracking-[0.18em] text-blue-300">Evidence Assistant</h3>
            </div>
            <span className="font-mono text-[9px] uppercase tracking-wider text-neutral-600">Scoped session</span>
          </div>
          <div className="p-2">
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

      {/* Metadata KPI Grid */}
      <div className="grid grid-cols-3 gap-px bg-neutral-800 border border-neutral-800 rounded overflow-hidden font-mono">
        <Field label="SEMANTIC MATCH" value={`${(result.similarity_score * 100).toFixed(1)}%`} highlight />
        <Field label="DATA QUALITY" value={result.quality_score == null ? "N/A" : `${(result.quality_score * 100).toFixed(1)}%`} />
        <Field label="CLOUD COVER" value={result.cloud_fraction == null ? "N/A" : `${(result.cloud_fraction * 100).toFixed(1)}%`} />
        <Field label="ACQUISITION" value={result.acquisition_date?.slice(0, 10) ?? "N/A"} />
        <Field label="RESOLUTION" value="10.0 M" />
        <Field label="COMPOSITE RANK" value={result.final_score.toFixed(3)} highlight />
      </div>

      {/* Basic Provenance Card (MVP Specification) */}
      <div className="p-3 bg-neutral-900/60 rounded border border-neutral-800/90 font-mono text-[11px] space-y-1">
        <div className="flex items-center justify-between border-b border-neutral-800/80 pb-1 mb-1">
          <span className="text-[9px] uppercase tracking-widest text-neutral-500 font-bold">SENSOR PROVENANCE</span>
          <span className="text-[9px] text-emerald-400 font-bold">AIR-GAPPED</span>
        </div>
        <div className="flex justify-between">
          <span className="text-neutral-500">SOURCE:</span>
          <span className="text-white font-bold">{result.sensor ?? "Sentinel-2 MSI"}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-neutral-500">ACQUIRED:</span>
          <span className="text-neutral-300">{result.acquisition_date?.slice(0, 10) ?? "2025-04-12"}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-neutral-500">TILE ID:</span>
          <span className="text-cyan-400 font-mono text-[10px] truncate max-w-[200px]">{result.tile_id}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-neutral-500">PROCESSING:</span>
          <span className="text-neutral-300">TerreX v1 (Windowed 256x256)</span>
        </div>
        <div className="flex justify-between">
          <span className="text-neutral-500">MODEL:</span>
          <span className="text-emerald-400">RemoteCLIP ViT-B/32</span>
        </div>
      </div>

      {/* Bitemporal Analysis Launcher / Date Controls */}
      <div className="space-y-3 p-3.5 bg-neutral-900/40 rounded border border-neutral-800/80">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-white font-sans tracking-tight uppercase">
            Bitemporal Change <span className="text-neutral-400 font-light">Analysis</span>
          </span>
          <span className="text-[9px] font-mono text-cyan-400">SPECTRAL + AI</span>
        </div>

        <div className="flex items-center gap-2 font-mono text-[11px]">
          <div className="flex-1">
            <span className="text-[9px] text-neutral-500 block mb-0.5">T0 (BEFORE)</span>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-full bg-black border border-neutral-700 focus:border-cyan-500 rounded px-2 py-1 text-neutral-200 text-[10px] outline-none"
            />
          </div>
          <span className="text-neutral-600 mt-3">&rarr;</span>
          <div className="flex-1">
            <span className="text-[9px] text-neutral-500 block mb-0.5">T1 (AFTER)</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-full bg-black border border-neutral-700 focus:border-cyan-500 rounded px-2 py-1 text-neutral-200 text-[10px] outline-none"
            />
          </div>
        </div>

        <button
          onClick={runChangeDetection}
          disabled={loading}
          className="w-full py-2.5 rounded bg-white hover:bg-neutral-200 text-black font-sans font-semibold text-xs uppercase tracking-widest transition-all disabled:opacity-50 shadow-md"
        >
          {loading ? "ANALYZING BITEMPORAL SPECTRAL DELTAS..." : "EXECUTE BITEMPORAL ANALYSIS"}
        </button>

        {/* Discover Similar Sites */}
        {onFindSimilar && (
          <button
            onClick={() => onFindSimilar(result)}
            className="w-full py-2 rounded border border-cyan-700/60 bg-cyan-950/20 hover:bg-cyan-950/50 text-cyan-400 font-sans font-semibold text-xs uppercase tracking-widest transition-all"
          >
            🔍 Discover Similar Sites
          </button>
        )}
      </div>

      {change?.status !== "ok" && (
        <div className="border border-amber-800/60 bg-amber-950/20 p-3 text-[11px] text-amber-300 font-mono">
          {change?.status === "error" ? "ANALYSIS ERROR: " : "ANALYSIS NOT RUN: "}
          {change?.message ?? "Run the analysis to load real before/after observations for this target."}
        </div>
      )}

      {/* Interactive Before / After Split Slider */}
      {changeReady && <BeforeAfterSlider
        beforeImg={change?.before?.thumbnail_url ?? change?.before?.thumbnail_path ?? result.thumbnail_path}
        afterImg={change?.after?.thumbnail_url ?? change?.after?.thumbnail_path ?? result.thumbnail_path}
        maskImg={change?.change_mask_url}
        beforeDate={change?.before?.acquisition_date?.slice(0, 10) ?? dateFrom}
        afterDate={change?.after?.acquisition_date?.slice(0, 10) ?? dateTo}
        dominantChange={change?.dominant_change_type}
        confidence={change?.confidence}
      />}

      {/* Multi-Spectral Radiometric Layer Toggles */}
      <div className="space-y-1.5">
        <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 font-bold block">
          SPECTRAL &amp; MASK LAYERS
        </span>
        <div className="grid grid-cols-3 gap-1.5 font-mono text-[10px]">
          <LayerToggle
            label="True Color (RGB)"
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
            label="ΔNDBI (Build)"
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
      </div>

      {/* Detected Change Summary Metrics */}
      <div className="bg-black/60 p-3 rounded border border-neutral-800 space-y-2 font-mono text-[11px]">
        <div className="flex items-center justify-between">
          <span className="text-neutral-400">CLASSIFIED TYPE:</span>
          <div className="flex items-center gap-1.5">
            {change?.dominant_dynamics && (
              <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase border ${
                change.dominant_dynamics === "appearance" ? "bg-emerald-950/60 border-emerald-700/60 text-emerald-300" :
                change.dominant_dynamics === "disappearance" ? "bg-red-950/60 border-red-700/60 text-red-300" :
                change.dominant_dynamics === "expansion" ? "bg-amber-950/60 border-amber-700/60 text-amber-300" :
                "bg-cyan-950/60 border-cyan-700/60 text-cyan-300"
              }`}>
                {change.dominant_dynamics}
              </span>
            )}
            <span className="text-emerald-400 font-bold uppercase bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-800/50">
              {change?.dominant_change_type?.replace("_", " ") ?? "N/A"}
            </span>
          </div>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-neutral-400">AFFECTED GROUND AREA:</span>
          <span className="text-white font-bold">
            {change?.change_area_hectares != null
              ? `${change.change_area_hectares} ha (${(change.change_area_m2 ?? 0).toLocaleString()} m²)`
              : "N/A"}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-neutral-400">EARLIEST OBSERVATION:</span>
          <span className="text-cyan-400 font-bold">
            {change?.earliest_supported_observation?.slice(0, 10) ?? "N/A"}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-neutral-400">CO-REGISTRATION:</span>
          <span className="text-emerald-400">
            {change?.registration ? (change.registration.is_aligned ? "Aligned" : "Residual Shift") : "N/A"}
          </span>
        </div>
      </div>

      {/* Detected Regions Breakdown */}
      {change?.change_regions && change.change_regions.length > 0 && (
        <div className="space-y-2">
          <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 font-bold block">
            DETECTED CHANGE REGIONS ({change.change_regions.length})
          </span>
          <div className="space-y-1.5">
            {change.change_regions.map((region) => {
              const isSelected = region.region_id === selectedRegionId;
              const dynColor = region.dynamics === "appearance" ? "text-emerald-300 border-emerald-700/50 bg-emerald-950/50" :
                region.dynamics === "disappearance" ? "text-red-300 border-red-700/50 bg-red-950/50" :
                region.dynamics === "expansion" ? "text-amber-300 border-amber-700/50 bg-amber-950/50" :
                "text-cyan-300 border-cyan-700/50 bg-cyan-950/50";
              return (
                <div
                  key={region.region_id}
                  onClick={() => setSelectedRegionId(region.region_id)}
                  className={`p-2.5 rounded border cursor-pointer transition-all ${
                    isSelected
                      ? "bg-neutral-900 border-cyan-500 text-white"
                      : "bg-black/50 border-neutral-800 text-neutral-400 hover:border-neutral-700"
                  }`}
                >
                  <div className="flex items-center justify-between font-mono text-[10px]">
                    <span className="font-bold text-neutral-200 uppercase">
                      REGION #{region.region_id.toString().padStart(2, "0")} &mdash; {region.change_type}
                    </span>
                    <div className="flex items-center gap-1.5">
                      {region.dynamics && (
                        <span className={`text-[8px] px-1.5 py-0.5 rounded border font-bold uppercase ${dynColor}`}>
                          {region.dynamics}
                        </span>
                      )}
                      <span className="text-emerald-400 font-bold">{region.area_m2} m²</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 mt-1 text-[9px] font-mono text-neutral-500">
                    <span>Conf: <strong className="text-cyan-400">{Math.round(region.confidence * 100)}%</strong></span>
                    <span>ΔNDBI: <strong className="text-amber-400">+{region.mean_d_ndbi.toFixed(2)}</strong></span>
                    <span>ΔNDVI: <strong className="text-emerald-400">{region.mean_d_ndvi.toFixed(2)}</strong></span>
                  </div>
                  <p className="text-[10px] text-neutral-400 font-sans mt-1 leading-snug">
                    {region.rationale}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Multi-temporal Change Timeline */}
      <ChangeTimeline
        earliestDate={change?.earliest_supported_observation?.slice(0, 10) ?? undefined}
        registrationConfidence={change?.registration?.correlation_after != null ? Math.round(change.registration.correlation_after * 100) : 0}
      />

      {/* Explainable AI Evidence Panel */}
      <EvidencePanel
        reasons={change?.reasons}
        suppressionReasons={change?.suppression_reasons}
        registrationCorr={change?.registration?.correlation_after}
        dNdvi={selectedRegion?.mean_d_ndvi}
        dNdbi={selectedRegion?.mean_d_ndbi}
      />

      {/* Analyst Decision Action Bar */}
      <div className="space-y-3 p-3.5 bg-neutral-900/50 rounded border border-neutral-800">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-white font-sans tracking-tight uppercase">
            Analyst Verification <span className="text-neutral-400 font-light">&middot; Decision</span>
          </span>
          {feedbackSent && (
            <span className="text-[10px] font-mono text-emerald-400 font-bold uppercase">
              ✓ LOGGED ({feedbackSent})
            </span>
          )}
        </div>

        <input
          type="text"
          value={analystNote}
          onChange={(e) => setAnalystNote(e.target.value)}
          placeholder="Analyst verification notes (optional)..."
          className="w-full bg-black border border-neutral-800 focus:border-neutral-600 rounded px-2.5 py-2 text-xs text-neutral-300 font-sans outline-none font-light"
        />

        <div className="flex gap-2 pt-1">
          <button
            onClick={() => sendFeedback("confirm")}
            className="flex-1 py-2.5 rounded bg-emerald-600 hover:bg-emerald-500 text-black font-sans font-semibold text-xs tracking-widest uppercase transition-all shadow-md"
          >
            ✓ CONFIRM
          </button>
          <button
            onClick={() => sendFeedback("reject")}
            className="flex-1 py-2.5 rounded bg-black border border-neutral-700 hover:border-red-500 text-neutral-300 hover:text-red-400 font-sans font-semibold text-xs tracking-widest uppercase transition-all"
          >
            ✕ REJECT
          </button>
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
      />
    </div>
  );
}

function Field({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="bg-neutral-900/80 p-2 flex flex-col justify-center">
      <p className="text-[9px] uppercase tracking-widest text-neutral-500">{label}</p>
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
      className={`py-1.5 px-2 rounded border text-left text-[9px] transition-all flex items-center justify-between ${
        active
          ? borderClasses[highlight]
          : "border-neutral-800 text-neutral-500 bg-black/40 hover:text-neutral-300 hover:border-neutral-700"
      }`}
    >
      <span>{label}</span>
      <span className="font-mono font-bold">{active ? "✓" : "○"}</span>
    </button>
  );
}
