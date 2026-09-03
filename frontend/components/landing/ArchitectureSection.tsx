"use client";

import { useState } from "react";

const PIPELINE_STEPS = [
  {
    step: "01",
    title: "Air-Gapped Ingestion & Tiling",
    description:
      "GeoTIFF and Cloud-Optimized GeoTIFF (COG) files dropped into data/incoming/ are automatically sliced into standardized geo-referenced tiles with WGS84 bounding bounds and GDAL spatial transforms.",
    tech: ["GDAL 3.8", "Rasterio", "Incremental Ingestion"],
  },
  {
    step: "02",
    title: "In-Process Neural Embeddings",
    description:
      "Computes high-dimensional semantic vector embeddings directly inside the backend container using RemoteCLIP and Prithvi-EO foundation models on local CPU/GPU.",
    tech: ["RemoteCLIP ViT-B/32", "Prithvi-EO 100M", "PyTorch"],
  },
  {
    step: "03",
    title: "Local Vector & PostGIS Indexing",
    description:
      "Vectors are indexed in a local Qdrant instance with HNSW cosine distance indexing. Spatial geometries and metadata are managed in PostgreSQL with PostGIS.",
    tech: ["Qdrant Local", "PostgreSQL 16", "PostGIS 3.4"],
  },
  {
    step: "04",
    title: "Bi-Temporal Change & False-Alarm Filter",
    description:
      "Pairs multi-temporal observations, computes feature differences, and applies false-alarm suppression rules to isolate confirmed physical changes.",
    tech: ["Feature Differencing Head", "Spectral Filtering", "QA Masks"],
  },
  {
    step: "05",
    title: "Analyst Command & GIS Export",
    description:
      "Review ranked tiles and change masks on the map. Verify findings and export GIS-ready GeoTIFFs, GeoJSON polygons, and intelligence reports.",
    tech: ["Next.js", "MapLibre GL", "GeoTIFF Export"],
  },
];

export default function ArchitectureSection() {
  const [activeStep, setActiveStep] = useState(0);

  return (
    <section id="technology" className="py-24 bg-black border-t border-neutral-900">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        
        <div className="space-y-3 mb-12">
          <div className="font-mono text-xs text-radar font-semibold tracking-widest uppercase flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-radar animate-pulse" />
            <span>SYSTEM ARCHITECTURE</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-bold text-white tracking-tight font-sans leading-[1.1]">
            Offline satellite <span className="text-neutral-400 font-light">intelligence stack.</span>
          </h2>
          <p className="text-base text-neutral-300 max-w-xl font-sans font-light leading-relaxed">
            Zero cloud telemetry calls, zero external API dependencies. Complete sovereign geospatial intelligence.
          </p>
        </div>

        {/* Step Tabs */}
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-2 mb-8">
          {PIPELINE_STEPS.map((item, idx) => (
            <button
              key={item.step}
              onClick={() => setActiveStep(idx)}
              className={`p-4 text-left border transition ${
                activeStep === idx
                  ? "bg-neutral-900 border-white text-white"
                  : "bg-neutral-950 border-neutral-800 text-neutral-400 hover:border-neutral-700 hover:text-white"
              }`}
            >
              <div className="text-xs font-mono text-neutral-500 mb-1">{item.step}</div>
              <div className="text-xs font-sans font-semibold line-clamp-2">{item.title}</div>
            </button>
          ))}
        </div>

        {/* Active Step Details */}
        <div className="bg-neutral-950 border border-neutral-800 p-8 rounded">
          <div className="max-w-3xl space-y-4 font-sans">
            <div className="text-xs font-mono text-neutral-500">STAGE {PIPELINE_STEPS[activeStep].step}</div>
            <h3 className="text-xl font-bold text-white">{PIPELINE_STEPS[activeStep].title}</h3>
            <p className="text-neutral-300 text-sm leading-relaxed font-light">
              {PIPELINE_STEPS[activeStep].description}
            </p>
            <div className="flex flex-wrap gap-2 pt-2">
              {PIPELINE_STEPS[activeStep].tech.map((t) => (
                <span key={t} className="px-2.5 py-1 bg-black border border-neutral-800 text-neutral-300 text-xs font-sans">
                  {t}
                </span>
              ))}
            </div>
          </div>
        </div>

      </div>
    </section>
  );
}
