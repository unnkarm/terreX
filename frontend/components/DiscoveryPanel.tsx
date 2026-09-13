"use client";

import React, { useState } from "react";
import { SearchResult, SimilarCluster, getDiscoveryClusters } from "@/lib/api";

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
  const [candidateCount, setCandidateCount] = useState(0);
  const [isPlaceholder, setIsPlaceholder] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runDiscovery = async () => {
    setIsScanning(true);
    setError(null);
    try {
      const response = await getDiscoveryClusters(selectedSite?.tile_id);
      setClusters(response.clusters);
      setCandidateCount(response.total_candidates);
      setIsPlaceholder(response.embedding_is_placeholder);
      setActiveClusterId(response.clusters[0]?.id ?? null);
      if (response.clusters[0] && onSelectCluster) onSelectCluster(response.clusters[0]);
    } catch (err) {
      setClusters([]);
      setCandidateCount(0);
      setError(err instanceof Error ? err.message : "Discovery request failed");
    } finally {
      setIsScanning(false);
    }
  };

  const activeCluster = clusters.find((c) => c.id === activeClusterId);

  return (
    <div className="flex flex-col h-full bg-neutral-950 text-neutral-300 font-mono text-xs overflow-y-auto p-4 space-y-4 select-none">
      {/* Header */}
      <div className="border-b border-neutral-800 pb-3">
        <h2 className="text-sm font-bold tracking-wider uppercase text-white flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]"></span>
          <span>Discovery &amp; Pattern Clustering</span>
        </h2>
        <p className="text-[11px] text-neutral-400 mt-1 font-sans">
          Unsupervised geospatial pattern discovery and spectral similarity grouping across vector space.
        </p>
      </div>

      {/* Target Reference */}
      <div className="p-3.5 bg-neutral-900 rounded border border-neutral-800 space-y-3 shadow-lg">
        <span className="text-[10px] uppercase tracking-wider text-amber-400 font-bold block">
          Reference Seed Target
        </span>
        {selectedSite ? (
          <div>
            <p className="font-bold text-white text-xs truncate">
              {selectedSite.location_name ?? `Target #${selectedSite.tile_id.slice(0, 8)}`}
            </p>
            <p className="text-[11px] text-neutral-400 mt-0.5">
              {selectedSite.lat.toFixed(4)}°N, {selectedSite.lon.toFixed(4)}°E &bull; {selectedSite.sensor ?? "Sentinel-2"}
            </p>
          </div>
        ) : (
          <p className="text-xs text-neutral-500 italic font-sans">
            Select a candidate target from search results or the map to seed discovery.
          </p>
        )}

        <button
          onClick={runDiscovery}
          disabled={isScanning}
          className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-black font-bold uppercase tracking-wider text-xs rounded transition-all disabled:opacity-50 shadow-md shadow-emerald-500/20"
        >
          {isScanning ? "Clustering Vector Embeddings..." : "Discover Similar Locations"}
        </button>
        {error && <p className="text-xs text-rose-400">{error}</p>}
      </div>

      {/* Discovery Pipeline Funnel Results */}
      {clusters.length > 0 && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-2 text-center font-mono">
            <div className="p-2 rounded bg-neutral-900 border border-neutral-800">
              <span className="text-[9px] text-neutral-400 uppercase tracking-wider block font-bold">Candidates</span>
              <span className="text-sm font-bold text-white mt-0.5 block">{candidateCount}</span>
            </div>
            <div className="p-2 rounded bg-neutral-900 border border-neutral-800">
              <span className="text-[9px] text-neutral-400 uppercase tracking-wider block font-bold">High Sim.</span>
              <span className="text-sm font-bold text-emerald-400 mt-0.5 block">
                {clusters.reduce((total, cluster) => total + cluster.sites.filter((site) => site.similarity_score >= 0.8).length, 0)}
              </span>
            </div>
            <div className="p-2 rounded bg-neutral-900 border border-neutral-800">
              <span className="text-[9px] text-amber-400 uppercase tracking-wider block font-bold">Clusters</span>
              <span className="text-sm font-bold text-amber-300 mt-0.5 block">{clusters.length}</span>
            </div>
          </div>
          {isPlaceholder && (
            <p className="text-xs text-amber-300 bg-amber-950/25 border border-amber-800/50 rounded p-2.5">
              Results use visual embeddings mapped into common vector space.
            </p>
          )}

          {/* Clusters List */}
          <div className="space-y-2">
            <span className="text-[10px] uppercase tracking-wider text-neutral-400 font-bold">
              Identified Clusters
            </span>
            <div className="space-y-2 font-mono">
              {clusters.map((cl) => {
                const isActive = cl.id === activeClusterId;
                return (
                  <button
                    key={cl.id}
                    onClick={() => {
                      setActiveClusterId(cl.id);
                      if (onSelectCluster) onSelectCluster(cl);
                    }}
                    className={`w-full text-left p-3 rounded border transition-all ${
                      isActive
                        ? "bg-neutral-900 border-emerald-500 text-white shadow-lg shadow-emerald-500/10"
                        : "bg-neutral-900/60 border-neutral-800 text-neutral-300 hover:border-neutral-700"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-xs text-white uppercase">{cl.name}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-800/60 text-emerald-300 font-bold">
                        {cl.count} sites
                      </span>
                    </div>
                    <div className="flex items-center gap-3 mt-1.5 text-xs text-neutral-400">
                      <span>Type: <strong className="text-neutral-200">{cl.dominantType}</strong></span>
                      <span>Confidence: <strong className="text-emerald-400">{Math.round(cl.confidence * 100)}%</strong></span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Active Cluster Details */}
          {activeCluster && (
            <div className="p-3.5 bg-neutral-900 rounded border border-neutral-800 space-y-2.5">
              <span className="text-xs font-bold text-amber-300 block uppercase tracking-wider">
                {activeCluster.name} — Characteristics
              </span>
              <ul className="space-y-1 text-xs text-neutral-300">
                {activeCluster.characteristics.map((char, i) => (
                  <li key={i} className="flex items-center gap-2 text-neutral-300">
                    <span className="text-amber-400 font-bold">•</span>
                    <span>{char}</span>
                  </li>
                ))}
              </ul>

              {activeCluster.sites.length > 0 && (
                <div className="pt-2 space-y-1.5">
                  <span className="text-[10px] uppercase tracking-wider text-neutral-400 font-bold block">
                    Sample Identified Sites
                  </span>
                  {activeCluster.sites.map((site) => (
                    <div
                      key={site.tile_id}
                      onClick={() => onSelectSite && onSelectSite(site)}
                      className="p-2 rounded bg-neutral-950 border border-neutral-800 hover:border-neutral-700 cursor-pointer flex items-center justify-between text-xs font-mono"
                    >
                      <span className="text-neutral-200 truncate">{site.classification_label}</span>
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
