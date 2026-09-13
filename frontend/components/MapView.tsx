"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import maplibregl, { Map as MapLibreMap, Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { SearchResult, SimilarCluster, API_BASE } from "@/lib/api";

interface Props {
  results: SearchResult[];
  selectedTileId: string | null;
  onSelect: (r: SearchResult) => void;
  center: [number, number];
  activeBbox?: [number, number, number, number];
  activePolygon?: [number, number][] | any;
  isDrawingAoi?: boolean;
  onDrawModeChange?: (mode: "none" | "box" | "polygon") => void;
  onAoiDrawn?: (bbox: [number, number, number, number]) => void;
  onAoiPolygonDrawn?: (polygonGeoJson: { type: "Polygon"; coordinates: number[][][] }) => void;
  activeCluster?: SimilarCluster | null;
}

type BasemapType = "satellite" | "offline_satellite" | "street" | "tactical";

// Procedural tactical coordinate graticule generator (axes, major 10-deg, intermediate 2-deg, and reticles)
function generateTacticalGraticule(): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];

  // 1. Prime Meridian and Equator (kind: "axis")
  features.push({
    type: "Feature",
    properties: { kind: "axis", name: "EQUATOR" },
    geometry: {
      type: "LineString",
      coordinates: Array.from({ length: 73 }, (_, i) => [-180 + i * 5, 0]),
    },
  });
  features.push({
    type: "Feature",
    properties: { kind: "axis", name: "PRIME MERIDIAN" },
    geometry: {
      type: "LineString",
      coordinates: [
        [0, -85],
        [0, 85],
      ],
    },
  });

  // 2. Tropics and Polar circles (kind: "tropics")
  const specialLats = [
    { lat: 23.4368, name: "TROPIC OF CANCER" },
    { lat: -23.4368, name: "TROPIC OF CAPRICORN" },
    { lat: 66.5636, name: "ARCTIC CIRCLE" },
    { lat: -66.5636, name: "ANTARCTIC CIRCLE" },
  ];
  for (const { lat, name } of specialLats) {
    features.push({
      type: "Feature",
      properties: { kind: "tropics", name },
      geometry: {
        type: "LineString",
        coordinates: Array.from({ length: 73 }, (_, i) => [-180 + i * 5, lat]),
      },
    });
  }

  // 3. 10-degree Major Graticules (kind: "major")
  for (let lon = -180; lon <= 180; lon += 10) {
    if (lon === 0) continue;
    features.push({
      type: "Feature",
      properties: { kind: "major", lon },
      geometry: {
        type: "LineString",
        coordinates: [
          [lon, -85],
          [lon, 85],
        ],
      },
    });
  }
  for (let lat = -80; lat <= 80; lat += 10) {
    if (lat === 0) continue;
    features.push({
      type: "Feature",
      properties: { kind: "major", lat },
      geometry: {
        type: "LineString",
        coordinates: Array.from({ length: 73 }, (_, i) => [-180 + i * 5, lat]),
      },
    });
  }

  // 4. 2-degree Intermediate Graticules (kind: "intermediate")
  for (let lon = -180; lon <= 180; lon += 2) {
    if (lon % 10 === 0) continue;
    features.push({
      type: "Feature",
      properties: { kind: "intermediate", lon },
      geometry: {
        type: "LineString",
        coordinates: [
          [lon, -84],
          [lon, 84],
        ],
      },
    });
  }
  for (let lat = -80; lat <= 80; lat += 2) {
    if (lat % 10 === 0) continue;
    features.push({
      type: "Feature",
      properties: { kind: "intermediate", lat },
      geometry: {
        type: "LineString",
        coordinates: Array.from({ length: 73 }, (_, i) => [-180 + i * 5, lat]),
      },
    });
  }

  // 5. Tactical Intersections / Reticles (kind: "reticle")
  for (let lon = -180; lon <= 180; lon += 10) {
    for (let lat = -80; lat <= 80; lat += 10) {
      features.push({
        type: "Feature",
        properties: { kind: "reticle" },
        geometry: {
          type: "Point",
          coordinates: [lon, lat],
        },
      });
    }
  }

  return {
    type: "FeatureCollection",
    features,
  };
}

