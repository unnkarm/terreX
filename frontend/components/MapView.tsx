"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl, { Map as MapLibreMap, Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { SearchResult } from "@/lib/api";

interface Props {
  results: SearchResult[];
  selectedTileId: string | null;
  onSelect: (r: SearchResult) => void;
  center: [number, number];
}

type BasemapType = "satellite" | "dark" | "osm" | "offline";

const BASEMAP_STYLES: Record<BasemapType, maplibregl.StyleSpecification> = {
  satellite: {
    version: 8,
    sources: {
      "esri-satellite": {
        type: "raster",
        tiles: [
          "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        ],
        tileSize: 256,
        attribution: "© Esri, Maxar, Earthstar Geographics",
      },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "#0b1220" } },
      { id: "satellite-layer", type: "raster", source: "esri-satellite", minzoom: 0, maxzoom: 19 },
    ],
  },
  dark: {
    version: 8,
    sources: {
      "carto-dark": {
        type: "raster",
        tiles: [
          "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
          "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        ],
        tileSize: 256,
        attribution: "© CARTO, © OpenStreetMap",
      },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "#0b1220" } },
      { id: "dark-layer", type: "raster", source: "carto-dark", minzoom: 0, maxzoom: 19 },
    ],
  },
  osm: {
    version: 8,
    sources: {
      "osm-tiles": {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "© OpenStreetMap contributors",
      },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "#0b1220" } },
      { id: "osm-layer", type: "raster", source: "osm-tiles", minzoom: 0, maxzoom: 19 },
    ],
  },
  offline: {
    version: 8,
    sources: {},
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "#0b1220" } },
    ],
  },
};

export default function MapView({ results, selectedTileId, onSelect, center }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<Marker[]>([]);
  const [basemap, setBasemap] = useState<BasemapType>("satellite");

  // Initialize Map
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASEMAP_STYLES[basemap],
      center,
      zoom: 12,
      attributionControl: false,
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Update style when basemap changes
  const switchBasemap = (type: BasemapType) => {
    setBasemap(type);
    if (mapRef.current) {
      mapRef.current.setStyle(BASEMAP_STYLES[type]);
    }
  };

  // Re-render markers and fit bounds
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    results.forEach((r) => {
      const isSelected = r.tile_id === selectedTileId;
      const el = document.createElement("div");
      el.className = "group relative flex items-center justify-center transition-transform hover:scale-125";
      el.style.width = isSelected ? "24px" : "18px";
      el.style.height = isSelected ? "24px" : "18px";
      el.style.cursor = "pointer";

      // Outer pulse halo for selected item
      if (isSelected) {
        const pulse = document.createElement("span");
        pulse.className = "absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-60";
        el.appendChild(pulse);
      }

      // Inner tactical dot
      const dot = document.createElement("span");
      dot.className = `relative inline-flex rounded-full border-2 border-black ${
        isSelected
          ? "h-4 w-4 bg-cyan-400 shadow-[0_0_12px_#22d3ee]"
          : r.final_score > 0.6
          ? "h-3.5 w-3.5 bg-emerald-400 shadow-[0_0_8px_#34d399]"
          : r.final_score > 0.4
          ? "h-3 w-3 bg-amber-400"
          : "h-2.5 w-2.5 bg-neutral-400"
      }`;
      el.appendChild(dot);

      el.title = `${r.sensor ?? "Sentinel-2"} | Score: ${(r.final_score * 100).toFixed(0)}%`;
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        onSelect(r);
      });

      const marker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([r.lon, r.lat])
        .addTo(map);

      markersRef.current.push(marker);
    });

    // Zoom to selected or fit all results
    if (selectedTileId) {
      const selected = results.find((r) => r.tile_id === selectedTileId);
      if (selected) {
        map.flyTo({ center: [selected.lon, selected.lat], zoom: Math.max(map.getZoom(), 13), duration: 600 });
      }
    } else if (results.length > 0) {
      const bounds = new maplibregl.LngLatBounds();
      results.forEach((r) => bounds.extend([r.lon, r.lat]));
      map.fitBounds(bounds, { padding: 80, maxZoom: 15, duration: 600 });
    }
  }, [results, selectedTileId]);

  return (
    <div className="relative w-full h-full">
      <div ref={containerRef} className="w-full h-full" />

      {/* Basemap Switcher Tactical Overlay */}
      <div className="absolute top-3 left-3 z-10 flex items-center gap-1 p-1 rounded-lg bg-neutral-950/85 backdrop-blur border border-neutral-800 shadow-xl text-[11px] font-mono">
        <button
          onClick={() => switchBasemap("satellite")}
          className={`px-2 py-1 rounded transition ${
            basemap === "satellite"
              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-semibold"
              : "text-neutral-400 hover:text-neutral-200"
          }`}
          title="High-resolution global satellite imagery"
        >
          🛰️ Satellite
        </button>
        <button
          onClick={() => switchBasemap("dark")}
          className={`px-2 py-1 rounded transition ${
            basemap === "dark"
              ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-semibold"
              : "text-neutral-400 hover:text-neutral-200"
          }`}
          title="CARTO dark tactical basemap"
        >
          🌑 Tactical Dark
        </button>
        <button
          onClick={() => switchBasemap("osm")}
          className={`px-2 py-1 rounded transition ${
            basemap === "osm"
              ? "bg-blue-500/20 text-blue-300 border border-blue-500/40 font-semibold"
              : "text-neutral-400 hover:text-neutral-200"
          }`}
          title="OpenStreetMap street and boundary map"
        >
          🗺️ Streets
        </button>
        <button
          onClick={() => switchBasemap("offline")}
          className={`px-2 py-1 rounded transition ${
            basemap === "offline"
              ? "bg-neutral-700 text-white font-semibold"
              : "text-neutral-400 hover:text-neutral-200"
          }`}
          title="Strict offline air-gapped grid"
        >
          🔒 Offline Grid
        </button>
      </div>
    </div>
  );
}
