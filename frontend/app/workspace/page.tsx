"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import TopNav from "@/components/TopNav";
import SearchBar from "@/components/SearchBar";
import FilterBar from "@/components/FilterBar";
import ResultsList from "@/components/ResultsList";
import ResultDetail from "@/components/ResultDetail";
import ExportModal from "@/components/ExportModal";
import {
  searchByText, searchByImage, getSystemStatus, listScenes,
  SearchResult, FilterState, SystemStatus,
} from "@/lib/api";

// MapLibre touches window at import time — load client-side only.
const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

export default function WorkspacePage() {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [filters, setFilters] = useState<FilterState>({ minSimilarity: 0, sensor: "Sentinel-2" });
  const [loading, setLoading] = useState(false);
  const [placeholderWarning, setPlaceholderWarning] = useState(false);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [hasData, setHasData] = useState<boolean | null>(null);
  const [sensors, setSensors] = useState<string[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [isLeftOpen, setIsLeftOpen] = useState(true);
  const [isRightOpen, setIsRightOpen] = useState(true);
  const [isExportOpen, setIsExportOpen] = useState(false);

  const [customCenter, setCustomCenter] = useState<[number, number] | null>([88.4754, 22.5867]); // Default Kolkata New Town

  const INDIAN_LOCATIONS = useMemo(() => [
    { id: "kolkata", name: "Kolkata (New Town)", coords: [88.4754, 22.5867] as [number, number], query: "New buildings near water in New Town, Kolkata" },
    { id: "delhi", name: "Delhi NCR (Yamuna)", coords: [77.2912, 28.5684] as [number, number], query: "Highways & construction along Yamuna corridor" },
    { id: "bengaluru", name: "Bengaluru (Outskirts)", coords: [77.6602, 12.8452] as [number, number], query: "Urban expansion & roads in Bengaluru outskirts" },
    { id: "ahmedabad", name: "Ahmedabad (Sabarmati)", coords: [72.5714, 23.0225] as [number, number], query: "Industrial development in Ahmedabad" },
    { id: "mumbai", name: "Mumbai (Coastal)", coords: [72.8777, 19.0760] as [number, number], query: "Dense coastal construction in Mumbai" },
  ], []);

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

    // Initial search focused on Kolkata New Town
    runTextSearch("New buildings near water in New Town, Kolkata");
  }, []);

  const runTextSearch = useCallback(async (query: string) => {
    setLoading(true);
    setSearchError(null);
    try {
      const res = await searchByText(query, filters, 20);
      setResults(res.results);
      setPlaceholderWarning(res.embedding_is_placeholder);
      if (res.results.length > 0) {
        setSelected(res.results[0]);
        setIsRightOpen(true);
      }
    } catch (err: any) {
      setSearchError(err?.message || "Search failed. Offline demo resilience active.");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  const runImageSearch = useCallback(async (file: File) => {
    setLoading(true);
    setSearchError(null);
    try {
      const res = await searchByImage(file, filters, 20);
      setResults(res.results);
      if (res.results.length > 0) {
        setSelected(res.results[0]);
        setIsRightOpen(true);
      }
    } catch (err: any) {
      setSearchError(err?.message || "Image search failed.");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  const handleSelectIndianLocation = useCallback((loc: typeof INDIAN_LOCATIONS[0]) => {
    setCustomCenter(loc.coords);
    const delta = 0.05;
    const bbox: [number, number, number, number] = [
      loc.coords[0] - delta,
      loc.coords[1] - delta,
      loc.coords[0] + delta,
      loc.coords[1] + delta,
    ];
    setFilters((prev) => ({ ...prev, bbox }));
    runTextSearch(loc.query);
  }, [runTextSearch]);

  const handleAoiDrawn = useCallback((bbox: [number, number, number, number]) => {
    const updated = { ...filters, bbox };
    setFilters(updated);
    runTextSearch("New buildings near water in New Town, Kolkata");
  }, [filters, runTextSearch]);

  const handleClearBbox = useCallback(() => {
    const updated = { ...filters, bbox: undefined };
    setFilters(updated);
    runTextSearch("New buildings near water in New Town, Kolkata");
  }, [filters, runTextSearch]);

  const center: [number, number] = useMemo(() => {
    if (selected) return [selected.lon, selected.lat];
    if (customCenter) return customCenter;
    if (results.length > 0) return [results[0].lon, results[0].lat];
    return [88.4754, 22.5867]; // Kolkata New Town AOI
  }, [selected, customCenter, results]);

  return (
    <main className="h-screen w-screen flex flex-col bg-black font-sans relative overflow-hidden select-none">
      {/* Top Navigation Bar */}
      <TopNav status={status} onExportClick={() => setIsExportOpen(true)} />

      {/* Empty State Warning if vector index has no data */}
      {hasData === false && (
        <div className="absolute inset-0 z-[45] flex items-center justify-center bg-black/95 backdrop-blur-sm">
          <div className="mx-5 w-full max-w-xl border border-neutral-800 bg-black/90 px-6 py-8 text-center shadow-[0_0_50px_rgba(0,0,0,0.8)] md:px-10 md:py-10">
            <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center border border-emerald-500/50 bg-emerald-950/20 text-emerald-400">
              <svg className="h-7 w-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
              </svg>
            </div>
            <p className="font-mono text-[10px] uppercase tracking-[0.25em] text-amber-400">Vector Index Empty</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-white md:text-3xl">Ingest data to access the workspace</h2>
            <p className="mx-auto mt-4 max-w-md text-sm leading-6 text-neutral-400">No satellite scenes are available in the local vector database yet. Add a scene to enable search, change detection, and evidence analysis.</p>
            <Link href="/ingest" className="mt-7 inline-flex items-center gap-3 border border-emerald-400 bg-emerald-500 px-5 py-3 font-mono text-[11px] font-bold uppercase tracking-[0.15em] text-black transition-colors hover:bg-emerald-300">
              Add satellite data <span aria-hidden="true">&rarr;</span>
            </Link>
          </div>
        </div>
      )}

      {/* Geospatial Intelligence Telemetry Bar */}
      <div className="w-full bg-neutral-950/90 border-b border-neutral-800/80 px-6 py-2 flex items-center justify-between z-40">
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono text-radar font-semibold uppercase tracking-widest flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-radar animate-pulse" />
            INDIAN EO PIPELINE:
          </span>
          <span className="px-2 py-0.5 rounded bg-neutral-900 border border-neutral-700 text-cyan-400 font-mono text-[10px] font-bold">
            SENTINEL-2 + ISRO BHUVAN / MOSDAC
          </span>
          <span className="hidden md:inline-block text-[10px] text-neutral-500 font-mono">
            &middot; EPSG:32645 (UTM 45N)
          </span>
        </div>

        <div className="flex items-center gap-4 text-[10px] font-mono text-neutral-400">
          <span>COORDINATES: <strong className="text-white">{center[1].toFixed(4)}°N, {center[0].toFixed(4)}°E</strong></span>
          <span className="hidden sm:inline-block">CANDIDATES: <strong className="text-emerald-400">{results.length}</strong></span>
        </div>
      </div>

      {/* Indian AOI Location Fast Selector */}
      <div className="w-full bg-black/95 border-b border-neutral-800/80 px-6 py-1.5 flex items-center justify-between gap-2 overflow-x-auto text-[10px] font-mono z-40">
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-neutral-500 uppercase tracking-wider font-bold flex items-center gap-1">
            <span className="text-amber-500">🇮🇳</span> TARGET AOI:
          </span>
          {INDIAN_LOCATIONS.map((loc) => {
            const isCurrent = Math.abs(center[0] - loc.coords[0]) < 0.05 && Math.abs(center[1] - loc.coords[1]) < 0.05;
            return (
              <button
                key={loc.id}
                onClick={() => handleSelectIndianLocation(loc)}
                className={`px-2.5 py-1 rounded transition-all tracking-wider uppercase font-semibold ${
                  isCurrent
                    ? "bg-amber-500/20 border border-amber-500/80 text-amber-300 shadow-sm"
                    : "bg-neutral-900 border border-neutral-800 text-neutral-400 hover:text-neutral-200 hover:border-neutral-700"
                }`}
              >
                {loc.name}
              </button>
            );
          })}
        </div>
        <div className="hidden lg:flex items-center gap-2 text-neutral-500 text-[9px]">
          <span>INDIAN EO INTEGRATION: BHUVAN LISS-III &middot; MOSDAC API &middot; SENTINEL-2 L2A</span>
        </div>
      </div>

      {/* 3-Column Operational Workspace Layout */}
      <div className="flex-1 min-h-0 flex relative overflow-hidden">
        
        {/* LEFT COLUMN: Search & Filters & Ranked Results (390px) */}
        <div
          className={`w-[390px] flex-shrink-0 h-full border-r border-neutral-800/80 bg-neutral-950/95 flex flex-col z-30 transition-transform duration-300 ${
            isLeftOpen ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          <div className="flex flex-col h-full overflow-hidden p-3 gap-2.5">
            {/* 1. Intent-Aware SearchBar (Semantic Text & Reference Chip) */}
            <SearchBar
              onTextSearch={runTextSearch}
              onImageSearch={runImageSearch}
              loading={loading}
            />

            {/* 2. Multi-Dimensional Filter Bar (AOI, Temporal, Cloud) */}
            <FilterBar
              filters={filters}
              onChange={setFilters}
              sensors={sensors}
              onTriggerDrawBbox={() => {}}
              onClearBbox={handleClearBbox}
            />

            {/* Error notification if any */}
            {searchError && (
              <div className="p-2 rounded bg-red-950/40 border border-red-800/50 text-red-400 font-mono text-[10px]">
                NOTICE: {searchError}
              </div>
            )}

            {/* 3. Ranked Candidate Results Queue */}
            <div className="flex-1 min-h-0 rounded border border-neutral-800/80 overflow-hidden">
              <ResultsList
                results={results}
                selectedTileId={selected?.tile_id ?? null}
                onSelect={(r) => {
                  setSelected(r);
                  setIsRightOpen(true);
                }}
                onInspect={(r) => {
                  setSelected(r);
                  setIsRightOpen(true);
                }}
                placeholderWarning={placeholderWarning}
              />
            </div>
          </div>
        </div>

        {/* Left Column Collapse Toggle Button */}
        <button
          onClick={() => setIsLeftOpen(!isLeftOpen)}
          className="absolute left-[390px] top-1/2 -translate-y-1/2 z-40 w-5 h-12 bg-neutral-900 border border-l-0 border-neutral-800 rounded-r flex items-center justify-center text-neutral-400 hover:text-white transition-all shadow-md"
          style={{ left: isLeftOpen ? "390px" : "0px" }}
          title={isLeftOpen ? "Collapse Left Panel" : "Expand Left Panel"}
        >
          <span className="text-[10px] font-mono">{isLeftOpen ? "‹" : "›"}</span>
        </button>

        {/* CENTER COLUMN: Full Map View with AOI Tools */}
        <div className="flex-1 h-full relative z-10">
          <MapView
            results={results}
            selectedTileId={selected?.tile_id ?? null}
            onSelect={(r) => {
              setSelected(r);
              setIsRightOpen(true);
            }}
            center={center}
            onAoiDrawn={handleAoiDrawn}
          />
        </div>

        {/* Right Column Collapse Toggle Button */}
        {selected && (
          <button
            onClick={() => setIsRightOpen(!isRightOpen)}
            className="absolute top-1/2 -translate-y-1/2 z-40 w-5 h-12 bg-neutral-900 border border-r-0 border-neutral-800 rounded-l flex items-center justify-center text-neutral-400 hover:text-white transition-all shadow-md"
            style={{ right: isRightOpen ? "420px" : "0px" }}
            title={isRightOpen ? "Collapse Inspection Panel" : "Expand Inspection Panel"}
          >
            <span className="text-[10px] font-mono">{isRightOpen ? "›" : "‹"}</span>
          </button>
        )}

        {/* RIGHT COLUMN: Site Inspection & Verification Panel (420px) */}
        {selected && (
          <div
            className={`w-[420px] flex-shrink-0 h-full border-l border-neutral-800/80 bg-neutral-950/95 flex flex-col z-30 transition-transform duration-300 ${
              isRightOpen ? "translate-x-0" : "translate-x-full"
            }`}
          >
            <ResultDetail
              result={selected}
              onClose={() => setSelected(null)}
              onCitationClick={(citationId) => {
                const cited = results.find((item) => item.tile_id === citationId);
                if (cited) setSelected(cited);
              }}
            />
          </div>
        )}

      </div>

      {/* Export Modal */}
      {selected && (
        <ExportModal
          result={selected}
          isOpen={isExportOpen}
          onClose={() => setIsExportOpen(false)}
        />
      )}
    </main>
  );
}
