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
  getDiscoveryClusters,
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
  const [discoveryLoading, setDiscoveryLoading] = useState(false);

  const [customCenter, setCustomCenter] = useState<[number, number] | null>([88.2619, 22.5905]); // Default Kolkata AOI

  const INDIAN_LOCATIONS = useMemo(() => [
    { id: "kolkata", name: "Kolkata (Hooghly Basin)", coords: [88.2619, 22.5905] as [number, number], query: "Urban infrastructure & waterways in Kolkata" },
    { id: "delhi", name: "Delhi NCR (Yamuna)", coords: [77.2257, 28.5743] as [number, number], query: "River corridor and expanding built-up settlements" },
    { id: "bengaluru", name: "Bengaluru (Outskirts)", coords: [77.6602, 12.8452] as [number, number], query: "Urban expansion & roads in Bengaluru outskirts" },
    { id: "ahmedabad", name: "Ahmedabad (Sabarmati)", coords: [72.5714, 23.0225] as [number, number], query: "Industrial development in Ahmedabad" },
    { id: "mumbai", name: "Mumbai (Coastal)", coords: [72.8777, 19.0760] as [number, number], query: "Dense coastal construction in Mumbai" },
  ], []);

  const [parsedFilters, setParsedFilters] = useState<any>(null);
  const [lastQuery, setLastQuery] = useState<string>("Sentinel-2 satellite observation");

  useEffect(() => {
    getSystemStatus()
      .then((systemStatus) => {
        setStatus(systemStatus);
        setHasData(typeof systemStatus.vector_index_count === "number" ? systemStatus.vector_index_count > 0 : null);
      })
      .catch(() => {
        setStatus(null);
        setHasData(true);
      });

    listScenes()
      .then((scenes) => {
        setSensors(Array.from(new Set(scenes.map((s: any) => s.sensor).filter(Boolean))));
        if (scenes.length > 0) setHasData(true);
      })
      .catch(() => setSensors([]));

    // Initial search automatically preloads all Sentinel observations
    runTextSearch("Sentinel-2 satellite observation");
  }, []);

  const runTextSearch = useCallback(async (query: string, currentFilters?: FilterState) => {
    setLoading(true);
    setSearchError(null);
    setLastQuery(query);
    const activeF = currentFilters ?? filters;
    try {
      const res = await searchByText(query, activeF, 20);
      setResults(res.results);
      setPlaceholderWarning(res.embedding_is_placeholder);
      if (res.parsed_filters) {
        setParsedFilters(res.parsed_filters);
      }
      if (res.target_location) {
        setCustomCenter([res.target_location.lon, res.target_location.lat]);
      } else if (res.results.length > 0) {
        setCustomCenter([res.results[0].lon, res.results[0].lat]);
      }
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

  const handleFindSimilar = useCallback(async (seed: SearchResult) => {
    setDiscoveryLoading(true);
    try {
      const discovery = await getDiscoveryClusters(seed.tile_id, seed.lon, seed.lat, 4, 20);
      // Flatten all cluster sites into results queue (deduplicated by tile_id)
      const allSites = discovery.clusters.flatMap((c) => c.sites);
      const existingIds = new Set(results.map((r) => r.tile_id));
      const newSites = allSites.filter((s) => !existingIds.has(s.tile_id));
      setResults((prev) => [...prev, ...newSites]);
      // Show the first new site in the detail panel
      if (newSites.length > 0) {
        setSelected(newSites[0]);
        setIsRightOpen(true);
      }
    } catch (err: any) {
      console.warn("Discovery failed:", err);
    } finally {
      setDiscoveryLoading(false);
    }
  }, [results]);

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
    const updated = { ...filters, bbox, polygon: undefined };
    setFilters(updated);
    runTextSearch(loc.query, updated);
  }, [filters, runTextSearch]);

  const handleAoiDrawn = useCallback((bbox: [number, number, number, number]) => {
    const updated = { ...filters, bbox, polygon: undefined };
    setFilters(updated);
    runTextSearch(lastQuery, updated);
  }, [filters, lastQuery, runTextSearch]);

  const handleAoiPolygonDrawn = useCallback((polygonGeoJson: { type: "Polygon"; coordinates: number[][][] }) => {
    const updated = { ...filters, polygon: polygonGeoJson, bbox: undefined };
    setFilters(updated);
    runTextSearch(lastQuery, updated);
  }, [filters, lastQuery, runTextSearch]);

  const handleClearBbox = useCallback(() => {
    const updated = { ...filters, bbox: undefined, polygon: undefined };
    setFilters(updated);
    runTextSearch(lastQuery, updated);
  }, [filters, lastQuery, runTextSearch]);

  // customCenter takes priority: set explicitly by search/gazetteer/AOI buttons.
  // When user clicks a tile, we also update customCenter to that tile's location.
  const center: [number, number] = useMemo(() => {
    if (customCenter) return customCenter;
    if (results.length > 0) return [results[0].lon, results[0].lat];
    return [88.2619, 22.5905]; // Kolkata New Town default
  }, [customCenter, results]);

  const currentSelectedLoc = useMemo(() => {
    return INDIAN_LOCATIONS.find(
      (loc) => Math.abs(center[0] - loc.coords[0]) < 0.08 && Math.abs(center[1] - loc.coords[1]) < 0.08
    );
  }, [INDIAN_LOCATIONS, center]);

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
      <div className="w-full bg-black/95 border-b border-neutral-800/80 px-6 py-1.5 flex items-center justify-between gap-3 text-[10px] font-mono z-40">
        <div className="flex items-center gap-2.5 flex-shrink-0">
          <label htmlFor="target-aoi-select" className="text-neutral-400 uppercase tracking-wider font-bold flex items-center gap-1.5 cursor-pointer">
            <span className="text-amber-500">🇮🇳</span> TARGET AOI:
          </label>
          <div className="relative inline-flex items-center">
            <select
              id="target-aoi-select"
              value={currentSelectedLoc?.id ?? ""}
              onChange={(e) => {
                const loc = INDIAN_LOCATIONS.find((l) => l.id === e.target.value);
                if (loc) {
                  handleSelectIndianLocation(loc);
                }
              }}
              className="bg-neutral-900 border border-neutral-700 hover:border-amber-500/80 focus:border-amber-500 text-amber-300 font-semibold px-3 py-1 pr-8 rounded text-[10px] uppercase tracking-wider cursor-pointer outline-none appearance-none transition-all shadow-sm"
            >
              <option value="" disabled className="bg-neutral-950 text-neutral-500">
                SELECT TARGET AOI
              </option>
              {INDIAN_LOCATIONS.map((loc) => (
                <option key={loc.id} value={loc.id} className="bg-neutral-950 text-neutral-200 py-1 font-mono">
                  {loc.name}
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-amber-400">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </div>
          </div>
        </div>
        <div className="hidden lg:flex items-center gap-2 text-neutral-500 text-[9px]">
          <span>INDIAN EO INTEGRATION: BHUVAN LISS-III &middot; MOSDAC API &middot; SENTINEL-2 L2A</span>
        </div>
      </div>

      {/* 3-Column Operational Workspace Layout */}
      <div className="flex-1 min-h-0 flex relative overflow-hidden">

        {/* LEFT COLUMN: Search & Filters & Ranked Results (390px) */}
        <div
          className={`flex-shrink-0 h-full border-r border-neutral-800/80 bg-neutral-950/95 flex flex-col z-30 overflow-hidden transition-[width,transform] duration-300 ${
            isLeftOpen ? "w-[390px] translate-x-0" : "w-0 -translate-x-full border-r-0"
          }`}
        >
          <div className="flex flex-col h-full min-w-[390px] overflow-y-auto overflow-x-hidden p-3 gap-2.5">
            {/* 1. Intent-Aware SearchBar (Semantic Text & Reference Chip) */}
            <SearchBar
              onTextSearch={runTextSearch}
              onImageSearch={runImageSearch}
              loading={loading}
              parsedFilters={parsedFilters}
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
            <div className="flex-none rounded border border-neutral-800/80 overflow-hidden">
              <ResultsList
                results={results}
                selectedTileId={selected?.tile_id ?? null}
                onSelect={(r) => {
                  setSelected(r);
                  setCustomCenter([r.lon, r.lat]);
                  setIsRightOpen(true);
                }}
                onInspect={(r) => {
                  setSelected(r);
                  setCustomCenter([r.lon, r.lat]);
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
              setCustomCenter([r.lon, r.lat]);
              setIsRightOpen(true);
            }}
            center={center}
            onAoiDrawn={handleAoiDrawn}
            onAoiPolygonDrawn={handleAoiPolygonDrawn}
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
            className={`flex-shrink-0 h-full border-l border-neutral-800/80 bg-neutral-950/95 flex flex-col z-30 overflow-hidden transition-[width,transform] duration-300 ${
              isRightOpen ? "w-[420px] translate-x-0" : "w-0 translate-x-full border-l-0"
            }`}
          >
            <ResultDetail
              key={selected.tile_id}
              result={selected}
              onClose={() => setSelected(null)}
              onFindSimilar={handleFindSimilar}
              onCitationClick={(citationId) => {
                const cited = results.find((item) => item.tile_id === citationId);
                if (cited) setSelected(cited);
              }}
            />
            {discoveryLoading && (
              <div className="absolute bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 bg-neutral-900 border border-cyan-700/60 text-cyan-400 font-mono text-[10px] rounded shadow-lg z-50 flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                DISCOVERING SIMILAR SITES...
              </div>
            )}
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
