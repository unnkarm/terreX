"use client";

import { useState } from "react";

interface CliTab {
  id: string;
  title: string;
  command: string;
  output: string;
}

const TABS: CliTab[] = [
  {
    id: "search",
    title: "1. Semantic Search",
    command: `curl -X POST "http://localhost:8000/api/search/text" \\
  -H "Content-Type: application/json" \\
  -d '{
    "query": "new buildings near a river",
    "limit": 3,
    "min_similarity": 0.80,
    "sensor": "Cartosat-3"
  }'`,
    output: `{
  "query": "new buildings near a river",
  "embedding_model": "chendelong/RemoteCLIP-ViT-B-32",
  "embedding_is_placeholder": false,
  "results_count": 3,
  "execution_time_ms": 118.4,
  "results": [
    {
      "tile_id": "cartosat3_20240120_tile_042",
      "similarity": 0.9682,
      "sensor": "Cartosat-3",
      "acquired_at": "2024-01-20T05:32:11Z",
      "lon": 77.2584,
      "lat": 28.5519,
      "resolution_m": 0.28
    }
  ]
}`,
  },
  {
    id: "change",
    title: "2. Change Detection",
    command: `curl -X GET "http://localhost:8000/api/change/detect?\\
before_tile_id=cartosat3_20230115_tile_042&\\
after_tile_id=cartosat3_20240120_tile_042&\\
suppress_false_alarms=true"`,
    output: `{
  "status": "success",
  "before_tile_id": "cartosat3_20230115_tile_042",
  "after_tile_id": "cartosat3_20240120_tile_042",
  "model_head": "Prithvi-EO-100M-FeatureDiff",
  "change_detected": true,
  "change_confidence": 0.884,
  "false_alarm_suppression": {
    "enabled": true,
    "sun_glint_filtered_pixels": 450,
    "cloud_shadow_filtered_pixels": 1200
  },
  "mask_geotiff_path": "/data/tiles/change_masks/diff_042_masked.tif"
}`,
  },
  {
    id: "ingest",
    title: "3. Ingestion CLI",
    command: `python scripts/ingest.py \\
  --incoming-dir data/incoming/ \\
  --tile-size 256`,
    output: `[INFO] Scanning directory: data/incoming/ ...
[INFO] Found 2 new GeoTIFF scenes (1.4 GB total):
       - Cartosat3_Yamuna_20240120_PAN.tif (EPSG:32645, 0.28m GSD)
[INFO] Slicing into 256x256 tiles: 384 tiles generated.
[INFO] Computing 512-dim visual embeddings with RemoteCLIP...
[INFO] Upserting vectors to local Qdrant collection... [OK]
[SUCCESS] Ingestion complete: 384 tiles indexed.`,
  },
];

export default function TerminalDemo() {
  const [activeTab, setActiveTab] = useState(0);

  return (
    <section className="py-20 bg-black border-t border-neutral-900">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4">
          <div className="space-y-3">
            <div className="font-mono text-xs text-radar font-semibold tracking-widest uppercase flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-radar animate-pulse" />
              <span>DEVELOPER INTERFACE</span>
            </div>
            <h2 className="text-3xl sm:text-5xl font-bold text-white tracking-tight font-sans leading-[1.1]">
              REST API &amp; <span className="text-neutral-400 font-light">CLI commands.</span>
            </h2>
          </div>
          <div className="text-xs font-sans text-neutral-500">
            FastAPI OpenAPI docs at <span className="text-white">/docs</span>
          </div>
        </div>

        <div className="bg-neutral-950 border border-neutral-800 rounded overflow-hidden">
          <div className="flex items-center justify-between px-4 py-2.5 bg-black border-b border-neutral-800">
            <div className="flex rounded text-xs font-sans">
              {TABS.map((tab, idx) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(idx)}
                  className={`px-3 py-1.5 transition ${
                    activeTab === idx ? "text-white font-semibold border-b border-white" : "text-neutral-500 hover:text-neutral-300"
                  }`}
                >
                  {tab.title}
                </button>
              ))}
            </div>
          </div>

          <div className="p-4 font-mono text-xs overflow-x-auto space-y-3">
            <div>
              <div className="text-neutral-500 text-[10px] uppercase mb-1">COMMAND:</div>
              <pre className="text-neutral-200 bg-black p-3 rounded border border-neutral-800 leading-relaxed">
                <code>{TABS[activeTab].command}</code>
              </pre>
            </div>
            <div>
              <div className="text-neutral-500 text-[10px] uppercase mb-1">RESPONSE:</div>
              <pre className="text-neutral-400 bg-black p-3 rounded border border-neutral-800 max-h-56 overflow-y-auto leading-relaxed">
                <code>{TABS[activeTab].output}</code>
              </pre>
            </div>
          </div>
        </div>

      </div>
    </section>
  );
}
