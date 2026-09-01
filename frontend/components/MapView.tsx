"use client";

import { useEffect, useRef } from "react";
import maplibregl, { Map as MapLibreMap, Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { SearchResult } from "@/lib/api";

interface Props {
  results: SearchResult[];
  selectedTileId: string | null;
  onSelect: (r: SearchResult) => void;
  center: [number, number];
}

// Offline map style: a simple solid/graticule style with no external tile
// server dependency. For a real deployment, stage a local raster/vector
// tile server (e.g. TileServer-GL with an offline MBTiles extract) and
// point `sources.basemap.tiles` at it — see README "Staging map data".
const OFFLINE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#0b1220" } },
  ],
};

export default function MapView({ results, selectedTileId, onSelect, center }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<Marker[]>([]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    mapRef.current = new maplibregl.Map({
      container: containerRef.current,
      style: OFFLINE_STYLE,
      center,
      zoom: 12,
      attributionControl: false,
    });
    mapRef.current.addControl(new maplibregl.NavigationControl(), "top-right");
    mapRef.current.addControl(
      new maplibregl.AttributionControl({ compact: true, customAttribution: "TerreX — offline demo basemap" })
    );
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    results.forEach((r) => {
      const el = document.createElement("div");
      const isSelected = r.tile_id === selectedTileId;
      el.style.width = isSelected ? "16px" : "10px";
      el.style.height = isSelected ? "16px" : "10px";
      el.style.borderRadius = "50%";
      el.style.cursor = "pointer";
      el.style.border = "2px solid #0b1220";
      el.style.background = isSelected
        ? "#22d3ee"
        : r.final_score > 0.7
        ? "#22c55e"
        : r.final_score > 0.4
        ? "#f59e0b"
        : "#ef4444";
      el.title = `${r.sensor ?? "unknown"} · score ${r.final_score.toFixed(2)}`;
      el.addEventListener("click", () => onSelect(r));

      const marker = new maplibregl.Marker({ element: el }).setLngLat([r.lon, r.lat]).addTo(map);
      markersRef.current.push(marker);
    });

    if (results.length > 0) {
      const bounds = new maplibregl.LngLatBounds();
      results.forEach((r) => bounds.extend([r.lon, r.lat]));
      map.fitBounds(bounds, { padding: 60, maxZoom: 15, duration: 500 });
    }
  }, [results, selectedTileId]);

  return <div ref={containerRef} className="w-full h-full" />;
}