const TACTICAL_BASE_DATA = generateTacticalGraticule();

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
  offline_satellite: {
    version: 8,
    sources: {
      "offline-satellite-cache": {
        type: "raster",
        tiles: [
          `${API_BASE}/api/basemap/tiles/{z}/{x}/{y}.png`,
        ],
        tileSize: 256,
        attribution: "TerreX Offline Satellite Tile Store",
      },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "#050505" } },
      { id: "offline-sat-layer", type: "raster", source: "offline-satellite-cache", minzoom: 0, maxzoom: 19 },
    ],
  },
  street: {
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
      { id: "street-layer", type: "raster", source: "osm-tiles", minzoom: 0, maxzoom: 19 },
    ],
  },
  tactical: {
    version: 8,
    sources: {
      "tactical-graticule": {
        type: "geojson",
        data: TACTICAL_BASE_DATA,
      },
      "tactical-micro": {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      },
    },
    layers: [
      {
        id: "bg",
        type: "background",
        paint: { "background-color": "#080c14" },
      },
      // 10-degree Major grid lines
      {
        id: "tactical-major",
        type: "line",
        source: "tactical-graticule",
        filter: ["==", ["get", "kind"], "major"],
        paint: {
          "line-color": "#1e3a5f",
          "line-width": 1,
          "line-opacity": 0.55,
        },
      },
      // 2-degree Intermediate grid lines (visible when zoomed in)
      {
        id: "tactical-intermediate",
        type: "line",
        source: "tactical-graticule",
        minzoom: 4,
        filter: ["==", ["get", "kind"], "intermediate"],
        paint: {
          "line-color": "#0e243b",
          "line-width": 0.75,
          "line-opacity": 0.5,
          "line-dasharray": [2, 2],
        },
      },
      // Tropics / Polar Circles
      {
        id: "tactical-tropics",
        type: "line",
        source: "tactical-graticule",
        filter: ["==", ["get", "kind"], "tropics"],
        paint: {
          "line-color": "#f59e0b",
          "line-width": 1,
          "line-opacity": 0.45,
          "line-dasharray": [3, 3],
        },
      },
      // Equator & Prime Meridian Axis
      {
        id: "tactical-axis",
        type: "line",
        source: "tactical-graticule",
        filter: ["==", ["get", "kind"], "axis"],
        paint: {
          "line-color": "#06b6d4",
          "line-width": 1.5,
          "line-opacity": 0.85,
          "line-dasharray": [4, 2],
        },
      },
      // Dynamic Micro-grid lines (0.1 / 0.05 / 0.01 deg based on zoom)
      {
        id: "tactical-micro-lines",
        type: "line",
        source: "tactical-micro",
        minzoom: 7,
        paint: {
          "line-color": "#00f0ff",
          "line-width": 0.75,
          "line-opacity": 0.35,
          "line-dasharray": [2, 2],
        },
      },
      // Intersection reticle dots
      {
        id: "tactical-reticles",
        type: "circle",
        source: "tactical-graticule",
        filter: ["==", ["get", "kind"], "reticle"],
        paint: {
          "circle-radius": 2.5,
          "circle-color": "#22d3ee",
          "circle-opacity": 0.7,
          "circle-stroke-width": 1,
          "circle-stroke-color": "#080c14",
        },
      },
    ],
  },
};

function formatCoord(deg: number, type: "lat" | "lon"): string {
  const dir = type === "lat" ? (deg >= 0 ? "N" : "S") : (deg >= 0 ? "E" : "W");
  const abs = Math.abs(deg);
  const d = Math.floor(abs);
  const m = Math.floor((abs - d) * 60);
  const s = ((abs - d - m / 60) * 3600).toFixed(1);
  return `${d}°${m}'${s}"${dir} (${deg.toFixed(4)}°)`;
}

