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
  const [hasData, setHasData] = useState<boolean | null>(null);
  const [ingestMsg, setIngestMsg] = useState<string | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [isResultsOpen, setIsResultsOpen] = useState(true);
  const [isDetailOpen, setIsDetailOpen] = useState(true);

  useEffect(() => {
    getSystemStatus()
      .then((systemStatus) => {
        setStatus(systemStatus);
        setHasData((systemStatus.vector_index_count ?? 0) > 0);
      })
      .catch(() => setStatus(null));
    listScenes()
      .then((scenes) => {
        setSensors(Array.from(new Set(scenes.map((s: any) => s.sensor).filter(Boolean))));
      })
      .catch(() => setSensors([]));
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

  const center: [number, number] = useMemo(() => {
    if (results.length > 0) return [results[0].lon, results[0].lat];
    return [77.25, 28.55]; // demo AOI default
  }, [results.length]);

  return (
    <main className="h-screen w-screen flex flex-col bg-black font-sans relative overflow-hidden">
      {/* Empty State Overlay */}
      {hasData === false && (
        <div className="absolute inset-0 z-[45] flex items-center justify-center bg-black/95 backdrop-blur-sm scanlines">
          <div className="mx-5 w-full max-w-xl border border-neutral-800 bg-black/90 px-6 py-8 text-center shadow-[0_0_50px_rgba(0,0,0,0.8)] md:px-10 md:py-10">
            <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center border border-emerald-500/50 bg-emerald-950/20 text-emerald-400">
              <svg className="h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
              </svg>
            </div>
            <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-amber-400">Index empty</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-white md:text-3xl">Ingest data to access the dashboard</h2>
            <p className="mx-auto mt-4 max-w-md text-sm leading-6 text-neutral-400">No satellite scenes are available in the local vector database yet. Add a scene to enable search, change detection, and evidence chat.</p>
            <Link href="/ingest" className="mt-7 inline-flex items-center gap-3 border border-emerald-400 bg-emerald-500 px-5 py-3 font-mono text-[11px] font-bold uppercase tracking-[0.15em] text-black transition-colors hover:bg-emerald-300">Add satellite data <span aria-hidden="true">→</span></Link>
          </div>
        </div>
      )}

      {/* Full Bleed Map Background */}
      {hasData !== false && (
        <div className="absolute inset-0 z-0">
          <MapView results={results} selectedTileId={selected?.tile_id ?? null} onSelect={setSelected} center={center} />
        </div>
      )}

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
              {status.embedding_version_warning && (
                <span className="border border-amber-700/60 bg-amber-950/30 px-2 py-0.5 text-amber-400" title="Stored vectors were created with a different embedding model version">
                  INDEX VERSION MISMATCH
                </span>
              )}
              <StatusPill label="RemoteCLIP" staged={status.models.remoteclip.staged} />
              <StatusPill label="Prithvi-EO" staged={status.models.prithvi.staged} />
              <span className="flex items-center gap-2 text-cyan-500 font-bold ml-2">
                <span className="w-2 h-2 rounded-full bg-cyan-500 shadow-[0_0_8px_#06b6d4]" />
                {status.offline_mode ? "OFFLINE GRID" : "ONLINE SECURE"}
              </span>
            </>
          )}
          <Link
            href="/ingest"
            className="ml-4 px-3 py-1.5 rounded-sm border border-neutral-700 text-neutral-300 hover:border-emerald-500 hover:text-emerald-400 transition-all bg-black/50"
          >
            [ ADD DATA ]
          </Link>
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
          className={`absolute top-[64px] right-4 bottom-4 w-[min(340px,calc(100vw-2rem))] z-40 flex flex-col gap-3 transition-transform duration-300 ease-in-out ${
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
            <ResultDetail
              result={selected}
              onClose={() => setSelected(null)}
              onCitationClick={(citationId) => {
                const cited = results.find((item) => item.tile_id === citationId);
                if (cited) setSelected(cited);
              }}
            />
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
