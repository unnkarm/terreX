"use client";
"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl, { Map as MapLibreMap, Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { SearchResult, SimilarCluster } from "@/lib/api";

interface Props {
  results: SearchResult[];
  selectedTileId: string | null;
  onSelect: (r: SearchResult) => void;
  center: [number, number];
  isDrawingAoi?: boolean;
  onAoiDrawn?: (bbox: [number, number, number, number]) => void;
  onAoiPolygonDrawn?: (polygonGeoJson: { type: "Polygon"; coordinates: number[][][] }) => void;
  activeCluster?: SimilarCluster | null;
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
      { id: "bg", type: "background", paint: { "background-color": "#050505" } },
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
      { id: "bg", type: "background", paint: { "background-color": "#050505" } },
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
      { id: "bg", type: "background", paint: { "background-color": "#050505" } },
      { id: "osm-layer", type: "raster", source: "osm-tiles", minzoom: 0, maxzoom: 19 },
    ],
  },
  offline: {
    version: 8,
    sources: {},
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "#050505" } },
    ],
  },
};

export default function MapView({
  results,
  selectedTileId,
  onSelect,
  center,
  isDrawingAoi = false,
  onAoiDrawn,
  onAoiPolygonDrawn,
  activeCluster,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<Marker[]>([]);
  const clusterMarkersRef = useRef<Marker[]>([]);
  const polygonMarkersRef = useRef<Marker[]>([]);
  const [basemap, setBasemap] = useState<BasemapType>("satellite");
  const [drawMode, setDrawMode] = useState<"none" | "box" | "polygon">("none");
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [dragCurrent, setDragCurrent] = useState<{ x: number; y: number } | null>(null);
  const [polygonPts, setPolygonPts] = useState<[number, number][]>([]);
  const [activePolygon, setActivePolygon] = useState<[number, number][] | null>(null);

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

    map.on("load", () => {
      // Setup GeoJSON Polygon AOI layer
      if (!map.getSource("aoi-polygon-source")) {
        map.addSource("aoi-polygon-source", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });

        map.addLayer({
          id: "aoi-polygon-fill",
          type: "fill",
          source: "aoi-polygon-source",
          paint: {
            "fill-color": "#06b6d4",
            "fill-opacity": 0.22,
          },
        });

        map.addLayer({
          id: "aoi-polygon-stroke",
          type: "line",
          source: "aoi-polygon-source",
          paint: {
            "line-color": "#22d3ee",
            "line-width": 2.5,
            "line-dasharray": [2, 1],
          },
        });
      }
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // MapLibre needs an explicit resize when the surrounding side panels open
  // or close; observing the container also covers the sidebar transition.
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver(() => mapRef.current?.resize());
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  // Switch basemap
  const switchBasemap = (type: BasemapType) => {
    setBasemap(type);
    if (mapRef.current) {
      mapRef.current.setStyle(BASEMAP_STYLES[type]);
    }
  };

  // Smoothly fly camera whenever center coordinates change (search, AOI button, tile click)
  const centerLon = center[0];
  const centerLat = center[1];
  useEffect(() => {
    if (!mapRef.current) return;
    mapRef.current.flyTo({
      center: [centerLon, centerLat],
      zoom: Math.max(mapRef.current.getZoom(), 13),
      duration: 800,
    });
  }, [centerLon, centerLat]);

  // Zoom / Pan helpers
  const handleZoomIn = () => mapRef.current?.zoomIn();
  const handleZoomOut = () => mapRef.current?.zoomOut();
  const handleResetCenter = () => {
    mapRef.current?.flyTo({ center, zoom: 12, duration: 600 });
  };

  const setMode = (mode: "none" | "box" | "polygon") => {
    const next = drawMode === mode ? "none" : mode;
    setDrawMode(next);
    if (next !== "polygon") {
      setPolygonPts([]);
    }
    if (mapRef.current) {
      if (next === "box") {
        mapRef.current.dragPan.disable();
      } else {
        mapRef.current.dragPan.enable();
      }
    }
  };

  // Drag box handlers for AOI creation
  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (drawMode !== "box" || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const pt = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    setDragStart(pt);
    setDragCurrent(pt);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!dragStart || drawMode !== "box" || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    setDragCurrent({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  const handleMouseUp = () => {
    if (!dragStart || !dragCurrent || drawMode !== "box" || !mapRef.current) {
      setDragStart(null);
      setDragCurrent(null);
      return;
    }

    const map = mapRef.current;
    const sw = map.unproject([Math.min(dragStart.x, dragCurrent.x), Math.max(dragStart.y, dragCurrent.y)]);
    const ne = map.unproject([Math.max(dragStart.x, dragCurrent.x), Math.min(dragStart.y, dragCurrent.y)]);

    const bbox: [number, number, number, number] = [sw.lng, sw.lat, ne.lng, ne.lat];
    if (onAoiDrawn) {
      onAoiDrawn(bbox);
    }

    setDragStart(null);
    setDragCurrent(null);
    setDrawMode("none");
    map.dragPan.enable();
  };

  // Polygon click handler on map
  const handleMapClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (drawMode !== "polygon" || !mapRef.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;
    const lngLat = mapRef.current.unproject([clickX, clickY]);
    const nextPts: [number, number][] = [...polygonPts, [lngLat.lng, lngLat.lat]];
    setPolygonPts(nextPts);
  };

  const completePolygon = () => {
    if (polygonPts.length < 3) return;
    const closed = [...polygonPts, polygonPts[0]];
    setActivePolygon(closed);
    const geoJsonPoly = {
      type: "Polygon" as const,
      coordinates: [closed],
    };

    // Update GeoJSON layer on map
    if (mapRef.current && mapRef.current.getSource("aoi-polygon-source")) {
      const src = mapRef.current.getSource("aoi-polygon-source") as maplibregl.GeoJSONSource;
      src.setData({
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            geometry: geoJsonPoly,
            properties: { name: "Active AOI Polygon" },
          },
        ],
      });
    }

    if (onAoiPolygonDrawn) {
      onAoiPolygonDrawn(geoJsonPoly);
    }

    setPolygonPts([]);
    setDrawMode("none");
  };

  const clearPolygon = () => {
    setActivePolygon(null);
    setPolygonPts([]);
    if (mapRef.current && mapRef.current.getSource("aoi-polygon-source")) {
      const src = mapRef.current.getSource("aoi-polygon-source") as maplibregl.GeoJSONSource;
      src.setData({ type: "FeatureCollection", features: [] });
    }
  };

  // Markers render
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    results.forEach((r) => {
      const isSelected = r.tile_id === selectedTileId;
      const el = document.createElement("div");
      el.className = "group relative flex items-center justify-center transition-transform hover:scale-125";
      el.style.width = isSelected ? "26px" : "18px";
      el.style.height = isSelected ? "26px" : "18px";
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

      el.title = `${r.classification_label ?? "Observation"} | Score: ${(r.final_score * 100).toFixed(0)}%`;
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        onSelect(r);
      });

      const marker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([r.lon, r.lat])
        .addTo(map);

      markersRef.current.push(marker);
    });

    // Only fit bounds on fresh result sets (no tile selected)
    if (!selectedTileId && results.length > 0) {
      const bounds = new maplibregl.LngLatBounds();
      results.forEach((r) => bounds.extend([r.lon, r.lat]));
      map.fitBounds(bounds, { padding: 80, maxZoom: 15, duration: 600 });
    }
  }, [results, selectedTileId, onSelect]);

  // Cluster marker render
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    clusterMarkersRef.current.forEach((m) => m.remove());
    clusterMarkersRef.current = [];

    if (activeCluster) {
      const el = document.createElement("div");
      el.className = "flex items-center justify-center p-2 rounded-full bg-cyan-500/30 border-2 border-cyan-400 shadow-[0_0_20px_#06b6d4] text-white font-mono text-[10px] font-bold";
      el.style.width = "40px";
      el.style.height = "40px";
      el.innerText = String(activeCluster.count);

      const marker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat(activeCluster.centroid)
        .addTo(map);

      clusterMarkersRef.current.push(marker);
      map.flyTo({ center: activeCluster.centroid, zoom: 13, duration: 600 });
    }
  }, [activeCluster]);

  return (
    <div
      className="relative w-full h-full overflow-hidden select-none"
      onClick={handleMapClick}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
    >
      <div ref={containerRef} className="w-full h-full" />

      {/* AOI Drag Drawing Box Overlay */}
      {dragStart && dragCurrent && drawMode === "box" && (
        <div
          className="absolute border-2 border-dashed border-cyan-400 bg-cyan-500/20 pointer-events-none z-30"
          style={{
            left: Math.min(dragStart.x, dragCurrent.x),
            top: Math.min(dragStart.y, dragCurrent.y),
            width: Math.abs(dragCurrent.x - dragStart.x),
            height: Math.abs(dragCurrent.y - dragStart.y),
          }}
        >
          <span className="absolute top-1 left-1 px-1.5 py-0.5 rounded bg-black/80 font-mono text-[9px] text-cyan-400 font-bold">
            RECTANGLE AOI
          </span>
        </div>
      )}

      {/* Floating Basemap Switcher */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1 p-1 rounded bg-black/85 backdrop-blur-md border border-neutral-800 shadow-xl text-[10px] font-mono tracking-widest uppercase">
        {(["satellite", "dark", "osm", "offline"] as BasemapType[]).map((type) => (
          <button
            key={type}
            onClick={() => switchBasemap(type)}
            className={`px-3 py-1 rounded transition-all ${
              basemap === type
                ? "bg-neutral-800 text-cyan-400 border border-cyan-500/50 font-bold"
                : "text-neutral-400 hover:text-neutral-200 border border-transparent"
            }`}
          >
            [ {type.toUpperCase()} ]
          </button>
        ))}
      </div>

      {/* Custom Map Controls HUD */}
      <div className="absolute top-4 right-4 z-20 flex flex-col gap-1.5 bg-black/85 backdrop-blur-md p-1.5 rounded border border-neutral-800 shadow-xl font-mono text-xs">
        <button
          onClick={handleZoomIn}
          className="w-8 h-8 rounded bg-neutral-900 hover:bg-neutral-800 text-neutral-300 hover:text-white flex items-center justify-center border border-neutral-800"
          title="Zoom In"
        >
          +
        </button>
        <button
          onClick={handleZoomOut}
          className="w-8 h-8 rounded bg-neutral-900 hover:bg-neutral-800 text-neutral-300 hover:text-white flex items-center justify-center border border-neutral-800"
          title="Zoom Out"
        >
          −
        </button>
        <button
          onClick={handleResetCenter}
          className="w-8 h-8 rounded bg-neutral-900 hover:bg-neutral-800 text-neutral-300 hover:text-cyan-400 flex items-center justify-center border border-neutral-800"
          title="Reset Center"
        >
          ⌖
        </button>
        <div className="w-full h-px bg-neutral-800 my-0.5" />
        <button
          onClick={() => setMode("box")}
          className={`w-8 h-8 rounded flex items-center justify-center transition-all border ${
            drawMode === "box"
              ? "bg-cyan-950 text-cyan-400 border-cyan-500 font-bold shadow-[0_0_10px_#06b6d4]"
              : "bg-neutral-900 hover:bg-neutral-800 text-neutral-300 hover:text-cyan-400 border-neutral-800"
          }`}
          title="Draw Rectangle BBox AOI"
        >
          ◇
        </button>
        <button
          onClick={() => setMode("polygon")}
          className={`w-8 h-8 rounded flex items-center justify-center transition-all border ${
            drawMode === "polygon"
              ? "bg-emerald-950 text-emerald-400 border-emerald-500 font-bold shadow-[0_0_10px_#10b981]"
              : "bg-neutral-900 hover:bg-neutral-800 text-neutral-300 hover:text-emerald-400 border-neutral-800"
          }`}
          title="Draw Freehand Polygon AOI"
        >
          ⬡
        </button>
        {activePolygon && (
          <button
            onClick={clearPolygon}
            className="w-8 h-8 rounded bg-neutral-900 hover:bg-red-950 text-neutral-400 hover:text-red-400 flex items-center justify-center border border-neutral-800"
            title="Clear Polygon AOI"
          >
            ✕
          </button>
        )}
      </div>

      {/* AOI Draw Mode HUD Notifications */}
      {drawMode === "box" && (
        <div className="absolute top-16 left-1/2 -translate-x-1/2 z-20 px-4 py-1.5 rounded-full bg-cyan-950/90 border border-cyan-500 text-cyan-300 font-mono text-[10px] tracking-wider uppercase shadow-lg animate-pulse">
          Click and drag on the map to define bounding box AOI
        </div>
      )}

      {drawMode === "polygon" && (
        <div className="absolute top-16 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 px-4 py-1.5 rounded-full bg-emerald-950/90 border border-emerald-500 text-emerald-300 font-mono text-[10px] tracking-wider uppercase shadow-lg">
          <span>Click map to add polygon vertices ({polygonPts.length} pts)</span>
          {polygonPts.length >= 3 && (
            <button
              onClick={completePolygon}
              className="px-2 py-0.5 rounded bg-emerald-500 text-black font-bold hover:bg-emerald-400 transition-colors"
            >
              COMPLETE POLYGON ✓
            </button>
          )}
        </div>
      )}
    </div>
  );
}