export default function MapView({
  results,
  selectedTileId,
  onSelect,
  center,
  activeBbox,
  activePolygon: externalPolygon,
  isDrawingAoi = false,
  onDrawModeChange,
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
  const basemapRef = useRef<BasemapType>("satellite");
  const activePolygonRef = useRef<[number, number][] | null>(null);
  const [cursorCoord, setCursorCoord] = useState<{ lon: number; lat: number } | null>(null);
  const [drawMode, setDrawMode] = useState<"none" | "box" | "polygon">("none");
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [dragCurrent, setDragCurrent] = useState<{ x: number; y: number } | null>(null);
  const [polygonPts, setPolygonPts] = useState<[number, number][]>([]);
  const [activePolygon, setActivePolygon] = useState<[number, number][] | null>(null);

  // Synchronize external bounding box or polygon onto the map GeoJSON overlay
  useEffect(() => {
    let coords: [number, number][] | null = null;
    if (externalPolygon) {
      if (Array.isArray(externalPolygon) && Array.isArray(externalPolygon[0])) {
        coords = externalPolygon as [number, number][];
      } else if (externalPolygon.coordinates && Array.isArray(externalPolygon.coordinates[0])) {
        coords = externalPolygon.coordinates[0] as [number, number][];
      }
    } else if (activeBbox && activeBbox.length === 4) {
      const [w, s, e, n] = activeBbox;
      coords = [
        [w, s],
        [e, s],
        [e, n],
        [w, n],
        [w, s],
      ];
    }

    activePolygonRef.current = coords;
    setActivePolygon(coords);

    if (mapRef.current && mapRef.current.getSource("aoi-polygon-source")) {
      const src = mapRef.current.getSource("aoi-polygon-source") as maplibregl.GeoJSONSource;
      if (coords) {
        src.setData({
          type: "FeatureCollection",
          features: [
            {
              type: "Feature",
              geometry: {
                type: "Polygon",
                coordinates: [coords],
              },
              properties: { name: "Active AOI" },
            },
          ],
        });
      } else {
        src.setData({ type: "FeatureCollection", features: [] });
      }
    }
  }, [activeBbox, externalPolygon]);

  // Sync external draw trigger
  useEffect(() => {
    if (isDrawingAoi) {
      setDrawMode("box");
      if (mapRef.current) {
        mapRef.current.dragPan.disable();
      }
    } else if (drawMode === "box" && !isDrawingAoi) {
      // allow user or parent to toggle
    }
  }, [isDrawingAoi]);

  // Helper to ensure AOI polygon layers exist across basemap switches
  const ensureAoiPolygonLayers = (map: MapLibreMap) => {
    if (!map.getSource("aoi-polygon-source")) {
      map.addSource("aoi-polygon-source", {
        type: "geojson",
        data: activePolygonRef.current
          ? {
              type: "FeatureCollection",
              features: [
                {
                  type: "Feature",
                  geometry: {
                    type: "Polygon",
                    coordinates: [activePolygonRef.current],
                  },
                  properties: { name: "Active AOI Polygon" },
                },
              ],
            }
          : { type: "FeatureCollection", features: [] },
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
  };

  // Adaptive micro-grid calculation for tactical mode
  const updateTacticalMicroGrid = useCallback(() => {
    const map = mapRef.current;
    if (!map || basemapRef.current !== "tactical") return;
    const zoom = map.getZoom();
    const microSrc = map.getSource("tactical-micro") as maplibregl.GeoJSONSource | undefined;
    if (!microSrc) return;

    if (zoom < 7) {
      microSrc.setData({ type: "FeatureCollection", features: [] });
      return;
    }

    const bounds = map.getBounds();
    const west = Math.max(-180, bounds.getWest());
    const east = Math.min(180, bounds.getEast());
    const south = Math.max(-85, bounds.getSouth());
    const north = Math.min(85, bounds.getNorth());

    let step = 1;
    if (zoom >= 14) step = 0.01;
    else if (zoom >= 12) step = 0.05;
    else if (zoom >= 10) step = 0.1;
    else if (zoom >= 8) step = 0.5;

    const microFeatures: GeoJSON.Feature[] = [];
    const startLon = Math.floor(west / step) * step;
    const endLon = Math.ceil(east / step) * step;
    const startLat = Math.floor(south / step) * step;
    const endLat = Math.ceil(north / step) * step;

    const maxLines = 80;
    const lonCount = Math.round((endLon - startLon) / step);
    const latCount = Math.round((endLat - startLat) / step);

    if (lonCount <= maxLines) {
      for (let lon = startLon; lon <= endLon; lon += step) {
        microFeatures.push({
          type: "Feature",
          properties: { lon },
          geometry: {
            type: "LineString",
            coordinates: [
              [Number(lon.toFixed(4)), Number(south.toFixed(4))],
              [Number(lon.toFixed(4)), Number(north.toFixed(4))],
            ],
          },
        });
      }
    }

    if (latCount <= maxLines) {
      for (let lat = startLat; lat <= endLat; lat += step) {
        microFeatures.push({
          type: "Feature",
          properties: { lat },
          geometry: {
            type: "LineString",
            coordinates: [
              [Number(west.toFixed(4)), Number(lat.toFixed(4))],
              [Number(east.toFixed(4)), Number(lat.toFixed(4))],
            ],
          },
        });
      }
    }

    microSrc.setData({
      type: "FeatureCollection",
      features: microFeatures,
    });
  }, []);

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
      ensureAoiPolygonLayers(map);
      if (basemapRef.current === "tactical") {
        updateTacticalMicroGrid();
      }
    });

    map.on("styledata", () => {
      ensureAoiPolygonLayers(map);
      if (basemapRef.current === "tactical") {
        updateTacticalMicroGrid();
      }
    });

    map.on("moveend", () => {
      if (basemapRef.current === "tactical") {
        updateTacticalMicroGrid();
      }
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [updateTacticalMicroGrid]);

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
    basemapRef.current = type;
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
    onDrawModeChange?.(next);
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
    if (mapRef.current && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      const lngLat = mapRef.current.unproject([e.clientX - rect.left, e.clientY - rect.top]);
      setCursorCoord({ lon: lngLat.lng, lat: lngLat.lat });
    }
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
    onDrawModeChange?.("none");
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
    activePolygonRef.current = closed;
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
    onDrawModeChange?.("none");
  };

  const clearPolygon = () => {
    setActivePolygon(null);
    activePolygonRef.current = null;
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

    // Deduplicate or render only selected tile when a selection is active
    results.forEach((r) => {
      const isSelected = r.tile_id === selectedTileId;

      // If a tile is selected, only render the active selected point
      if (selectedTileId && !isSelected) {
        return;
      }

      const el = document.createElement("div");
      el.className = "group relative flex items-center justify-center transition-transform hover:scale-125";
      el.style.width = isSelected ? "32px" : "14px";
      el.style.height = isSelected ? "32px" : "14px";
      el.style.cursor = "pointer";

      // Outer pulse halo & target reticle for selected item
      if (isSelected) {
        const pulse = document.createElement("span");
        pulse.className = "absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-75";
        el.appendChild(pulse);

        const ring = document.createElement("span");
        ring.className = "absolute inline-flex h-7 w-7 rounded-full border border-cyan-400/80 animate-pulse";
        el.appendChild(ring);
      }

      // Inner tactical dot
      const dot = document.createElement("span");
      dot.className = `relative inline-flex rounded-full border-2 border-black ${
        isSelected
          ? "h-4 w-4 bg-cyan-400 shadow-[0_0_16px_#22d3ee]"
          : "h-2 w-2 bg-amber-400/80 shadow-[0_0_4px_#f59e0b]"
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
      <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-1 p-1 rounded-md bg-neutral-950/90 backdrop-blur-md border border-neutral-800 shadow-2xl text-[10px] font-mono whitespace-nowrap select-none">
        {[
          { id: "satellite" as const, label: "SATELLITE" },
          { id: "offline_satellite" as const, label: "OFFLINE SAT" },
          { id: "street" as const, label: "STREET" },
          { id: "tactical" as const, label: "TACTICAL" },
        ].map((item) => {
          const isActive = basemap === item.id;
          return (
            <button
              key={item.id}
              onClick={() => switchBasemap(item.id)}
              className={`px-3 py-1.5 rounded text-[10px] font-mono uppercase tracking-wider transition-all whitespace-nowrap flex items-center gap-1.5 ${
                isActive
                  ? "bg-neutral-800 text-cyan-400 border border-cyan-500/60 font-bold shadow-[0_0_12px_rgba(6,182,212,0.25)]"
                  : "text-neutral-400 hover:text-white hover:bg-neutral-900 border border-transparent"
              }`}
            >
              {isActive && <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_#06b6d4]" />}
              <span>{item.label}</span>
            </button>
          );
        })}
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
      {/* Center crosshair reticle for Tactical Mode */}
      {basemap === "tactical" && (
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none z-10 opacity-30">
          <div className="relative w-10 h-10 flex items-center justify-center">
            <div className="absolute w-10 h-px bg-cyan-400" />
            <div className="absolute h-10 w-px bg-cyan-400" />
            <div className="w-4 h-4 rounded-full border border-cyan-400" />
          </div>
        </div>
      )}

      {/* Tactical Mode Offline Status & Coordinate Readout HUD */}
      {basemap === "tactical" && (
        <div className="absolute bottom-4 left-4 z-20 flex items-center gap-2.5 px-3 py-1.5 rounded bg-black/85 backdrop-blur-md border border-cyan-900/60 shadow-xl font-mono text-[10px] text-cyan-400">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-bold text-emerald-400 tracking-wider">AIR-GAP 100% OFFLINE</span>
          </div>
          <span className="text-neutral-700">|</span>
          <span className="text-neutral-300">
            {cursorCoord
              ? `CURSOR: ${formatCoord(cursorCoord.lat, "lat")} · ${formatCoord(cursorCoord.lon, "lon")}`
              : `CENTER: ${formatCoord(center[1], "lat")} · ${formatCoord(center[0], "lon")}`}
          </span>
          <span className="text-neutral-700">|</span>
          <span className="text-neutral-500 uppercase tracking-widest text-[9px]">PROCEDURAL GRATICULE</span>
        </div>
      )}
    </div>
  );
}
