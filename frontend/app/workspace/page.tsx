"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import dynamic from "next/dynamic";
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
  const [sensors, setSensors] = useState<string[]>([]);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [isLeftOpen, setIsLeftOpen] = useState(true);
  const [isRightOpen, setIsRightOpen] = useState(true);
  const [isExportOpen, setIsExportOpen] = useState(false);

  useEffect(() => {
    getSystemStatus().then(setStatus).catch(() => setStatus(null));
    listScenes()
      .then((scenes) => {
        setSensors(Array.from(new Set(scenes.map((s: any) => s.sensor).filter(Boolean))));
      })
      .catch(() => {});

    // Initial search to populate candidate grid
    runTextSearch("Newly built structures near a river");
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

  const handleAoiDrawn = useCallback((bbox: [number, number, number, number]) => {
    const updated = { ...filters, bbox };
    setFilters(updated);
    runTextSearch("Newly built structures near a river");
  }, [filters, runTextSearch]);

  const handleClearBbox = useCallback(() => {
    const updated = { ...filters, bbox: undefined };
    setFilters(updated);
    runTextSearch("Newly built structures near a river");
  }, [filters, runTextSearch]);

  const center: [number, number] = useMemo(() => {
    if (selected) return [selected.lon, selected.lat];
    if (results.length > 0) return [results[0].lon, results[0].lat];
    return [77.2912, 28.5684]; // Yamuna Riverbank demo AOI
  }, [selected, results.length]);

  return (
    <main className="h-screen w-screen flex flex-col bg-black font-sans relative overflow-hidden select-none">
      {/* Top Navigation Bar */}
      <TopNav status={status} onExportClick={() => setIsExportOpen(true)} />

      {/* Geospatial Intelligence Telemetry Bar (Focused MVP) */}
      <div className="w-full bg-neutral-950/90 border-b border-neutral-800/80 px-6 py-2 flex items-center justify-between z-40">
        <div className="flex items-center gap-3">
          <span className="text-[10px] font-mono text-radar font-semibold uppercase tracking-widest flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-radar animate-pulse" />
            PRIMARY SENSOR:
          </span>
          <span className="px-2 py-0.5 rounded bg-neutral-900 border border-neutral-700 text-cyan-400 font-mono text-[10px] font-bold">
            SENTINEL-2 MSI (10M GSD)
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
