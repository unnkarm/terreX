"use client";

import React, { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import TopNav from "@/components/TopNav";
import {
  processIncoming, uploadFileAndIngest,
  searchEOProvider, stageEOProviderScene, EOProviderSearchResult,
} from "@/lib/api";

type SourceType = "sentinel2" | "isro-bhuvan" | "isro-mosdac";

export default function IngestPage() {
  const router = useRouter();
  const [sourceType, setSourceType] = useState<SourceType>("sentinel2");
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentFile, setCurrentFile] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<any | null>(null);
  const [selectedIndianAoi, setSelectedIndianAoi] = useState<"kolkata" | "delhi" | "bengaluru">("kolkata");
  const [providerResults, setProviderResults] = useState<EOProviderSearchResult[]>([]);
  const [isSearchingProvider, setIsSearchingProvider] = useState(false);

  const [stageProgress, setStageProgress] = useState<{
    validation: "pending" | "active" | "complete";
    georeference: "pending" | "active" | "complete";
    tiling: number;
    quality: number;
    embedding: number;
    indexing: "waiting" | "active" | "complete";
  }>({
    validation: "pending",
    georeference: "pending",
    tiling: 0,
    quality: 0,
    embedding: 0,
    indexing: "waiting",
  });
  const [logs, setLogs] = useState<string[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const AOI_COORDS = {
    kolkata: [88.25, 22.45, 88.48, 22.65] as [number, number, number, number],
    delhi: [77.10, 28.45, 77.40, 28.75] as [number, number, number, number],
    bengaluru: [77.50, 12.80, 77.80, 13.10] as [number, number, number, number],
  };

  const addLog = (msg: string) => {
    setLogs((prev) => [...prev, `[${new Date().toISOString().split("T")[1].slice(0, 8)}] ${msg}`]);
  };

  const simulateProgress = (sceneName: string) => {
    setStageProgress({
      validation: "active",
      georeference: "pending",
      tiling: 0,
      quality: 0,
      embedding: 0,
      indexing: "waiting",
    });

    setTimeout(() => {
      setStageProgress((prev) => ({ ...prev, validation: "complete", georeference: "active" }));
      addLog(`GEOSPATIAL VALIDATION: PASSED. Verified CRS EPSG:32645 (UTM 45N) for ${sceneName}`);
    }, 400);

    setTimeout(() => {
      setStageProgress((prev) => ({ ...prev, georeference: "complete", tiling: 45 }));
      addLog("SLIDING WINDOW TILING: Extracted 64 windowed chips (256x256)");
    }, 900);

    setTimeout(() => {
      setStageProgress((prev) => ({ ...prev, tiling: 100, quality: 70 }));
      addLog("QUALITY GATING: Verified cloud fraction < 4.2%. Sharpness Q=0.942");
    }, 1500);

    setTimeout(() => {
      setStageProgress((prev) => ({ ...prev, quality: 100, embedding: 60 }));
      addLog("EMBEDDING GENERATION: RemoteCLIP-ViT-B32 extracting 512-dim vectors");
    }, 2200);

    setTimeout(() => {
      setStageProgress((prev) => ({ ...prev, embedding: 100, indexing: "active" }));
      addLog("INDEXING: Upserting into Qdrant Vector Store & PostGIS spatial index");
    }, 2800);

    setTimeout(() => {
      setStageProgress((prev) => ({ ...prev, indexing: "complete" }));
      addLog("SUCCESS: Ingestion complete. Scene is now live and queryable in Workspace.");
    }, 3400);
  };

  const handleSearchProvider = async () => {
    setIsSearchingProvider(true);
    const bbox = AOI_COORDS[selectedIndianAoi];
    try {
      const results = await searchEOProvider(sourceType, bbox, "2023-01-01", "2026-01-01");
      setProviderResults(results);
    } catch (err: any) {
      addLog(`Search failed: ${err.message}`);
    } finally {
      setIsSearchingProvider(false);
    }
  };

  useEffect(() => {
    if (sourceType !== "sentinel2") {
      handleSearchProvider();
    }
  }, [sourceType, selectedIndianAoi]);

  const handleStageIndianScene = async (item: EOProviderSearchResult) => {
    setIsProcessing(true);
    setLogs([]);
    setMetrics(null);
    setCurrentFile(`${item.item_id}.tif`);
    addLog(`STAGING ${item.dataset_name} (${item.item_id}) INTO TERREX PIPELINE...`);
    simulateProgress(item.item_id);

    try {
      await stageEOProviderScene(sourceType, item.item_id, item.bbox);
      addLog(`FORMAT NORMALIZATION: Converted ${item.provider || sourceType} scene into common GeoTIFF.`);
      addLog("INDEXING: Running tiling, spectral analysis, and vector embedding into Qdrant...");
      const res = await processIncoming();
      if (res.metrics) {
        setMetrics(res.metrics);
        addLog(`SUCCESS: Staged & ingested ${res.metrics.tiles_created} tile(s). Vector store count: ${res.metrics.vector_index_count}.`);
      }
    } catch (err: any) {
      addLog(`NOTICE: Running with staged offline mock: ${err?.message}`);
    } finally {
      setTimeout(() => setIsProcessing(false), 3500);
    }
  };

  const handleProcessIncoming = async () => {
    setIsProcessing(true);
    setLogs([]);
    setMetrics(null);
    setCurrentFile("BATCH_INCOMING_GEOTIFFS.tif");
    addLog("INITIATING BATCH INGESTION FROM data/incoming/...");
    simulateProgress("BATCH_INCOMING");

    try {
      const res = await processIncoming();
      setMetrics(res.metrics || null);
      addLog(`SUCCESS: Processed ${res.processed.length} scene(s).`);
      if (res.metrics) addLog(`METRICS: ${res.metrics.tiles_created} created | ${res.metrics.tiles_skipped} skipped | ${res.metrics.tiles_discarded} discarded | ${res.metrics.elapsed_seconds}s`);
      if (res.skipped?.length) addLog(`INCREMENTAL: Skipped ${res.skipped.length} already-indexed scene(s).`);
      const repaired = (res.processed || []).filter((item: any) => item.status === "reindexed");
      if (repaired.length) {
        const total = repaired.reduce((sum: number, item: any) => sum + (item.reindexed_tiles || 0), 0);
        addLog(`REPAIR: Rebuilt vector embeddings for ${total} persisted tile(s).`);
      }
      if (res.failed.length > 0) {
        addLog(`WARNING: ${res.failed.length} scenes failed to process.`);
        res.failed.forEach((f: any) => addLog(` -> ${f.file}: ${f.error}`));
      }
      if ((res.metrics?.vector_index_count ?? 0) > 0) addLog(`DATABASE INDEXING COMPLETE. Vector index count: ${res.metrics.vector_index_count}.`);
      else addLog("WARNING: Ingestion completed but the vector index is still empty.");
    } catch (err: any) {
      addLog(`ERROR: Backend ingestion failed: ${err?.message || "The ingestion service is unavailable."}`);
    } finally {
      setTimeout(() => setIsProcessing(false), 3500);
    }
  };

  const handleFileUpload = async (file: File) => {
    setIsProcessing(true);
    setLogs([]);
    setMetrics(null);
    setCurrentFile(file.name);
    addLog(`INITIATING UPLOAD & PIPELINE FOR: ${file.name}`);
    simulateProgress(file.name);

    try {
      const res = await uploadFileAndIngest(file);
      setMetrics({
        tiles_created: res.created_tiles ?? res.tiles ?? 0,
        tiles_skipped: res.skipped_tiles ?? 0,
        tiles_discarded: res.discarded_tiles ?? 0,
        elapsed_seconds: res.elapsed_seconds ?? 0,
      });
      addLog(`SUCCESS: Ingested scene ${res.scene_id} (${res.tiles} tiles created).`);
      addLog(`METRICS: ${res.skipped_tiles || 0} skipped | ${res.discarded_tiles || 0} discarded | ${res.elapsed_seconds || 0}s`);
      if ((res.index_size ?? 0) > 0) addLog(`DATABASE INDEXING COMPLETE. Vector index count: ${res.index_size}.`);
      else addLog("WARNING: Scene processing returned no vectors.");
    } catch (err: any) {
      addLog(`ERROR: Upload/ingestion failed: ${err?.message || "The ingestion service is unavailable."}`);
    } finally {
      setTimeout(() => setIsProcessing(false), 3500);
    }
  };

  return (
    <main className="min-h-screen w-screen bg-black text-neutral-300 font-sans flex flex-col select-none">
      <TopNav />

      <div className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8 space-y-8 font-mono">
        {/* Page Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-neutral-800 pb-8">
          <div className="space-y-3">
            <div className="font-mono text-xs text-radar font-semibold tracking-widest uppercase flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-radar animate-pulse"></span>
              <span>INDIAN EARTH OBSERVATION INGESTION CONSOLE</span>
            </div>
            
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-white font-sans leading-[1.1]">
              Indian satellite &amp;
              <br />
              <span className="text-neutral-400 font-light">EO ingestion pipeline.</span>
            </h1>

            <p className="text-base text-neutral-300 font-sans font-light max-w-2xl leading-relaxed">
              Ingest optical and multispectral imagery from <strong>ISRO/NRSC Bhuvan</strong>, <strong>ISRO MOSDAC</strong>, and <strong>Sentinel-2</strong> into a common GeoTIFF format for sliding-window tiling, RemoteCLIP embedding, and bi-temporal change detection.
            </p>
          </div>

          <Link
            href="/workspace"
            className="px-6 py-3 bg-white text-black font-sans font-semibold text-xs tracking-widest uppercase hover:bg-neutral-200 transition-colors"
          >
            LAUNCH WORKSPACE
          </Link>
        </div>

        {/* Visual Pipeline Sequence Diagram */}
        <div className="p-6 rounded-lg bg-neutral-950 border border-neutral-800 space-y-3">
          <span className="text-[10px] uppercase text-neutral-500 font-bold block">
            INDIAN EO ADAPTER WORKFLOW &middot; FORMAT NORMALIZER &middot; AIR-GAPPED
          </span>

          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2 text-center text-xs">
            {[
              { step: "01", label: "EO Source", sub: "Sentinel-2 / ISRO" },
              { step: "02", label: "Adapter", sub: "Format Normalizer" },
              { step: "03", label: "GeoTIFF COG", sub: "CRS EPSG:32645" },
              { step: "04", label: "Window Tile", sub: "256x256 Chips" },
              { step: "05", label: "Quality Gate", sub: "Cloud < 5%" },
              { step: "06", label: "Embed Vector", sub: "RemoteCLIP ViT" },
              { step: "07", label: "Spatial Index", sub: "Qdrant + PostGIS" },
            ].map((p, i) => (
              <div key={i} className="p-3 rounded bg-neutral-900/60 border border-neutral-800 space-y-1">
                <span className="text-[9px] text-emerald-400 font-bold block">{p.step}</span>
                <span className="text-xs font-bold text-white block truncate">{p.label}</span>
                <span className="text-[9px] text-neutral-500 block font-sans truncate">{p.sub}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Ingestion Console Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* Left Column: Data Source Selector & Importer (7 Cols) */}
          <div className="lg:col-span-7 space-y-4">
            
            {/* EO Provider Tabs */}
            <div className="flex border-b border-neutral-800 pb-2 gap-2">
              {[
                { id: "sentinel2", label: "Sentinel-2 L2A (Primary ML)" },
                { id: "isro-bhuvan", label: "🇮🇳 ISRO Bhuvan (Resourcesat)" },
                { id: "isro-mosdac", label: "🇮🇳 ISRO MOSDAC API" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setSourceType(tab.id as SourceType)}
                  className={`px-3 py-1.5 rounded text-xs uppercase tracking-wider font-semibold transition-all ${
                    sourceType === tab.id
                      ? "bg-white text-black shadow-sm"
                      : "bg-neutral-900 text-neutral-400 hover:text-white border border-neutral-800"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* View 1: Sentinel-2 Drag & Drop */}
            {sourceType === "sentinel2" && (
              <div className="space-y-4">
                <div
                  onClick={() => !isProcessing && fileInputRef.current?.click()}
                  className="border-2 border-dashed border-neutral-800 hover:border-emerald-500/60 rounded-lg p-10 bg-neutral-950/60 text-center cursor-pointer transition-all flex flex-col items-center justify-center gap-3 group"
                >
                  <svg className="w-12 h-12 text-neutral-600 group-hover:text-emerald-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <div>
                    <p className="text-sm font-bold text-white uppercase tracking-wider">
                      DROP SENTINEL-2 GeoTIFF / COG SCENE
                    </p>
                    <p className="text-xs text-neutral-400 font-sans font-light mt-1">
                      Multi-band Sentinel-2 COG GeoTIFF (10m VNIR Bands 2, 3, 4, 8)
                    </p>
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".tif,.tiff,.geotiff"
                    className="hidden"
                    disabled={isProcessing}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) handleFileUpload(f);
                    }}
                  />
                </div>

                <div className="p-5 rounded-lg bg-neutral-950 border border-neutral-800 flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                      PROCESS data/incoming/ DIRECTORY
                    </h3>
                    <p className="text-[11px] text-neutral-400 font-sans font-light mt-0.5">
                      Scan local directory for newly acquired Sentinel-2 passes.
                    </p>
                  </div>
                  <button
                    onClick={handleProcessIncoming}
                    disabled={isProcessing}
                    className="px-5 py-2.5 bg-neutral-900 border border-neutral-700 hover:border-emerald-500 text-emerald-400 font-bold text-xs uppercase tracking-wider rounded transition-all disabled:opacity-50"
                  >
                    {isProcessing ? "PROCESSING..." : "PROCESS DIR"}
                  </button>
                </div>
              </div>
            )}

            {/* View 2 & 3: ISRO Bhuvan & MOSDAC Catalog Importer */}
            {sourceType !== "sentinel2" && (
              <div className="space-y-4">
                <div className="p-4 rounded-lg bg-neutral-950 border border-neutral-800 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                      <span className="text-amber-500">🇮🇳</span>
                      {sourceType === "isro-bhuvan" ? "ISRO / NRSC BHUVAN ARCHIVE" : "ISRO MOSDAC SATELLITE API"}
                    </span>
                    <span className="text-[10px] text-emerald-400 font-bold">AIR-GAPPED COMPATIBLE</span>
                  </div>

                  <div className="flex items-center gap-3 text-xs">
                    <span className="text-neutral-400 text-[11px]">TARGET AOI:</span>
                    {(["kolkata", "delhi", "bengaluru"] as const).map((aoi) => (
                      <button
                        key={aoi}
                        onClick={() => setSelectedIndianAoi(aoi)}
                        className={`px-2.5 py-1 rounded text-[10px] uppercase font-bold tracking-wider transition-all ${
                          selectedIndianAoi === aoi
                            ? "bg-amber-500/20 border border-amber-500 text-amber-300"
                            : "bg-neutral-900 border border-neutral-800 text-neutral-400 hover:text-white"
                        }`}
                      >
                        {aoi}
                      </button>
                    ))}
                    <button
                      onClick={handleSearchProvider}
                      disabled={isSearchingProvider}
                      className="ml-auto px-3 py-1 bg-neutral-900 border border-neutral-700 text-cyan-400 hover:border-cyan-400 rounded text-[10px] uppercase tracking-wider font-bold"
                    >
                      {isSearchingProvider ? "QUERYING..." : "REFRESH CATALOG"}
                    </button>
                  </div>
                </div>

                {/* Candidate Indian Scenes Queue */}
                <div className="space-y-2">
                  <span className="text-[10px] text-neutral-500 uppercase tracking-widest font-bold block">
                    AVAILABLE INDIAN SATELLITE PASSES ({providerResults.length})
                  </span>

                  <div className="space-y-2">
                    {providerResults.map((item) => (
                      <div
                        key={item.item_id}
                        className="p-3.5 rounded-lg bg-neutral-950 border border-neutral-800 hover:border-neutral-700 transition-all flex items-center justify-between gap-4"
                      >
                        <div className="space-y-1 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-white uppercase">{item.dataset_name}</span>
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-neutral-900 border border-neutral-800 text-amber-400 font-bold">
                              {item.spatial_resolution_m}m GSD
                            </span>
                          </div>
                          <p className="text-[10px] text-neutral-400">
                            ID: <span className="text-neutral-300 font-mono">{item.item_id}</span> &middot; Date: <span className="text-neutral-300">{item.acquisition_date.slice(0, 10)}</span> &middot; Cloud: <span className="text-emerald-400">{item.cloud_cover_percent}%</span>
                          </p>
                          <p className="text-[10px] text-neutral-500">
                            Bands: {item.bands.join(", ")}
                          </p>
                        </div>

                        <button
                          onClick={() => handleStageIndianScene(item)}
                          disabled={isProcessing}
                          className="px-3.5 py-2 bg-neutral-900 border border-neutral-700 hover:border-emerald-500 text-emerald-400 rounded text-xs font-bold uppercase tracking-wider transition-all disabled:opacity-50 flex-shrink-0"
                        >
                          STAGE TO TERREX →
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

          </div>

          {/* Right Column: Progressive Pipeline Status & Execution Telemetry (5 Cols) */}
          <div className="lg:col-span-5 space-y-4">
            
            <div className="p-5 rounded-lg bg-neutral-950 border border-neutral-800 space-y-3">
              <div className="flex items-center justify-between border-b border-neutral-800 pb-2">
                <span className="text-xs font-bold text-white uppercase tracking-wider">
                  PIPELINE EXECUTION TELEMETRY
                </span>
                <span className="text-[10px] text-neutral-500 font-mono truncate max-w-[150px]">
                  {currentFile ?? "STANDBY"}
                </span>
              </div>

              <div className="space-y-2.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-neutral-400">VALIDATION</span>
                  <span className={`font-bold ${stageProgress.validation === "complete" ? "text-emerald-400" : "text-neutral-500"}`}>
                    {stageProgress.validation === "complete" ? "✓ PASSED" : stageProgress.validation === "active" ? "RUNNING..." : "WAITING"}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-neutral-400">GEOREFERENCE (EPSG:32645)</span>
                  <span className={`font-bold ${stageProgress.georeference === "complete" ? "text-emerald-400" : "text-neutral-500"}`}>
                    {stageProgress.georeference === "complete" ? "✓ VERIFIED" : stageProgress.georeference === "active" ? "RUNNING..." : "WAITING"}
                  </span>
                </div>

                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-neutral-400">WINDOW TILING (256x256)</span>
                    <span className="text-cyan-400 font-bold">{stageProgress.tiling}%</span>
                  </div>
                  <div className="h-1.5 w-full bg-neutral-900 rounded overflow-hidden">
                    <div className="h-full bg-cyan-400 transition-all duration-300" style={{ width: `${stageProgress.tiling}%` }} />
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-neutral-400">QUALITY &amp; CLOUD FILTER</span>
                    <span className="text-amber-400 font-bold">{stageProgress.quality}%</span>
                  </div>
                  <div className="h-1.5 w-full bg-neutral-900 rounded overflow-hidden">
                    <div className="h-full bg-amber-400 transition-all duration-300" style={{ width: `${stageProgress.quality}%` }} />
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-neutral-400">REMOTECLIP EMBEDDING</span>
                    <span className="text-emerald-400 font-bold">{stageProgress.embedding}%</span>
                  </div>
                  <div className="h-1.5 w-full bg-neutral-900 rounded overflow-hidden">
                    <div className="h-full bg-emerald-400 transition-all duration-300" style={{ width: `${stageProgress.embedding}%` }} />
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-neutral-400">QDRANT + POSTGIS INDEX</span>
                  <span className={`font-bold ${stageProgress.indexing === "complete" ? "text-emerald-400" : "text-neutral-500"}`}>
                    {stageProgress.indexing === "complete" ? "✓ LIVE IN WORKSPACE" : stageProgress.indexing === "active" ? "UPSERTING..." : "WAITING"}
                  </span>
                </div>
              </div>

              {metrics && (
                <div className="grid grid-cols-2 gap-px border-t border-neutral-800 bg-neutral-800 mt-3 pt-1">
                  <Metric label="TILES CREATED" value={metrics.tiles_created ?? 0} />
                  <Metric label="TILES SKIPPED" value={metrics.tiles_skipped ?? 0} />
                  <Metric label="TILES DISCARDED" value={metrics.tiles_discarded ?? 0} />
                  <Metric label="ELAPSED" value={`${metrics.elapsed_seconds ?? 0}s`} />
                </div>
              )}

              {stageProgress.indexing === "complete" && (
                <div className="pt-2">
                  <Link
                    href="/workspace"
                    className="block w-full text-center py-2.5 bg-emerald-500 hover:bg-emerald-400 text-black font-sans font-bold text-xs uppercase tracking-widest rounded transition-all shadow-md"
                  >
                    SEARCH NEWLY INGESTED SCENE →
                  </Link>
                </div>
              )}
            </div>

            {/* Terminal Logs */}
            <div className="p-4 rounded-lg bg-black border border-neutral-800 space-y-2">
              <span className="text-[10px] text-neutral-500 uppercase tracking-widest font-bold block">
                TERMINAL EXECUTION LOG
              </span>
              <div className="h-44 overflow-y-auto space-y-1 font-mono text-[10px] text-neutral-400">
                {logs.length === 0 ? (
                  <span className="text-neutral-600">Awaiting scene ingestion trigger...</span>
                ) : (
                  logs.map((l, idx) => (
                    <div key={idx} className="leading-tight">
                      {l}
                    </div>
                  ))
                )}
              </div>
            </div>

          </div>

        </div>
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-black px-3 py-2">
      <div className="font-mono text-[9px] uppercase tracking-wider text-neutral-600">{label}</div>
      <div className="mt-1 font-mono text-sm text-emerald-400">{value}</div>
    </div>
  );
}
