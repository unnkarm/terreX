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
      <div className="h-full flex items-center justify-center text-gray-600 text-sm p-6 text-center">
        Select a result on the map or in the list to inspect location details,
        run change detection, and record analyst feedback.
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
    <div className="h-full overflow-y-auto p-4 space-y-5">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-sm font-semibold text-gray-100">Location detail</h2>
          <p className="text-xs text-gray-500">{result.lat.toFixed(5)}, {result.lon.toFixed(5)}</p>
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-sm">✕</button>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs">
        <Field label="Sensor" value={result.sensor ?? "unknown"} />
        <Field label="Acquisition date" value={result.acquisition_date?.slice(0, 10) ?? "unknown"} />
        <Field label="Similarity" value={result.similarity_score.toFixed(3)} />
        <Field label="Quality score" value={(result.quality_score ?? 0).toFixed(3)} />
        <Field label="Cloud fraction" value={(result.cloud_fraction ?? 0).toFixed(3)} />
        <Field label="Final rank score" value={result.final_score.toFixed(3)} />
      </div>

      {result.embedding_is_placeholder && (
        <div className="text-[11px] text-warn bg-warn/10 border border-warn/30 rounded p-2">
          This result used a placeholder embedding model ({result.embedding_model}) because
          RemoteCLIP weights are not staged — similarity reflects visual/lexical hashing,
          not learned semantics. See README to stage real weights.
        </div>
      )}

      {result.thumbnail_path && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={thumbnailUrl(result.thumbnail_path)} alt="tile" className="w-full rounded border border-gray-800" />
      )}

      <div className="border-t border-gray-800 pt-4 space-y-3">
        <h3 className="text-xs uppercase tracking-wide text-gray-500 font-medium">Change detection</h3>
        <div className="flex items-center gap-2 text-xs">
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
            className="bg-panel2 border border-gray-700 rounded px-2 py-1" />
          <span>→</span>
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
            className="bg-panel2 border border-gray-700 rounded px-2 py-1" />
          <button onClick={runChangeDetection} disabled={loading}
            className="ml-auto px-3 py-1.5 rounded bg-accent/90 hover:bg-accent text-black font-medium disabled:opacity-50">
            {loading ? "Running…" : "Detect changes"}
          </button>
        </div>

        {change && change.status === "insufficient_data" && (
          <div className="text-xs text-gray-500 bg-panel2 rounded p-2">{change.message}</div>
        )}
        {change && change.status === "error" && (
          <div className="text-xs text-danger bg-danger/10 rounded p-2">{change.message}</div>
        )}
        {change && change.status === "ok" && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <p className="text-[10px] text-gray-500 mb-1">Before ({change.before?.acquisition_date?.slice(0,10)})</p>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={thumbnailUrl(change.before?.thumbnail_path)} className="w-full rounded border border-gray-800" alt="before" />
              </div>
              <div>
                <p className="text-[10px] text-gray-500 mb-1">After ({change.after?.acquisition_date?.slice(0,10)})</p>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={thumbnailUrl(change.after?.thumbnail_path)} className="w-full rounded border border-gray-800" alt="after" />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2 text-center">
              <Metric label="Change score" value={change.change_score} />
              <Metric label="Quality" value={change.quality_score} />
              <Metric label="Confidence" value={change.confidence} highlight />
            </div>

            <div className="text-xs text-gray-400">
              Area changed: <span className="text-gray-200">{change.change_area_m2?.toLocaleString()} m²</span>
            </div>

            {change.is_placeholder_model && (
              <div className="text-[11px] text-warn bg-warn/10 border border-warn/30 rounded p-2">
                Prithvi-EO weights are not staged — this used the placeholder
                statistical feature-difference method ({change.method}). Treat as
                a wiring demo, not a validated AI change signal.
              </div>
            )}

            <div>
              <p className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">Reasons / provenance</p>
              <ul className="text-xs text-gray-400 list-disc list-inside space-y-0.5">
                {change.reasons?.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </div>

            <div className="flex gap-2 pt-2">
              <button onClick={() => sendFeedback("confirm")}
                className="flex-1 py-2 rounded bg-ok/20 text-ok border border-ok/40 hover:bg-ok/30 text-sm font-medium">
                ✓ Confirm
              </button>
              <button onClick={() => sendFeedback("reject")}
                className="flex-1 py-2 rounded bg-danger/20 text-danger border border-danger/40 hover:bg-danger/30 text-sm font-medium">
                ✕ Reject
              </button>
            </div>
            {feedbackSent && (
              <p className="text-xs text-gray-500 text-center">Feedback recorded: {feedbackSent}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-gray-500">{label}</p>
      <p className="text-gray-200 truncate">{value}</p>
    </div>
  );
}

function Metric({ label, value, highlight }: { label: string; value?: number; highlight?: boolean }) {
  return (
    <div className={`rounded p-2 ${highlight ? "bg-accent/10 border border-accent/40" : "bg-panel2"}`}>
      <p className="text-[10px] text-gray-500">{label}</p>
      <p className={`text-sm font-semibold ${highlight ? "text-accent" : "text-gray-200"}`}>
        {value !== undefined ? value.toFixed(2) : "—"}
      </p>
    </div>
  );
}
