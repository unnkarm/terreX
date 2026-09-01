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

  useEffect(() => {
    getSystemStatus().then(setStatus).catch(() => setStatus(null));
    listScenes()
      .then((scenes) => setSensors(Array.from(new Set(scenes.map((s: any) => s.sensor).filter(Boolean)))))
      .catch(() => {});
  }, []);

  const runTextSearch = async (query: string) => {
    setLoading(true);
    try {
      const res = await searchByText(query, filters);
      setResults(res.results);
      setPlaceholderWarning(res.embedding_is_placeholder);
      setSelected(res.results[0] ?? null);
    } finally {
      setLoading(false);
    }
  };

  const runImageSearch = async (file: File) => {
    setLoading(true);
    try {
      const res = await searchByImage(file, filters);
      setResults(res.results);
      setPlaceholderWarning(res.embedding_is_placeholder);
      setSelected(res.results[0] ?? null);
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
    <main className="h-screen w-screen flex flex-col bg-black font-sans">
      {/* Tactical Header */}
      <header className="flex items-center justify-between px-4 py-2 border-b border-neutral-800 bg-neutral-950">
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2 group">
            <Logo size={32} showText={true} />
          </Link>
          <span className="text-[10px] uppercase font-sans tracking-widest px-2 py-0.5 rounded border border-neutral-800 text-neutral-400 hidden sm:inline bg-black">
            AIR-GAPPED EO CONSOLE &middot; EPSG:32645
          </span>
        </div>

        <div className="flex items-center gap-3 text-[11px] font-sans text-neutral-400">
          {status && (
            <>
              <StatusPill label="RemoteCLIP" staged={status.models.remoteclip.staged} />
              <StatusPill label="Prithvi-EO" staged={status.models.prithvi.staged} />
              <span className="flex items-center gap-1.5 text-radar font-semibold">
                <span className="w-1.5 h-1.5 rounded-full bg-radar" />
                {status.offline_mode ? "OFFLINE AIR-GAPPED" : "ONLINE"}
              </span>
            </>
          )}
          <button
            onClick={runProcessIncoming}
            className="px-2.5 py-1 rounded border border-neutral-700 text-neutral-200 hover:bg-neutral-800 transition text-[11px] font-sans"
          >
            + Ingest Incoming
          </button>
          <Link
            href="/"
            className="px-2.5 py-1 rounded border border-neutral-800 text-neutral-400 hover:text-white hover:border-neutral-600 transition text-[11px] font-sans"
          >
            ← Overview
          </Link>
        </div>
      </header>

      {/* Search + filters */}
      <div className="px-4 py-2.5 border-b border-neutral-800 bg-neutral-950 space-y-2">
        <SearchBar onTextSearch={runTextSearch} onImageSearch={runImageSearch} loading={loading} />
        <FilterBar filters={filters} onChange={setFilters} sensors={sensors} />
        {ingestMsg && <p className="text-[11px] font-mono text-neutral-300">{ingestMsg}</p>}
      </div>

      {/* Main content: map | results | detail */}
      <div className="flex-1 flex min-h-0">
        <div className="flex-1 min-w-0 border-r border-neutral-800">
          <MapView results={results} selectedTileId={selected?.tile_id ?? null} onSelect={setSelected} center={center} />
        </div>
        <div className="w-80 flex-shrink-0 border-r border-neutral-800 bg-neutral-950">
          <ResultsList
            results={results}
            selectedTileId={selected?.tile_id ?? null}
            onSelect={setSelected}
            placeholderWarning={placeholderWarning}
          />
        </div>
        <div className="w-96 flex-shrink-0 bg-black overflow-y-auto">
          <ResultDetail result={selected} onClose={() => setSelected(null)} />
        </div>
      </div>
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
