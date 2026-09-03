"use client";

import React, { useState } from "react";
import {
  SearchResult, ChangeDetectionResponse,
  exportGeoJSON, exportCSV, exportAnalystReport, exportEvidencePackage,
} from "@/lib/api";

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  result: SearchResult | null;
  change?: ChangeDetectionResponse | null;
  allResults?: SearchResult[];
}

export default function ExportModal({
  isOpen,
  onClose,
  result,
  change,
  allResults = [],
}: ExportModalProps) {
  const [selectedFormats, setSelectedFormats] = useState({
    geojson: true,
    csv: true,
    mask: false,
    report: true,
    evidencePkg: true,
  });
  const [exportScope, setExportScope] = useState<"current" | "all">("current");
  const [downloading, setDownloading] = useState(false);

  if (!isOpen) return null;

  const target = result || (allResults.length > 0 ? allResults[0] : null);

  const handleExport = () => {
    if (!target) return;
    setDownloading(true);

    setTimeout(() => {
      const itemsToExport = exportScope === "all" && allResults.length > 0 ? allResults : [target];

      if (selectedFormats.geojson) {
        exportGeoJSON(itemsToExport, `terrex_export_${target.tile_id}.geojson`);
      }
      if (selectedFormats.csv) {
        exportCSV(itemsToExport, `terrex_report_${target.tile_id}.csv`);
      }
      if (selectedFormats.report) {
        exportAnalystReport(target, change, `terrex_analyst_report_${target.tile_id}.md`);
      }
      if (selectedFormats.evidencePkg) {
        exportEvidencePackage(target, change, `terrex_evidence_package_${target.tile_id}.json`);
      }

      setDownloading(false);
      onClose();
    }, 400);
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/80 backdrop-blur-sm animate-in fade-in">
      <div className="w-[460px] max-w-[90vw] bg-neutral-950 border border-neutral-800 rounded-xl p-6 shadow-2xl space-y-5 font-sans text-xs">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-neutral-800 pb-3 font-mono">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            <h2 className="text-sm font-bold text-white uppercase tracking-wider">
              EXPORT INTELLIGENCE PACKAGE
            </h2>
          </div>
          <button onClick={onClose} className="text-neutral-500 hover:text-white transition-colors text-base">
            ✕
          </button>
        </div>

        {/* Scope Selector */}
        <div className="space-y-1.5 font-mono">
          <label className="text-[10px] uppercase tracking-wider text-neutral-400 font-semibold">
            EXPORT SCOPE
          </label>
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => setExportScope("current")}
              className={`py-2 px-3 rounded text-[11px] uppercase transition-all border ${
                exportScope === "current"
                  ? "bg-neutral-900 border-cyan-500/50 text-cyan-400 font-bold"
                  : "bg-black/50 border-neutral-800 text-neutral-400 hover:text-neutral-200"
              }`}
            >
              Current Site ({target?.tile_id ? target.tile_id.slice(0, 8) : "None"})
            </button>
            <button
              onClick={() => setExportScope("all")}
              disabled={allResults.length === 0}
              className={`py-2 px-3 rounded text-[11px] uppercase transition-all border ${
                exportScope === "all"
                  ? "bg-neutral-900 border-cyan-500/50 text-cyan-400 font-bold"
                  : "bg-black/50 border-neutral-800 text-neutral-400 hover:text-neutral-200 disabled:opacity-40"
              }`}
            >
              All Results ({allResults.length})
            </button>
          </div>
        </div>

        {/* Format Options */}
        <div className="space-y-2.5">
          <label className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 font-semibold">
            SELECT PACKAGING FORMATS
          </label>
          <div className="space-y-2 bg-neutral-900/50 p-3 rounded border border-neutral-800/80">
            <FormatCheckbox
              label="GeoJSON Features"
              desc="Full coordinate footprints, EPSG:4326 geometries, and scores"
              checked={selectedFormats.geojson}
              onChange={(c) => setSelectedFormats((prev) => ({ ...prev, geojson: c }))}
            />
            <FormatCheckbox
              label="CSV Analyst Summary"
              desc="Tabular spreadsheet with metrics, sensor info, and classification"
              checked={selectedFormats.csv}
              onChange={(c) => setSelectedFormats((prev) => ({ ...prev, csv: c }))}
            />
            <FormatCheckbox
              label="Analyst Verification Report (.md)"
              desc="Markdown dossier with explainable AI evidence and suppression logs"
              checked={selectedFormats.report}
              onChange={(c) => setSelectedFormats((prev) => ({ ...prev, report: c }))}
            />
            <FormatCheckbox
              label="Full Evidence Package (.json)"
              desc="Cryptographically auditable JSON envelope with complete DAG provenance"
              checked={selectedFormats.evidencePkg}
              onChange={(c) => setSelectedFormats((prev) => ({ ...prev, evidencePkg: c }))}
            />
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-3 pt-2">
          <button
            onClick={onClose}
            className="flex-1 py-2 rounded bg-neutral-900 hover:bg-neutral-800 text-neutral-300 border border-neutral-700 font-mono text-[11px] uppercase tracking-wider font-semibold transition-all"
          >
            CANCEL
          </button>
          <button
            onClick={handleExport}
            disabled={downloading || !target}
            className="flex-1 py-2 rounded bg-emerald-600 hover:bg-emerald-500 text-black border border-emerald-400 font-mono text-[11px] uppercase tracking-wider font-bold transition-all disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {downloading ? "PACKAGING..." : "GENERATE EXPORT"}
          </button>
        </div>
      </div>
    </div>
  );
}

function FormatCheckbox({
  label,
  desc,
  checked,
  onChange,
}: {
  label: string;
  desc: string;
  checked: boolean;
  onChange: (c: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-2.5 cursor-pointer group">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 w-4 h-4 rounded bg-black border-neutral-700 text-emerald-500 focus:ring-0 focus:ring-offset-0 cursor-pointer accent-emerald-500"
      />
      <div>
        <p className="text-neutral-200 font-medium group-hover:text-white transition-colors">
          {label}
        </p>
        <p className="text-[10px] text-neutral-500 leading-snug">{desc}</p>
      </div>
    </label>
  );
}
