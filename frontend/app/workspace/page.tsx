"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import Logo from "@/components/Logo";
import SearchBar from "@/components/SearchBar";
import FilterBar from "@/components/FilterBar";
import ResultsList from "@/components/ResultsList";
import ResultDetail from "@/components/ResultDetail";
import {
  searchByText, searchByImage, getSystemStatus, listScenes, processIncoming,
  SearchResult, FilterState, SystemStatus,
} from "@/lib/api";

// MapLibre touches window at import time — load client-side only.
const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

export default function WorkspacePage() {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [filters, setFilters] = useState<FilterState>({ minSimilarity: 0 });
  const [loading, setLoading] = useState(false);
  const [placeholderWarning, setPlaceholderWarning] = useState(false);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [sensors, setSensors] = useState<string[]>([]);
  const [ingestMsg, setIngestMsg] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [isResultsOpen, setIsResultsOpen] = useState(true);
  const [isDetailOpen, setIsDetailOpen] = useState(true);

  useEffect(() => {
    getSystemStatus().then(setStatus).catch(() => setStatus(null));
    listScenes()
      .then((scenes) => setSensors(Array.from(new Set(scenes.map((s: any) => s.sensor).filter(Boolean)))))
      .catch(() => {});
  }, []);

  const runTextSearch = async (query: string) => {
    setLoading(true);
    setSearchError(null);
    try {
      const res = await searchByText(query, filters);
      setResults(res.results);
      setPlaceholderWarning(res.embedding_is_placeholder);
      setSelected(res.results[0] ?? null);
    } catch (err: any) {
      setSearchError(err?.message || "Text search failed.");
    } finally {
      setLoading(false);
    }
  };

  const runImageSearch = async (file: File) => {
    setLoading(true);
    setSearchError(null);
    try {
      const res = await searchByImage(file, filters);
      setResults(res.results);
      setPlaceholderWarning(res.embedding_is_placeholder);
      setSelected(res.results[0] ?? null);
    } catch (err: any) {
      setSearchError(err?.message || "Image search failed.");
    } finally {
      setLoading(false);
    }
  };

  const runProcessIncoming = async () => {
    setIngestMsg("Processing data/incoming/ …");
    try {
      const res = await processIncoming();
      setIngestMsg(`Processed ${res.processed.length} new scene(s), ${res.failed.length} failed.`);
    } catch (e) {
      setIngestMsg(`Error: ${e}`);
    }
  };

  const center: [number, number] = useMemo(() => {
    if (results.length > 0) return [results[0].lon, results[0].lat];
    return [77.25, 28.55]; // demo AOI default
  }, [results.length]);

  return (
    <main className="h-screen w-screen flex flex-col bg-black font-sans relative overflow-hidden">
      {/* Full Bleed Map Background */}
      <div className="absolute inset-0 z-0">
        <MapView results={results} selectedTileId={selected?.tile_id ?? null} onSelect={setSelected} center={center} />
      </div>

      {/* Floating Header */}
      <header className="absolute top-0 left-0 w-full flex items-center justify-between px-6 py-3 bg-black/60 backdrop-blur-md border-b border-neutral-800/80 z-50 shadow-md scanlines">
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2 group">
            <Logo size={28} showText={true} />
          </Link>
          <span className="text-[9px] uppercase font-mono tracking-[0.2em] px-2 py-0.5 rounded-sm border border-neutral-700/50 text-neutral-400 hidden sm:inline bg-black/40">
            AIR-GAPPED EO CONSOLE &middot; EPSG:32645
          </span>
        </div>

        <div className="flex items-center gap-4 text-[10px] font-mono tracking-widest text-neutral-400 uppercase">
          {status && (
            <>
              <StatusPill label="RemoteCLIP" staged={status.models.remoteclip.staged} />
              <StatusPill label="Prithvi-EO" staged={status.models.prithvi.staged} />
              <span className="flex items-center gap-2 text-cyan-500 font-bold ml-2">
                <span className="w-2 h-2 rounded-full bg-cyan-500 shadow-[0_0_8px_#06b6d4]" />
                {status.offline_mode ? "OFFLINE GRID" : "ONLINE SECURE"}
              </span>
            </>
          )}
          <button
            onClick={runProcessIncoming}
            className="ml-4 px-3 py-1.5 rounded-sm border border-neutral-700 text-neutral-300 hover:border-emerald-500 hover:text-emerald-400 transition-all bg-black/50"
          >
            [ INGEST ]
          </button>
          <Link
            href="/"
            className="px-3 py-1.5 rounded-sm border border-neutral-700 text-neutral-400 hover:text-white hover:border-neutral-500 transition-all bg-black/50"
          >
            ← OVERVIEW
          </Link>
        </div>
      </header>

      {/* Bottom Center Search & Filter Panel */}
      <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-40 w-[700px] max-w-[90vw] flex flex-col items-center gap-4">
        {ingestMsg && <p className="text-[10px] font-mono text-neutral-400 uppercase tracking-widest text-center bg-black/60 px-3 py-1 rounded-full">{ingestMsg}</p>}
        {searchError && (
          <div className="flex items-center gap-2 px-4 py-2 rounded-full border border-red-500/40 bg-red-950/80 backdrop-blur-md text-red-400 text-[10px] font-mono uppercase tracking-widest shadow-lg">
            <span className="font-bold">ERROR:</span>
            <span>{searchError}</span>
          </div>
        )}
        
        <FilterBar filters={filters} onChange={setFilters} sensors={sensors} />
        
        <div className="w-full">
          <SearchBar onTextSearch={runTextSearch} onImageSearch={runImageSearch} loading={loading} />
        </div>
      </div>

      {/* Left Tactical Panel (Results List) */}
      <div 
        className={`absolute top-[64px] left-4 bottom-8 w-[340px] z-40 flex flex-col gap-3 transition-transform duration-300 ease-in-out ${
          isResultsOpen ? "translate-x-0" : "-translate-x-[360px]"
        }`}
      >
        {/* Toggle Button */}
        <button
          onClick={() => setIsResultsOpen(!isResultsOpen)}
          className="absolute -right-8 top-1/2 -translate-y-1/2 w-8 h-16 bg-neutral-900/80 backdrop-blur-md border border-l-0 border-neutral-800/80 rounded-r-xl flex items-center justify-center text-neutral-400 hover:text-emerald-400 transition-colors shadow-lg z-50"
        >
          <svg className={`w-4 h-4 transition-transform duration-300 ${!isResultsOpen && "rotate-180"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>

        {/* Results List Block */}
        <div className="flex-1 min-h-0 bg-black/85 backdrop-blur-md border border-neutral-800/80 rounded-2xl shadow-[0_0_20px_rgba(0,0,0,0.8)] overflow-hidden flex flex-col scanlines">
          <ResultsList
            results={results}
            selectedTileId={selected?.tile_id ?? null}
            onSelect={(item) => {
              setSelected(item);
              setIsDetailOpen(true);
            }}
            placeholderWarning={placeholderWarning}
          />
        </div>
      </div>

      {/* Right Tactical Panel (Target Inspection) */}
      {selected && (
        <div 
          className={`absolute top-[64px] right-4 bottom-4 w-[340px] z-40 flex flex-col gap-3 transition-transform duration-300 ease-in-out ${
            isDetailOpen ? "translate-x-0" : "translate-x-[360px]"
          }`}
        >
          {/* Toggle Button */}
          <button
            onClick={() => setIsDetailOpen(!isDetailOpen)}
            className="absolute -left-8 top-1/2 -translate-y-1/2 w-8 h-16 bg-neutral-900/80 backdrop-blur-md border border-r-0 border-neutral-800/80 rounded-l-xl flex items-center justify-center text-neutral-400 hover:text-emerald-400 transition-colors shadow-lg z-50"
          >
            <svg className={`w-4 h-4 transition-transform duration-300 ${isDetailOpen && "rotate-180"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>

          <div className="flex-1 min-h-0 bg-black/90 backdrop-blur-xl border border-neutral-800 shadow-[0_0_30px_rgba(0,0,0,0.9)] rounded-2xl overflow-hidden flex flex-col">
            <ResultDetail result={selected} onClose={() => setSelected(null)} />
          </div>
        </div>
      )}
    </main>
  );
}

function StatusPill({ label, staged }: { label: string; staged: boolean }) {
  return (
    <span
      className={`px-2 py-0.5 rounded border font-sans text-[10px] ${
        staged ? "border-radar/40 text-radar bg-radar/10" : "border-warn/40 text-warn bg-warn/10"
      }`}
      title={staged ? `${label} real weights loaded` : `${label} running on placeholder — see README`}
    >
      {label} {staged ? "✓" : "placeholder"}
    </span>
  );
}
