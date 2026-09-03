"use client";

import React, { useState } from "react";
import { SearchResult, SimilarCluster, getDemoSimilarClusters } from "@/lib/api";

interface DiscoveryPanelProps {
  selectedSite: SearchResult | null;
  onSelectCluster?: (cluster: SimilarCluster) => void;
  onSelectSite?: (site: SearchResult) => void;
}

export default function DiscoveryPanel({
  selectedSite,
  onSelectCluster,
  onSelectSite,
}: DiscoveryPanelProps) {
  const [clusters, setClusters] = useState<SimilarCluster[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [activeClusterId, setActiveClusterId] = useState<string | null>(null);

  const runDiscovery = () => {
    setIsScanning(true);
    setTimeout(() => {
      const centerLon = selectedSite?.lon ?? 77.25;
      const centerLat = selectedSite?.lat ?? 28.55;
      const discovered = getDemoSimilarClusters(centerLon, centerLat);
      setClusters(discovered);
      setActiveClusterId(discovered[0]?.id ?? null);
      if (discovered[0] && onSelectCluster) onSelectCluster(discovered[0]);
      setIsScanning(false);
    }, 600);
  };

  const activeCluster = clusters.find((c) => c.id === activeClusterId);

  return (
    <div className="flex flex-col h-full bg-neutral-950 text-neutral-300 font-mono text-xs overflow-y-auto p-4 space-y-4">
      {/* Header */}
      <div className="border-b border-neutral-800 pb-2.5">
        <h2 className="text-sm font-bold tracking-tight text-white font-sans uppercase flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
          Discovery &amp; <span className="text-neutral-400 font-light">Clustering</span>
        </h2>
        <p className="text-[11px] text-neutral-300 font-sans font-light mt-0.5">
          Unsupervised geospatial pattern discovery &amp; spectral similarity grouping.
        </p>
      </div>

      {/* Target Reference */}
      <div className="p-3.5 bg-neutral-900/60 rounded border border-neutral-800 space-y-2.5">
        <span className="text-[9px] font-mono uppercase tracking-widest text-neutral-500 font-semibold block">
          REFERENCE SEED TARGET
        </span>
        {selectedSite ? (
          <div>
            <p className="font-sans font-bold text-white text-xs truncate tracking-tight">
              {selectedSite.location_name ?? `Target #${selectedSite.tile_id.slice(0, 8)}`}
            </p>
            <p className="text-[11px] text-neutral-400 font-mono mt-0.5">
              {selectedSite.lat.toFixed(4)}°N, {selectedSite.lon.toFixed(4)}°E &middot; {selectedSite.sensor ?? "Sentinel-2"}
            </p>
          </div>
        ) : (
          <p className="text-[11px] text-neutral-500 font-sans font-light italic">
            Select a target from search results or map to seed discovery.
          </p>
        )}

        <button
          onClick={runDiscovery}
          disabled={isScanning}
          className="w-full py-2.5 bg-white hover:bg-neutral-200 text-black font-sans font-semibold text-xs uppercase tracking-widest rounded transition-all disabled:opacity-50 shadow-md"
        >
          {isScanning ? "CLUSTERING HIGH-DIMENSIONAL EMBEDDINGS..." : "DISCOVER SIMILAR LOCATIONS"}
        </button>
      </div>

      {/* Discovery Pipeline Funnel Results */}
      {clusters.length > 0 && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-1.5 text-center">
            <div className="p-2 rounded bg-neutral-900 border border-neutral-800">
              <span className="text-[9px] text-neutral-500 block uppercase">Candidates</span>
              <span className="text-xs font-bold text-neutral-200">127</span>
            </div>
            <div className="p-2 rounded bg-neutral-900 border border-neutral-800">
              <span className="text-[9px] text-neutral-500 block uppercase">High Sim.</span>
              <span className="text-xs font-bold text-cyan-400">34</span>
            </div>
            <div className="p-2 rounded bg-cyan-950/30 border border-cyan-800/40">
              <span className="text-[9px] text-cyan-400 block uppercase">Clusters</span>
              <span className="text-xs font-bold text-white">{clusters.length}</span>
            </div>
          </div>

          {/* Clusters List */}
          <div className="space-y-2">
            <span className="text-[9px] uppercase tracking-widest text-neutral-500 font-bold">
              IDENTIFIED CLUSTERS
            </span>
            <div className="space-y-1.5">
              {clusters.map((cl) => {
                const isActive = cl.id === activeClusterId;
                return (
                  <button
                    key={cl.id}
                    onClick={() => {
                      setActiveClusterId(cl.id);
                      if (onSelectCluster) onSelectCluster(cl);
                    }}
                    className={`w-full text-left p-2.5 rounded border transition-all ${
                      isActive
                        ? "bg-neutral-900 border-cyan-500 text-white shadow-sm"
                        : "bg-black/50 border-neutral-800/80 text-neutral-400 hover:border-neutral-700"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-[11px] text-neutral-200">{cl.name}</span>
                      <span className="text-[9px] px-1.5 py-0.5 rounded bg-neutral-800 text-cyan-400 font-bold">
                        {cl.count} sites
                      </span>
                    </div>
                    <div className="flex items-center gap-3 mt-1.5 text-[10px] text-neutral-500 font-sans">
                      <span>Type: <strong className="text-neutral-300">{cl.dominantType}</strong></span>
                      <span>Confidence: <strong className="text-emerald-400">{Math.round(cl.confidence * 100)}%</strong></span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Active Cluster Details */}
          {activeCluster && (
            <div className="p-3 bg-neutral-900/40 rounded border border-neutral-800 space-y-2 font-sans">
              <span className="text-[9px] font-mono uppercase tracking-widest text-cyan-400 font-bold block">
                {activeCluster.name} &mdash; CHARACTERISTICS
              </span>
              <ul className="space-y-1 text-[11px] text-neutral-300">
                {activeCluster.characteristics.map((char, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <span className="text-cyan-400 font-bold">&bull;</span>
                    <span>{char}</span>
                  </li>
                ))}
              </ul>

              {activeCluster.sites.length > 0 && (
                <div className="pt-2 space-y-1 font-mono text-[10px]">
                  <span className="text-neutral-500 uppercase tracking-wider block">
                    SAMPLE IDENTIFIED SITES
                  </span>
                  {activeCluster.sites.map((site) => (
                    <div
                      key={site.tile_id}
                      onClick={() => onSelectSite && onSelectSite(site)}
                      className="p-1.5 rounded bg-black/60 border border-neutral-800 hover:border-neutral-700 cursor-pointer flex items-center justify-between"
                    >
                      <span className="text-neutral-300 truncate">{site.classification_label}</span>
                      <span className="text-emerald-400 font-bold">{(site.similarity_score * 100).toFixed(0)}%</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
