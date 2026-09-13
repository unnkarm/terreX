"use client";

import React, { useState } from "react";
import {
  SearchResult, ChangeDetectionResponse,
  exportGeoJSON, exportCSV, exportAnalystReport, exportEvidencePackage, exportForensicPDF,
} from "@/lib/api";

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  result: SearchResult | null;
  change?: ChangeDetectionResponse | null;
  allResults?: SearchResult[];
  analystNote?: string;
  verdict?: string | null;
  dateFrom?: string;
  dateTo?: string;
}

export default function ExportModal({
  isOpen,
  onClose,
  result,
  change,
  allResults = [],
  analystNote,
  verdict,
  dateFrom,
  dateTo,
}: ExportModalProps) {
  const [selectedFormats, setSelectedFormats] = useState({
    pdf: true,
    evidencePkg: true,
    geojson: true,
    csv: true,
    report: true,
  });
  const [exportScope, setExportScope] = useState<"current" | "all">("current");
  const [downloading, setDownloading] = useState(false);
  const [exportStatus, setExportStatus] = useState<string | null>(null);

  if (!isOpen) return null;

  const target = result || (allResults.length > 0 ? allResults[0] : null);

  const handleQuickPdf = async () => {
    if (!target) return;
    setDownloading(true);
    setExportStatus("Generating Forensic Intelligence PDF Dossier...");
    try {
      await exportForensicPDF(target, change, { analystNote, verdict, dateFrom, dateTo });
      setExportStatus("Dossier generated successfully!");
      setTimeout(() => {
        setDownloading(false);
        setExportStatus(null);
        onClose();
      }, 600);
    } catch (e) {
      console.error("PDF export failed:", e);
      setDownloading(false);
      setExportStatus(null);
    }
  };

  const handleExport = async () => {
    if (!target) return;
    setDownloading(true);
    setExportStatus("Packaging intelligence artifacts & computing SHA-256 signatures...");

    try {
      const itemsToExport = exportScope === "all" && allResults.length > 0 ? allResults : [target];

      // 1. Forensic PDF Dossier
      if (selectedFormats.pdf) {
        await exportForensicPDF(target, change, { analystNote, verdict, dateFrom, dateTo });
      }

      // 2. Cryptographically Signed JSON Evidence Package
      if (selectedFormats.evidencePkg) {
        await exportEvidencePackage(
          target,
          change,
          `terrex_evidence_package_${target.tile_id}.json`,
          analystNote,
          verdict || undefined
        );
      }

      // 3. GeoJSON Footprints
      if (selectedFormats.geojson) {
        exportGeoJSON(itemsToExport, `terrex_export_${target.tile_id}.geojson`);
      }

      // 4. Tabular CSV
      if (selectedFormats.csv) {
        exportCSV(itemsToExport, `terrex_report_${target.tile_id}.csv`);
      }

      // 5. Markdown Report
      if (selectedFormats.report) {
        await exportAnalystReport(
          target,
          change,
          `terrex_analyst_report_${target.tile_id}.md`,
          analystNote,
          verdict || undefined
        );
      }

      setExportStatus("Export bundle completed!");
      setTimeout(() => {
        setDownloading(false);
        setExportStatus(null);
        onClose();
      }, 600);
    } catch (e) {
      console.error("Export failed:", e);
      setDownloading(false);
      setExportStatus(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/85 backdrop-blur-md animate-in fade-in p-4">
      <div className="w-[500px] max-w-[95vw] bg-neutral-950 border border-neutral-800 rounded-xl p-6 shadow-[0_0_60px_rgba(0,0,0,0.9)] space-y-4 font-sans text-xs">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-neutral-800 pb-3 font-mono">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            <div>
              <h2 className="text-sm font-bold text-white uppercase tracking-wider">
                EXPORT INTELLIGENCE DOSSIER
              </h2>
              <p className="text-[10px] text-neutral-500 font-sans">
                Air-gapped verification bundle with cryptographic SHA-256 seal
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-neutral-500 hover:text-white transition-colors text-base p-1"
          >
            ✕
          </button>
        </div>

        {/* Scope Selector */}
        <div className="space-y-1.5 font-mono">
          <div className="flex justify-between items-center">
            <label className="text-[10px] uppercase tracking-wider text-neutral-400 font-semibold">
              EXPORT SCOPE
            </label>
            <span className="text-[9px] text-cyan-400">
              TARGET: {target?.tile_id ? target.tile_id.slice(0, 16) : "None Selected"}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={() => setExportScope("current")}
              className={`py-2 px-3 rounded text-[11px] uppercase transition-all border ${
                exportScope === "current"
                  ? "bg-cyan-950/40 border-cyan-500/80 text-cyan-300 font-bold shadow-[0_0_12px_rgba(6,182,212,0.15)]"
                  : "bg-black/50 border-neutral-800 text-neutral-400 hover:text-neutral-200"
              }`}
            >
              Current Site ({target?.tile_id ? target.tile_id.slice(0, 8) : "Active"})
            </button>
            <button
              onClick={() => setExportScope("all")}
              disabled={allResults.length === 0}
              className={`py-2 px-3 rounded text-[11px] uppercase transition-all border ${
                exportScope === "all"
                  ? "bg-cyan-950/40 border-cyan-500/80 text-cyan-300 font-bold shadow-[0_0_12px_rgba(6,182,212,0.15)]"
                  : "bg-black/50 border-neutral-800 text-neutral-400 hover:text-neutral-200 disabled:opacity-40"
              }`}
            >
              All Results ({allResults.length > 0 ? allResults.length : 1})
            </button>
          </div>
        </div>

        {/* Format Options */}
        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <label className="text-[10px] font-mono uppercase tracking-wider text-neutral-400 font-semibold">
              SELECT PACKAGING FORMATS
            </label>
            <button
              type="button"
              onClick={() =>
                setSelectedFormats({
                  pdf: true,
                  evidencePkg: true,
                  geojson: true,
                  csv: true,
                  report: true,
                })
              }
              className="text-[9px] font-mono text-cyan-400 hover:underline"
            >
              SELECT ALL
            </button>
          </div>

          <div className="space-y-2 bg-neutral-900/60 p-3 rounded-lg border border-neutral-800/80 max-h-60 overflow-y-auto pr-1">
            <FormatCheckbox
              label="Forensic Intelligence PDF Dossier (.pdf / Print-Ready)"
              desc="Full classified briefing with visual crops, FFT registration matrix, spectral charts, XAI checklist, and SHA-256 seal"
              checked={selectedFormats.pdf}
              highlight="cyan"
              onChange={(c) => setSelectedFormats((prev) => ({ ...prev, pdf: c }))}
            />
            <FormatCheckbox
              label="Full Evidence Package (.json)"
              desc="Cryptographically verifiable JSON envelope with complete DAG provenance and SHA-256 fingerprint"
              checked={selectedFormats.evidencePkg}
              highlight="emerald"
              onChange={(c) => setSelectedFormats((prev) => ({ ...prev, evidencePkg: c }))}
            />
            <FormatCheckbox
              label="GeoJSON Feature Collection (.geojson)"
              desc="Standard EPSG:4326 geospatial coordinates, similarity scores, and classification metadata"
              checked={selectedFormats.geojson}
              onChange={(c) => setSelectedFormats((prev) => ({ ...prev, geojson: c }))}
            />
            <FormatCheckbox
              label="CSV Analyst Tabular Summary (.csv)"
              desc="Tabular spreadsheet with metrics, sensor parameters, coordinates, and classification"
              checked={selectedFormats.csv}
              onChange={(c) => setSelectedFormats((prev) => ({ ...prev, csv: c }))}
            />
            <FormatCheckbox
              label="Analyst Verification Report (.md)"
              desc="Markdown formatted intelligence briefing with complete physical evidence checklist"
              checked={selectedFormats.report}
              onChange={(c) => setSelectedFormats((prev) => ({ ...prev, report: c }))}
            />
          </div>
        </div>

        {/* Status Notification */}
        {exportStatus && (
          <div className="p-2.5 rounded bg-cyan-950/40 border border-cyan-500/50 text-cyan-300 font-mono text-[10px] flex items-center gap-2 animate-fadeIn">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
            <span>{exportStatus}</span>
          </div>
        )}

        {/* Action Buttons */}
        <div className="space-y-2 pt-1">
          <div className="flex gap-2.5">
            <button
              onClick={onClose}
              className="py-2.5 px-4 rounded bg-neutral-900 hover:bg-neutral-800 text-neutral-300 border border-neutral-700 font-mono text-[11px] uppercase tracking-wider font-semibold transition-all"
            >
              CANCEL
            </button>
            <button
              onClick={handleQuickPdf}
              disabled={downloading || !target}
              className="flex-1 py-2.5 rounded bg-cyan-950 hover:bg-cyan-900 text-cyan-300 border border-cyan-500/60 font-mono text-[11px] uppercase tracking-wider font-bold transition-all disabled:opacity-50 flex items-center justify-center gap-1.5 shadow-[0_0_15px_rgba(6,182,212,0.15)]"
            >
              <span>🖨️</span>
              <span>1-CLICK PDF DOSSIER</span>
            </button>
            <button
              onClick={handleExport}
              disabled={downloading || !target || Object.values(selectedFormats).every((v) => !v)}
              className="flex-1 py-2.5 rounded bg-emerald-500 hover:bg-emerald-400 text-black border border-emerald-300 font-mono text-[11px] uppercase tracking-wider font-bold transition-all disabled:opacity-50 flex items-center justify-center gap-2 shadow-[0_0_15px_rgba(16,185,129,0.2)]"
            >
              {downloading ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-black border-t-transparent rounded-full animate-spin" />
                  <span>PACKAGING...</span>
                </>
              ) : (
                "GENERATE EXPORT"
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function FormatCheckbox({
  label,
  desc,
  checked,
  highlight,
  onChange,
}: {
  label: string;
  desc: string;
  checked: boolean;
  highlight?: "cyan" | "emerald";
  onChange: (c: boolean) => void;
}) {
  return (
    <label className="flex items-start gap-2.5 cursor-pointer group select-none">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 w-4 h-4 rounded bg-black border-neutral-700 text-cyan-500 focus:ring-0 focus:ring-offset-0 cursor-pointer accent-cyan-500"
      />
      <div>
        <p
          className={`text-neutral-200 font-medium group-hover:text-white transition-colors ${
            checked && highlight === "cyan"
              ? "text-cyan-300 font-semibold"
              : checked && highlight === "emerald"
              ? "text-emerald-300 font-semibold"
              : ""
          }`}
        >
          {label}
        </p>
        <p className="text-[10px] text-neutral-500 leading-snug">{desc}</p>
      </div>
    </label>
  );
}
