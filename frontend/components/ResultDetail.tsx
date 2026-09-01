"use client";

import { useState } from "react";
import {
  SearchResult, ChangeDetectionResponse, detectChange, submitFeedback, thumbnailUrl,
} from "@/lib/api";

interface Props {
  result: SearchResult | null;
  onClose: () => void;
}

export default function ResultDetail({ result, onClose }: Props) {
  const [dateFrom, setDateFrom] = useState("2023-01-01");
  const [dateTo, setDateTo] = useState("2024-01-01");
  const [change, setChange] = useState<ChangeDetectionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState<string | null>(null);

  if (!result) {
    return (
      <div className="h-full flex items-center justify-center text-neutral-500 text-xs p-6 text-center">
        Select a tile from the map or list to inspect spectral metadata, run 4-class multi-temporal change detection, and log analyst decisions.
      </div>
    );
  }

  const runChangeDetection = async () => {
    setLoading(true);
    setChange(null);
    try {
      const res = await detectChange(result.lon, result.lat, dateFrom, dateTo);
      setChange(res);
    } catch (e) {
      setChange({ status: "error", message: String(e) });
    } finally {
      setLoading(false);
    }
  };

  const sendFeedback = async (verdict: "confirm" | "reject") => {
    const targetType = change?.change_id ? "change_result" : "tile";
    const targetId = change?.change_id ?? result.tile_id;
    await submitFeedback(targetType, targetId, verdict);
    setFeedbackSent(verdict);
  };

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4 text-xs font-sans">
      {/* Header */}
      <div className="flex items-start justify-between border-b border-neutral-800 pb-2">
        <div>
          <h2 className="text-sm font-semibold text-neutral-100 flex items-center gap-2">
            Target Inspection
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-300 font-mono">
              {result.sensor ?? "EO"}
            </span>
          </h2>
          <p className="text-[11px] text-neutral-500 font-mono mt-0.5">
            {result.lat.toFixed(5)}°N, {result.lon.toFixed(5)}°E
          </p>
        </div>
        <button onClick={onClose} className="text-neutral-500 hover:text-neutral-200 text-base">✕</button>
      </div>

      {/* Metadata Grid */}
      <div className="grid grid-cols-2 gap-2 bg-neutral-950 p-2.5 rounded border border-neutral-800">
        <Field label="Sensor" value={result.sensor ?? "Unknown"} />
        <Field label="Acquisition" value={result.acquisition_date?.slice(0, 10) ?? "Unknown"} />
        <Field label="Semantic Match" value={`${(result.similarity_score * 100).toFixed(1)}%`} />
        <Field label="Quality Score" value={(result.quality_score ?? 0).toFixed(3)} />
        <Field label="Cloud Cover" value={`${((result.cloud_fraction ?? 0) * 100).toFixed(1)}%`} />
        <Field label="Composite Rank" value={(result.final_score).toFixed(3)} highlight />
      </div>

      {result.embedding_is_placeholder && (
        <div className="text-[11px] text-amber-400 bg-amber-950/30 border border-amber-800/40 rounded p-2">
          Model: <span className="font-mono">{result.embedding_model}</span> (deterministic visual hash). Full honesty contract preserved.
        </div>
      )}

      {/* Thumbnail */}
      {result.thumbnail_path && (
        <div className="space-y-1">
          <p className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold">Observation Patch</p>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={thumbnailUrl(result.thumbnail_path)}
            alt="tile"
            className="w-full h-44 object-cover rounded border border-neutral-800"
          />
        </div>
      )}

      {/* Change Detection Section */}
      <div className="border-t border-neutral-800 pt-3 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs uppercase tracking-wider text-neutral-400 font-semibold">Multi-Temporal Change</h3>
          <span className="text-[10px] text-neutral-500">2-Layer RS Engine</span>
        </div>

        {/* Date Filters */}
        <div className="space-y-1.5 bg-neutral-950 p-2 rounded border border-neutral-800">
          <div className="flex items-center gap-1.5 text-[11px]">
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="bg-black border border-neutral-700 rounded px-1.5 py-1 text-neutral-200 flex-1 font-mono text-[11px]"
            />
            <span className="text-neutral-500">→</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="bg-black border border-neutral-700 rounded px-1.5 py-1 text-neutral-200 flex-1 font-mono text-[11px]"
            />
          </div>
          <button
            onClick={runChangeDetection}
            disabled={loading}
            className="w-full py-1.5 rounded bg-emerald-500 hover:bg-emerald-400 text-black font-semibold text-xs transition disabled:opacity-50"
          >
            {loading ? "Analyzing Temporal Observations…" : "Analyze Multi-Temporal Change"}
          </button>
        </div>

        {/* Result status */}
        {change && change.status === "insufficient_data" && (
          <div className="text-[11px] text-neutral-400 bg-neutral-900 border border-neutral-800 rounded p-2.5">
            {change.message}
          </div>
        )}

        {change && change.status === "error" && (
          <div className="text-[11px] text-rose-400 bg-rose-950/20 border border-rose-900/50 rounded p-2.5">
            {change.message}
          </div>
        )}

        {change && change.status === "ok" && (
          <div className="space-y-3 pt-1">
            {/* Classified Change Type Badge */}
            <div className="flex items-center justify-between bg-neutral-900/80 p-2 rounded border border-neutral-800">
              <span className="text-[11px] text-neutral-400 font-medium">Classified Change:</span>
              <ChangeTypeBadge type={change.dominant_change_type ?? "unclassified"} />
            </div>

            {/* Before / After / Mask Display */}
            <div className="grid grid-cols-2 gap-2">
              <div>
                <p className="text-[10px] text-neutral-500 mb-1">
                  T0 ({change.before?.acquisition_date?.slice(0, 10)})
                </p>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={thumbnailUrl(change.before?.thumbnail_path)}
                  className="w-full h-28 object-cover rounded border border-neutral-800"
                  alt="before"
                />
              </div>
              <div>
                <p className="text-[10px] text-neutral-500 mb-1">
                  T1 ({change.after?.acquisition_date?.slice(0, 10)})
                </p>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={thumbnailUrl(change.after?.thumbnail_path)}
                  className="w-full h-28 object-cover rounded border border-neutral-800"
                  alt="after"
                />
              </div>
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-3 gap-1.5 text-center">
              <Metric label="Change Magnitude" value={change.change_score} />
              <Metric label="Quality Gate" value={change.quality_score} />
              <Metric label="Confidence" value={change.confidence} highlight />
            </div>

            {/* Area & Earliest Supported Observation */}
            <div className="bg-neutral-950 p-2 rounded border border-neutral-800 space-y-1 text-[11px]">
              <div className="flex justify-between">
                <span className="text-neutral-500">Affected Ground Area:</span>
                <span className="font-mono text-neutral-200">{change.change_area_m2?.toLocaleString()} m²</span>
              </div>
              {change.earliest_supported_observation && (
                <div className="flex justify-between">
                  <span className="text-neutral-500">Earliest Observation:</span>
                  <span className="font-mono text-emerald-400 font-medium">
                    {change.earliest_supported_observation.slice(0, 10)}
                  </span>
                </div>
              )}
              {change.registration && (
                <div className="flex justify-between">
                  <span className="text-neutral-500">Co-Registration:</span>
                  <span className={`font-mono ${change.registration.is_aligned ? "text-emerald-400" : "text-amber-400"}`}>
                    {change.registration.is_aligned ? "Aligned (ORB+Warp)" : "Residual Shift"} ({change.registration.correlation_after.toFixed(2)})
                  </span>
                </div>
              )}
            </div>

            {/* Detected Change Regions Breakdown */}
            {change.change_regions && change.change_regions.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold">
                  Detected Change Regions ({change.change_regions.length})
                </p>
                <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
                  {change.change_regions.map((r) => (
                    <div key={r.region_id} className="p-1.5 rounded bg-neutral-950 border border-neutral-800 text-[11px] space-y-0.5">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-neutral-200 capitalize">{r.change_type.replace("_", " ")}</span>
                        <span className="font-mono text-neutral-400">{r.area_m2} m²</span>
                      </div>
                      <p className="text-[10px] text-neutral-400 leading-tight">{r.rationale}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Suppression & Diagnostics */}
            <div>
              <p className="text-[10px] uppercase tracking-wider text-neutral-500 mb-1 font-semibold">
                Suppression Reasons & Provenance
              </p>
              <ul className="text-[11px] text-neutral-400 list-disc list-inside space-y-0.5 bg-neutral-950 p-2 rounded border border-neutral-800">
                {(change.suppression_reasons || change.reasons)?.map((r, i) => (
                  <li key={i} className="leading-snug">{r}</li>
                ))}
              </ul>
            </div>

            {/* Analyst Review Queue / Confirm & Reject Actions */}
            <div className="space-y-1 pt-1">
              <p className="text-[10px] uppercase tracking-wider text-neutral-500 font-semibold">Analyst Decision</p>
              <div className="flex gap-2">
                <button
                  onClick={() => sendFeedback("confirm")}
                  className="flex-1 py-1.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-700/60 hover:bg-emerald-900/60 text-xs font-semibold transition"
                >
                  ✓ Confirm Finding
                </button>
                <button
                  onClick={() => sendFeedback("reject")}
                  className="flex-1 py-1.5 rounded bg-rose-950/60 text-rose-300 border border-rose-700/60 hover:bg-rose-900/60 text-xs font-semibold transition"
                >
                  ✕ Suppress False Alarm
                </button>
              </div>
              {feedbackSent && (
                <p className="text-[11px] text-emerald-400 text-center font-medium pt-0.5">
                  Audit trail recorded: verdict={feedbackSent.toUpperCase()}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <p className="text-[10px] text-neutral-500">{label}</p>
      <p className={`font-mono text-[11px] truncate ${highlight ? "text-emerald-400 font-semibold" : "text-neutral-200"}`}>
        {value}
      </p>
    </div>
  );
}

function Metric({ label, value, highlight }: { label: string; value?: number; highlight?: boolean }) {
  return (
    <div className={`rounded p-1.5 border ${highlight ? "bg-emerald-950/20 border-emerald-800/50" : "bg-neutral-900 border-neutral-800"}`}>
      <p className="text-[10px] text-neutral-500">{label}</p>
      <p className={`text-xs font-mono font-semibold ${highlight ? "text-emerald-400" : "text-neutral-200"}`}>
        {value !== undefined ? value.toFixed(2) : "—"}
      </p>
    </div>
  );
}

function ChangeTypeBadge({ type }: { type: string }) {
  switch (type.toLowerCase()) {
    case "construction":
      return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-950 text-amber-300 border border-amber-700">CONSTRUCTION</span>;
    case "road_development":
      return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-950 text-blue-300 border border-blue-700">ROAD DEVELOPMENT</span>;
    case "water_extent":
      return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-cyan-950 text-cyan-300 border border-cyan-700">WATER EXTENT</span>;
    case "clearance":
      return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-orange-950 text-orange-300 border border-orange-700">CLEARANCE</span>;
    default:
      return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-neutral-800 text-neutral-300 border border-neutral-700">{type.toUpperCase()}</span>;
  }
}
