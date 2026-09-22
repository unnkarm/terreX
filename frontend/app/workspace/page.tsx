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
import SettingsModal, { AnalysisSettings, DEFAULT_ANALYSIS_SETTINGS } from "@/components/SettingsModal";
import {
  searchByText, searchByImage, getSystemStatus, listScenes,
  getDiscoveryClusters,
  SearchResult, FilterState, SystemStatus,
} from "@/lib/api";

// MapLibre touches window at import time — load client-side only.
const MapView = dynamic(() => import("@/components/MapView"), { ssr: false });

interface TargetAoi {
  id: string;
  name: string;
  coords: [number, number];
  query: string;
  sensor?: string;
  bbox?: [number, number, number, number];
}

export default function WorkspacePage() {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [filters, setFilters] = useState<FilterState>({ minSimilarity: 0 });
  const [loading, setLoading] = useState(false);
  const [placeholderWarning, setPlaceholderWarning] = useState(false);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [hasData, setHasData] = useState<boolean | null>(null);
  const [sensors, setSensors] = useState<string[]>([]);
  const [scenes, setScenes] = useState<any[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [isLeftOpen, setIsLeftOpen] = useState(true);
  const [isRightOpen, setIsRightOpen] = useState(true);
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [analysisSettings, setAnalysisSettings] = useState<AnalysisSettings>(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = window.localStorage.getItem("terrex.changeAnalysisSettings");
        if (saved) return { ...DEFAULT_ANALYSIS_SETTINGS, ...JSON.parse(saved) };
      } catch {
        /* fallback */
      }
    }
    return DEFAULT_ANALYSIS_SETTINGS;
  });
  const [discoveryLoading, setDiscoveryLoading] = useState(false);
  const [isDrawingAoi, setIsDrawingAoi] = useState(false);

  const [customCenter, setCustomCenter] = useState<[number, number] | null>(null);

  // Dynamically compute Target AOIs from currently ingested scenes in the database
  const targetAois: TargetAoi[] = useMemo(() => {
    const validScenes = (scenes || []).filter(
      (s) => (s.tile_count ?? 0) > 0 && s.status === "ingested"
    );

    if (validScenes.length === 0) {
      return [
        {
          id: "default",
          name: "All Ingested Regions",
          coords: [88.4, 22.5],
          query: "water bodies and terrain",
          sensor: undefined,
          bbox: undefined,
        },
      ];
    }

    return validScenes.map((s, idx) => {
      const bbox = s.provenance?.bounding_box;
      const centerLon = bbox ? (bbox[0] + bbox[2]) / 2.0 : 88.4;
      const centerLat = bbox ? (bbox[1] + bbox[3]) / 2.0 : 22.5;
      const sensorLabel = s.sensor || "EO";
      const sourceLabel = s.source_portal || s.underlying_dataset || "Copernicus";
      const tileCount = s.tile_count ?? 0;

      return {
        id: s.scene_id || String(idx),
        name: `${sensorLabel} (${tileCount} tiles · ${sourceLabel})`,
        sensor: s.sensor,
        coords: [centerLon, centerLat],
        bbox: bbox as [number, number, number, number] | undefined,
        query: sensorLabel.includes("SAR")
          ? "water bodies and terrain"
          : "urban structures and vegetation cover",
      };
    });
  }, [scenes]);

  // Dynamic search suggestions based on available sensors
  const dynamicSuggestions = useMemo(() => {
    const hasSar = sensors.some((s) => s.toLowerCase().includes("sar") || s.toLowerCase().includes("s1"));
    const hasOptical = sensors.some((s) => s.toLowerCase().includes("sentinel-2") || s.toLowerCase().includes("landsat") || s.toLowerCase().includes("liss"));

    const suggestions: string[] = [];
    if (hasSar) {
      suggestions.push("water bodies and rivers");
      suggestions.push("flooded agricultural land");
      suggestions.push("terrain roughness and wetlands");
    }
    if (hasOptical) {
      suggestions.push("new buildings near water");
      suggestions.push("dense urban expansion");
      suggestions.push("vegetation and forest canopy");
    }
    if (suggestions.length === 0) {
      suggestions.push("water bodies and rivers", "dense urban expansion", "agricultural land");
    }
    return suggestions;
  }, [sensors]);

  const [parsedFilters, setParsedFilters] = useState<any>(null);
  const [lastQuery, setLastQuery] = useState<string>("water bodies and terrain");

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
      .then((loadedScenes) => {
        setScenes(loadedScenes);
        const uniqueSensors = Array.from(new Set(loadedScenes.map((s: any) => s.sensor).filter(Boolean)));
        setSensors(uniqueSensors as string[]);
        if (loadedScenes.length > 0) {
          setHasData(true);
          // Set initial map center to the first ingested scene's center
          const firstBbox = loadedScenes[0]?.provenance?.bounding_box;
          if (firstBbox) {
            const cLon = (firstBbox[0] + firstBbox[2]) / 2.0;
            const cLat = (firstBbox[1] + firstBbox[3]) / 2.0;
            setCustomCenter([cLon, cLat]);
          }
        }
      })
      .catch(() => setSensors([]));

    // Initial search automatically preloads all observations
    runTextSearch("water bodies and terrain", { minSimilarity: 0 });
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
      } else if (res.results.length > 0 && !customCenter) {
        setCustomCenter([res.results[0].lon, res.results[0].lat]);
      }
      if (res.results.length > 0) {
        setSelected(res.results[0]);
        setIsRightOpen(true);
      } else {
        setSelected(null);
      }
    } catch (err: any) {
      setSearchError(err?.message || "Search failed. Offline demo resilience active.");
    } finally {
      setLoading(false);
    }
  }, [filters, customCenter]);

  const handleFindSimilar = useCallback(async (seed: SearchResult) => {
    setDiscoveryLoading(true);
    try {
      const discovery = await getDiscoveryClusters(seed.tile_id, seed.lon, seed.lat, 4, 20);
      const allSites = discovery.clusters.flatMap((c) => c.sites);
      const existingIds = new Set(results.map((r) => r.tile_id));
      const newSites = allSites.filter((s) => !existingIds.has(s.tile_id));
      if (newSites.length > 0) {
        setResults((prev) => [...newSites, ...prev]);
        setSelected(newSites[0]);
        setCustomCenter([newSites[0].lon, newSites[0].lat]);
        setIsRightOpen(true);
      } else if (allSites.length > 0) {
        setSelected(allSites[0]);
        setCustomCenter([allSites[0].lon, allSites[0].lat]);
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

  const handleSelectAoi = useCallback((aoi: typeof targetAois[0]) => {
    setCustomCenter(aoi.coords);
    let bbox = aoi.bbox;
    if (!bbox) {
      const delta = 0.1;
      bbox = [aoi.coords[0] - delta, aoi.coords[1] - delta, aoi.coords[0] + delta, aoi.coords[1] + delta];
    }
    const updated = { ...filters, bbox, polygon: undefined, sensor: aoi.sensor || undefined };
    setFilters(updated);
    runTextSearch(aoi.query, updated);
  }, [filters, runTextSearch]);

  const handleAoiDrawn = useCallback((bbox: [number, number, number, number]) => {
    setIsDrawingAoi(false);
    const updated = { ...filters, bbox, polygon: undefined };
    setFilters(updated);
    runTextSearch(lastQuery, updated);
  }, [filters, lastQuery, runTextSearch]);

  const handleAoiPolygonDrawn = useCallback((polygonGeoJson: { type: "Polygon"; coordinates: number[][][] }) => {
    setIsDrawingAoi(false);
    const updated = { ...filters, polygon: polygonGeoJson, bbox: undefined };
    setFilters(updated);
    runTextSearch(lastQuery, updated);
  }, [filters, lastQuery, runTextSearch]);

  const handleClearBbox = useCallback(() => {
    setIsDrawingAoi(false);
    const updated = { ...filters, bbox: undefined, polygon: undefined };
    setFilters(updated);
    runTextSearch(lastQuery, updated);
  }, [filters, lastQuery, runTextSearch]);

  const center: [number, number] = useMemo(() => {
    if (customCenter) return customCenter;
    if (results.length > 0) return [results[0].lon, results[0].lat];
    if (scenes.length > 0 && scenes[0]?.provenance?.bounding_box) {
      const b = scenes[0].provenance.bounding_box;
      return [(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0];
    }
    return [88.4, 22.5];
  }, [customCenter, results, scenes]);

  const currentSelectedAoi = useMemo(() => {
    return targetAois.find(
      (loc) => Math.abs(center[0] - loc.coords[0]) < 0.15 && Math.abs(center[1] - loc.coords[1]) < 0.15
    );
  }, [targetAois, center]);

  const filteredResults = useMemo(() => {
    let list = [...results];
    if (filters.minChangeEvidence !== undefined && filters.minChangeEvidence > 0) {
      list = list.filter((r) => (r.change_score ?? 0) >= (filters.minChangeEvidence ?? 0));
    }

    const sortOrder = filters.sortBy ?? (parsedFilters?.temporal_change_intent ? "change" : "rank");
    list.sort((a, b) => {
      if (sortOrder === "change") {
        const ca = a.change_score ?? 0;
        const cb = b.change_score ?? 0;
        if (cb !== ca) return cb - ca;
        return b.final_score - a.final_score;
      }
      if (sortOrder === "similarity") {
        return b.similarity_score - a.similarity_score;
      }
      if (sortOrder === "date") {
        const da = a.acquisition_date ? new Date(a.acquisition_date).getTime() : 0;
        const db = b.acquisition_date ? new Date(b.acquisition_date).getTime() : 0;
        return db - da;
      }
      return b.final_score - a.final_score;
    });

    return list;
  }, [results, filters.minChangeEvidence, filters.sortBy, parsedFilters?.temporal_change_intent]);

  return (
    <main className="h-screen w-screen flex flex-col bg-black font-sans relative overflow-hidden select-none">
      {/* Top Navigation Bar */}
      <TopNav
        status={status}
        onExportClick={() => setIsExportOpen(true)}
        onSettingsClick={() => setIsSettingsOpen(true)}
      />

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

      {/* Unified Compact Telemetry & AOI Control Bar */}
      <div className="w-full bg-black/95 border-b border-neutral-800/80 backdrop-blur-md px-4 py-1.5 flex items-center justify-between gap-3 text-xs z-40 font-mono select-none">
        {/* Left: Active Pipeline & Target AOI Selector */}
        <div className="flex items-center gap-3 min-w-0 flex-wrap">
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_#34d399]" />
            <span className="text-emerald-400 font-bold text-[10px] tracking-wider uppercase">ACTIVE EO PIPELINE:</span>
            <span className="px-2 py-0.5 rounded bg-neutral-900 border border-neutral-700 text-cyan-400 font-mono text-[10px] font-bold">
              {sensors.length > 0 ? sensors.join(" + ") : "SAR-C + MSI"}
            </span>
          </div>

          <div className="h-3.5 w-px bg-neutral-800 hidden sm:block" />

          {/* Target AOI Dropdown */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <label htmlFor="target-aoi-select" className="text-amber-400 font-bold text-[10px] tracking-wider uppercase flex items-center gap-1 cursor-pointer">
              <span>TARGET AOI:</span>
            </label>
            <div className="relative inline-flex items-center">
              <select
                id="target-aoi-select"
                value={currentSelectedAoi?.id ?? ""}
                onChange={(e) => {
                  const aoi = targetAois.find((l) => l.id === e.target.value);
                  if (aoi) {
                    handleSelectAoi(aoi);
                  }
                }}
                className="bg-neutral-900 border border-neutral-700 hover:border-amber-500/80 focus:border-amber-500 text-amber-300 font-mono font-bold px-2.5 py-0.5 pr-7 rounded text-[10px] uppercase tracking-wider cursor-pointer outline-none appearance-none transition-all shadow-sm max-w-[280px] truncate"
              >
                <option value="" disabled className="bg-neutral-950 text-neutral-500">
                  SELECT TARGET AOI / SCENE
                </option>
                {targetAois.map((aoi) => (
                  <option key={aoi.id} value={aoi.id} className="bg-neutral-950 text-neutral-200 py-1 font-mono">
                    {aoi.name}
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
        </div>

        {/* Right: Coordinates & Telemetry Stats */}
        <div className="flex items-center gap-3 text-[10px] font-mono tracking-wider uppercase text-neutral-400 flex-shrink-0">
          <div className="hidden md:flex items-center gap-2">
            <span className="text-amber-400/90 font-medium">
              &middot; {scenes.length} SCENES LOADED
            </span>
            <div className="h-3 w-px bg-neutral-800" />
            <span className="text-neutral-400">
              CANDIDATES: <span className="font-bold text-emerald-400">{results.length}</span>
            </span>
          </div>

          <div className="h-3.5 w-px bg-neutral-800 hidden md:block" />

          <div className="flex items-center gap-1.5 text-[10px] font-mono text-neutral-300">
            <span className="text-neutral-500">COORDINATES:</span>
            <span className="font-bold text-white">{center[1].toFixed(4)}°N, {center[0].toFixed(4)}°E</span>
          </div>
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
              activeSensor={filters.sensor}
              suggestions={dynamicSuggestions}
            />

            {/* 2. Multi-Dimensional Filter Bar (AOI, Temporal, Cloud) */}
            <FilterBar
              filters={filters}
              onChange={(f) => {
                setFilters(f);
                runTextSearch(lastQuery, f);
              }}
              sensors={sensors}
              onTriggerDrawBbox={() => setIsDrawingAoi((prev) => !prev)}
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
                results={filteredResults}
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
                temporalQuery={Boolean(parsedFilters?.temporal_change_intent)}
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
            results={filteredResults}
            selectedTileId={selected?.tile_id ?? null}
            onSelect={(r) => {
              setSelected(r);
              setCustomCenter([r.lon, r.lat]);
              setIsRightOpen(true);
            }}
            center={center}
            activeBbox={filters.bbox}
            activePolygon={filters.polygon}
            isDrawingAoi={isDrawingAoi}
            onDrawModeChange={(mode) => setIsDrawingAoi(mode === "box")}
            onAoiDrawn={handleAoiDrawn}
            onAoiPolygonDrawn={handleAoiPolygonDrawn}
          />
        </div>

        {/* Right Column Collapse Toggle Button */}
        {selected && (
          <button
            onClick={() => setIsRightOpen(!isRightOpen)}
            className="absolute top-1/2 -translate-y-1/2 z-40 w-5 h-12 bg-neutral-900 border border-r-0 border-neutral-800 rounded-l flex items-center justify-center text-neutral-400 hover:text-white transition-all shadow-md"
            style={{ right: isRightOpen ? "490px" : "0px" }}
            title={isRightOpen ? "Collapse Inspection Panel" : "Expand Inspection Panel"}
          >
            <span className="text-[10px] font-mono">{isRightOpen ? "›" : "‹"}</span>
          </button>
        )}

        {/* RIGHT COLUMN: Site Inspection & Verification Panel (490px) */}
        {selected && (
          <div
            className={`flex-shrink-0 h-full border-l border-neutral-800/80 bg-neutral-950/95 flex flex-col z-30 overflow-hidden transition-[width,transform] duration-300 ${
              isRightOpen ? "w-[490px] translate-x-0" : "w-0 translate-x-full border-l-0"
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
              analysisSettings={analysisSettings}
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
      <ExportModal
        result={selected}
        allResults={results}
        isOpen={isExportOpen}
        onClose={() => setIsExportOpen(false)}
      />

      {/* Global Analysis Thresholds Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        settings={analysisSettings}
        onSave={(newSettings) => {
          setAnalysisSettings(newSettings);
        }}
      />
    </main>
  );
}
