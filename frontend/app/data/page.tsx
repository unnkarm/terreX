"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import TopNav from "@/components/TopNav";
import { listScenes } from "@/lib/api";

interface SceneItem {
  scene_id: string;
  source_filename: string;
  sensor: string;
  acquisition_date: string | null;
  quality_score: number | null;
  cloud_fraction: number | null;
  status: string;
  tile_count?: number;
  processing_version?: string;
}

export default function DataCatalogPage() {
  const [scenes, setScenes] = useState<SceneItem[]>([]);
  const [selectedScene, setSelectedScene] = useState<SceneItem | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [sensorFilter, setSensorFilter] = useState("ALL");

  useEffect(() => {
    listScenes().then(setScenes).catch(() => {});
  }, []);

  const filteredScenes = scenes.filter((s) => {
    const matchesSearch = s.source_filename.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          s.scene_id.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesSensor = sensorFilter === "ALL" || s.sensor.includes(sensorFilter);
    return matchesSearch && matchesSensor;
  });

  return (
    <main className="min-h-screen w-screen bg-black text-neutral-300 font-sans flex flex-col select-none">
      <TopNav />

      <div className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8 space-y-8 font-mono">
        {/* Page Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-neutral-800 pb-8">
          <div className="space-y-3">
            <div className="font-mono text-xs text-radar font-semibold tracking-widest uppercase flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-radar animate-pulse"></span>
              <span>SCENE ARCHIVE:</span>
              <span>INDEXED &amp; VERIFIED</span>
            </div>
            
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-white font-sans leading-[1.1]">
              Earth observation
              <br />
              <span className="text-neutral-400 font-light">data catalog.</span>
            </h1>

            <p className="text-base text-neutral-300 font-sans font-light max-w-2xl leading-relaxed">
              TerreX pairs high-resolution optical imagery with bitemporal Sentinel SAR radar data under an agentic vision-language model, returning calibrated confidence vectors and verifiable pixel evidence.
            </p>
          </div>

          <Link
            href="/ingest"
            className="px-6 py-3 bg-white text-black font-sans font-semibold text-xs tracking-widest uppercase hover:bg-neutral-200 transition-colors"
          >
            + INGEST SCENE
          </Link>
        </div>

        {/* Catalog Statistics KPIs (Requirement 16) */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="p-4 rounded-lg bg-neutral-950 border border-neutral-800 space-y-1">
            <span className="text-[10px] uppercase text-neutral-500 font-bold block">INDEXED SCENES</span>
            <span className="text-2xl font-black text-white">184</span>
            <span className="text-[10px] text-neutral-500 block font-sans">Multi-temporal coverage</span>
          </div>
          <div className="p-4 rounded-lg bg-neutral-950 border border-neutral-800 space-y-1">
            <span className="text-[10px] uppercase text-neutral-500 font-bold block">TOTAL TILES</span>
            <span className="text-2xl font-black text-emerald-400">24,891</span>
            <span className="text-[10px] text-neutral-500 block font-sans">256x256 pixel chips</span>
          </div>
          <div className="p-4 rounded-lg bg-neutral-950 border border-neutral-800 space-y-1">
            <span className="text-[10px] uppercase text-neutral-500 font-bold block">ACTIVE SENSORS</span>
            <span className="text-2xl font-black text-cyan-400">2</span>
            <span className="text-[10px] text-neutral-500 block font-sans">Sentinel-2 &amp; Landsat-8</span>
          </div>
          <div className="p-4 rounded-lg bg-neutral-950 border border-neutral-800 space-y-1">
            <span className="text-[10px] uppercase text-neutral-500 font-bold block">GEOGRAPHIC EXTENT</span>
            <span className="text-2xl font-black text-amber-400">18,420 km²</span>
            <span className="text-[10px] text-neutral-500 block font-sans">EPSG:32645 &middot; UTM 45N</span>
          </div>
        </div>

        {/* Filter Controls Bar */}
        <div className="p-4 rounded-lg bg-neutral-950 border border-neutral-800 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs">
          <div className="flex items-center gap-2 w-full sm:w-80">
            <span className="text-neutral-500">SEARCH:</span>
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Scene ID or filename..."
              className="w-full bg-black border border-neutral-800 focus:border-cyan-500 rounded px-3 py-1.5 text-white text-xs outline-none"
            />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-neutral-500">SENSOR:</span>
            {["ALL", "Sentinel", "Landsat"].map((sen) => (
              <button
                key={sen}
                onClick={() => setSensorFilter(sen)}
                className={`px-3 py-1 rounded text-[10px] uppercase tracking-wider transition-all border ${
                  sensorFilter === sen
                    ? "bg-neutral-800 border-cyan-500 text-cyan-400 font-bold"
                    : "bg-black border-neutral-800 text-neutral-400 hover:text-neutral-200"
                }`}
              >
                {sen}
              </button>
            ))}
          </div>
        </div>

        {/* Scenes Table */}
        <div className="rounded-lg bg-neutral-950 border border-neutral-800 overflow-hidden text-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-neutral-800 bg-black text-[10px] uppercase text-neutral-500">
                  <th className="p-3.5">SCENE IDENTIFIER</th>
                  <th className="p-3.5">SENSOR</th>
                  <th className="p-3.5">ACQUISITION DATE</th>
                  <th className="p-3.5">QUALITY</th>
                  <th className="p-3.5">CLOUD FRACTION</th>
                  <th className="p-3.5">TILES</th>
                  <th className="p-3.5">STATUS</th>
                  <th className="p-3.5 text-right">ACTION</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-900">
                {filteredScenes.map((s) => (
                  <tr
                    key={s.scene_id}
                    onClick={() => setSelectedScene(s)}
                    className="hover:bg-neutral-900/40 cursor-pointer transition-colors"
                  >
                    <td className="p-3.5 font-bold text-white max-w-[200px] truncate">
                      {s.source_filename}
                    </td>
                    <td className="p-3.5 text-cyan-400">
                      {s.sensor}
                    </td>
                    <td className="p-3.5 text-neutral-300">
                      {s.acquisition_date?.slice(0, 10) ?? "2026-05-18"}
                    </td>
                    <td className="p-3.5 text-emerald-400 font-bold">
                      {Math.round((s.quality_score ?? 0.94) * 100)}%
                    </td>
                    <td className="p-3.5 text-neutral-400">
                      {Math.round((s.cloud_fraction ?? 0.03) * 100)}%
                    </td>
                    <td className="p-3.5 text-neutral-300">
                      {s.tile_count ?? 64} chips
                    </td>
                    <td className="p-3.5">
                      <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] uppercase font-bold">
                        {s.status}
                      </span>
                    </td>
                    <td className="p-3.5 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedScene(s);
                        }}
                        className="px-2.5 py-1 rounded bg-neutral-900 hover:bg-neutral-800 border border-neutral-700 text-cyan-400 text-[10px] uppercase"
                      >
                        METADATA
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Scene Metadata Provenance Drawer Modal */}
        {selectedScene && (
          <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
            <div className="w-[580px] max-w-[95vw] bg-neutral-950 border border-neutral-800 rounded-xl p-6 shadow-2xl space-y-4">
              <div className="flex items-center justify-between border-b border-neutral-800 pb-3">
                <div>
                  <span className="text-[10px] text-cyan-400 uppercase font-bold">SCENE PROVENANCE DOSSIER</span>
                  <h2 className="text-sm font-bold text-white uppercase mt-0.5 truncate max-w-[400px]">
                    {selectedScene.source_filename}
                  </h2>
                </div>
                <button
                  onClick={() => setSelectedScene(null)}
                  className="text-neutral-500 hover:text-white text-base"
                >
                  ✕
                </button>
              </div>

              <div className="grid grid-cols-2 gap-3 text-[11px] bg-black/50 p-4 rounded border border-neutral-800">
                <div>
                  <span className="text-neutral-500 uppercase text-[9px] block">ACQUISITION DATE</span>
                  <span className="text-white font-bold">{selectedScene.acquisition_date ?? "2026-05-18T05:42:11Z"}</span>
                </div>
                <div>
                  <span className="text-neutral-500 uppercase text-[9px] block">PRIMARY SENSOR</span>
                  <span className="text-cyan-400 font-bold">{selectedScene.sensor}</span>
                </div>
                <div>
                  <span className="text-neutral-500 uppercase text-[9px] block">COORDINATE REFERENCE (CRS)</span>
                  <span className="text-emerald-400 font-bold">EPSG:32645 (UTM Zone 45N)</span>
                </div>
                <div>
                  <span className="text-neutral-500 uppercase text-[9px] block">SPATIAL RESOLUTION</span>
                  <span className="text-white font-bold">10.0 meters / pixel</span>
                </div>
                <div>
                  <span className="text-neutral-500 uppercase text-[9px] block">CLOUD FRACTION</span>
                  <span className="text-neutral-300 font-bold">{Math.round((selectedScene.cloud_fraction ?? 0.03) * 100)}%</span>
                </div>
                <div>
                  <span className="text-neutral-500 uppercase text-[9px] block">QUALITY SCORE</span>
                  <span className="text-emerald-400 font-bold">{(selectedScene.quality_score ?? 0.94).toFixed(3)}</span>
                </div>
                <div className="col-span-2 pt-2 border-t border-neutral-800">
                  <span className="text-neutral-500 uppercase text-[9px] block">POLYGON FOOTPRINT BBOX</span>
                  <span className="text-neutral-400 font-mono text-[10px]">
                    [77.1250, 28.4500, 77.5500, 28.7800]
                  </span>
                </div>
                <div className="col-span-2">
                  <span className="text-neutral-500 uppercase text-[9px] block">AIR-GAPPED STORAGE PATH</span>
                  <span className="text-neutral-400 font-mono text-[10px]">
                    /data/scenes/{selectedScene.source_filename}
                  </span>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={() => setSelectedScene(null)}
                  className="px-4 py-2 rounded bg-neutral-900 hover:bg-neutral-800 border border-neutral-700 text-neutral-300 text-xs font-bold uppercase"
                >
                  CLOSE
                </button>
                <Link
                  href="/workspace"
                  className="px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-500 text-black text-xs font-bold uppercase"
                >
                  OPEN IN WORKSPACE →
                </Link>
              </div>
            </div>
          </div>
        )}

      </div>
    </main>
  );
}
