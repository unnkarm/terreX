"use client";

import { useState } from "react";

interface QueryPreset {
  id: string;
  label: string;
  query: string;
  aoi: string;
  sensor: string;
  dateBefore: string;
  dateAfter: string;
  similarity: number;
  changeScore: number;
  falseAlarmCountRaw: number;
  falseAlarmCountFiltered: number;
  changeSummary: string;
  description: string;
}

const PRESETS: QueryPreset[] = [
  {
    id: "buildings-river",
    label: "New buildings near a river",
    query: "new buildings and construction expansion near riverbank",
    aoi: "YAMUNA BASIN SECTOR 4",
    sensor: "Cartosat-3 (0.28m PAN)",
    dateBefore: "2023-01-15",
    dateAfter: "2024-01-20",
    similarity: 96.8,
    changeScore: 0.88,
    falseAlarmCountRaw: 14,
    falseAlarmCountFiltered: 0,
    changeSummary: "+4 New reinforced concrete structures (1,240 m²) erected within 80m of shoreline.",
    description: "Multi-temporal optical comparison identifying new housing and industrial foundation slabs along the riparian boundary.",
  },
  {
    id: "runway-extension",
    label: "Airfield runway & hangar expansion",
    query: "asphalt runway extension and new aircraft revetments",
    aoi: "NORTHERN FORWARD AIRBASE",
    sensor: "PlanetScope SuperDove (3m)",
    dateBefore: "2023-04-10",
    dateAfter: "2024-02-18",
    similarity: 94.2,
    changeScore: 0.92,
    falseAlarmCountRaw: 22,
    falseAlarmCountFiltered: 1,
    changeSummary: "+650m asphalt taxiway extension + 3 hardened shelter footprints.",
    description: "Sub-pixel feature differences isolated tarmac hardening against surrounding arid soil reflectance shifts.",
  },
  {
    id: "vessel-berth",
    label: "Coastal naval vessel berthing",
    query: "large combatant vessels docked at deepwater pier",
    aoi: "EASTERN NAVAL COMMAND PIER 3",
    sensor: "Sentinel-2 MSI (10m VNIR)",
    dateBefore: "2023-06-02",
    dateAfter: "2024-01-12",
    similarity: 91.5,
    changeScore: 0.79,
    falseAlarmCountRaw: 38,
    falseAlarmCountFiltered: 0,
    changeSummary: "+2 Frigate-class vessels (length ~135m) berthed at Berth Alpha.",
    description: "Sun glint and tidal wave chop successfully suppressed to detect metallic vessel hull radar/optical signatures.",
  },
  {
    id: "border-deforestation",
    label: "Deforestation along border corridor",
    query: "canopy clearing and logging road penetration",
    aoi: "RIDGELINE BUFFER ZONE B-12",
    sensor: "Sentinel-1 SAR + Sentinel-2",
    dateBefore: "2023-03-01",
    dateAfter: "2023-11-28",
    similarity: 89.4,
    changeScore: 0.84,
    falseAlarmCountRaw: 19,
    falseAlarmCountFiltered: 0,
    changeSummary: "+3.2 km newly graded unpaved access corridor + 14 hectares canopy removal.",
    description: "Seasonal deciduous foliage drop suppressed; road incision geometry confirmed.",
  },
];

export default function InteractiveSimulator() {
  const [selectedPreset, setSelectedPreset] = useState<QueryPreset>(PRESETS[0]);
  const [customQuery, setCustomQuery] = useState(PRESETS[0].query);
  const [sliderPosition, setSliderPosition] = useState(50);
  const [suppressFalseAlarms, setSuppressFalseAlarms] = useState(true);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [analystDecision, setAnalystDecision] = useState<"none" | "confirmed" | "rejected">("none");
  const [exportNotice, setExportNotice] = useState<string | null>(null);

  const handlePresetSelect = (preset: QueryPreset) => {
    setSelectedPreset(preset);
    setCustomQuery(preset.query);
    setAnalystDecision("none");
    setExportNotice(null);
  };

  const handleExport = () => {
    setExportNotice(
      `✓ Exported Tactical Packet [TERREX_${selectedPreset.id.toUpperCase()}_INTEL.zip]`
    );
    setTimeout(() => setExportNotice(null), 4000);
  };

  return (
    <section id="simulator" className="py-24 bg-black border-t border-neutral-900">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        
        {/* Minimal Section Header */}
        <div className="space-y-3 mb-12">
          <div className="text-xs font-sans uppercase tracking-widest text-neutral-500 font-medium">
            Interactive Search &amp; Change Detection
          </div>
          <h2 className="text-3xl sm:text-4xl font-bold text-white tracking-tight font-sans">
            Natural language query to verified change.
          </h2>
          <p className="text-neutral-400 max-w-2xl text-sm font-sans font-light">
            Search imagery across dates, detect bi-temporal modifications, and suppress false alarms on-prem.
          </p>
        </div>

        {/* Step 1: Query Console */}
        <div className="bg-neutral-950 border border-neutral-800 rounded p-6 mb-6">
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3 mb-4 border-b border-neutral-800 text-xs font-sans">
            <span className="text-neutral-400 tracking-wider uppercase font-medium">
              Sample Intelligence Queries:
            </span>
            <span className="text-neutral-500">
              Model: RemoteCLIP ViT-B/32 &middot; Offline
            </span>
          </div>

          {/* Presets */}
          <div className="flex flex-wrap gap-2 mb-4">
            {PRESETS.map((preset) => (
              <button
                key={preset.id}
                onClick={() => handlePresetSelect(preset)}
                className={`px-3 py-1.5 text-xs font-sans transition-colors border ${
                  selectedPreset.id === preset.id
                    ? "bg-white text-black border-white font-medium"
                    : "bg-black text-neutral-400 border-neutral-800 hover:border-neutral-600 hover:text-white"
                }`}
              >
                {preset.label}
              </button>
            ))}
          </div>

          {/* Search Input Bar */}
          <div className="flex items-center gap-3 bg-black border border-neutral-800 p-2.5 rounded focus-within:border-neutral-600">
            <input
              type="text"
              value={customQuery}
              onChange={(e) => setCustomQuery(e.target.value)}
              placeholder="Type satellite query..."
              className="w-full bg-transparent text-white font-sans text-sm focus:outline-none placeholder-neutral-600"
            />
            <button className="px-5 py-1.5 bg-white text-black font-sans font-semibold text-xs tracking-wider uppercase hover:bg-neutral-200 transition">
              Search
            </button>
          </div>

          {/* Query metadata strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-4 pt-3 border-t border-neutral-800 text-xs font-sans text-neutral-400">
            <div>
              <span className="text-neutral-600 block text-[11px]">SENSOR</span>
              <span className="text-neutral-200 font-medium">{selectedPreset.sensor}</span>
            </div>
            <div>
              <span className="text-neutral-600 block text-[11px]">TARGET REGION</span>
              <span className="text-neutral-200 font-medium">{selectedPreset.aoi}</span>
            </div>
            <div>
              <span className="text-neutral-600 block text-[11px]">CLOUD COVER</span>
              <span className="text-neutral-200">&lt; 10% (QA Pass)</span>
            </div>
            <div>
              <span className="text-neutral-600 block text-[11px]">SIMILARITY</span>
              <span className="text-white font-semibold">{selectedPreset.similarity}%</span>
            </div>
          </div>
        </div>

        {/* Step 2: Bi-Temporal Split View */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          
          {/* Main Before / After Canvas */}
          <div className="lg:col-span-8 bg-neutral-950 border border-neutral-800 rounded p-5">
            
            <div className="flex flex-wrap items-center justify-between gap-3 pb-3 mb-4 border-b border-neutral-800 text-xs font-sans">
              <span className="text-neutral-300 font-medium uppercase tracking-wider">
                Bi-Temporal Comparison
              </span>

              <div className="flex items-center gap-5 text-xs">
                <label className="flex items-center gap-2 cursor-pointer text-neutral-300">
                  <input
                    type="checkbox"
                    checked={showHeatmap}
                    onChange={(e) => setShowHeatmap(e.target.checked)}
                    className="accent-white w-3.5 h-3.5"
                  />
                  <span>Change Mask</span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer text-neutral-300">
                  <input
                    type="checkbox"
                    checked={suppressFalseAlarms}
                    onChange={(e) => setSuppressFalseAlarms(e.target.checked)}
                    className="accent-white w-3.5 h-3.5"
                  />
                  <span>Suppress False Alarms</span>
                </label>
              </div>
            </div>

            {/* Simulated Satellite Image Split */}
            <div className="relative aspect-[16/10] w-full rounded overflow-hidden border border-neutral-800 bg-black select-none">
              
              {/* T1 Baseline */}
              <div className="absolute inset-0 flex items-center justify-center">
                <svg className="w-full h-full" viewBox="0 0 600 375" preserveAspectRatio="none">
                  <rect width="600" height="375" fill="#171e19" />
                  <path
                    d="M 0 120 Q 180 80 320 190 T 600 240 L 600 300 Q 320 250 180 140 T 0 180 Z"
                    fill="#15262f"
                  />
                  <polygon points="40,20 160,30 150,110 30,90" fill="#202c23" stroke="#171e19" />
                  <polygon points="360,40 540,50 520,160 350,140" fill="#1c2820" stroke="#171e19" />
                  <polygon points="80,220 220,230 200,340 70,330" fill="#19231c" stroke="#171e19" />
                  <polygon points="380,260 560,270 540,360 370,350" fill="#202c23" stroke="#171e19" />
                  <rect x="120" y="50" width="16" height="14" fill="#475569" />
                  <rect x="145" y="55" width="14" height="12" fill="#334155" />
                  <rect x="420" y="80" width="18" height="14" fill="#475569" />
                  <path d="M 10 70 L 260 90 L 320 180 L 480 320 L 590 330" stroke="#334155" strokeWidth="2.5" fill="none" />
                </svg>
              </div>

              {/* T2 Observation (Slider clipped) */}
              <div
                className="absolute inset-0 overflow-hidden"
                style={{ width: `${sliderPosition}%` }}
              >
                <div className="absolute inset-0 w-[600px] h-full" style={{ width: "100%", minWidth: "100%" }}>
                  <svg className="w-full h-full" viewBox="0 0 600 375" preserveAspectRatio="none">
                    <rect width="600" height="375" fill="#141c16" />
                    <path
                      d="M 0 120 Q 180 80 320 190 T 600 240 L 600 300 Q 320 250 180 140 T 0 180 Z"
                      fill="#12222b"
                    />
                    <polygon points="40,20 160,30 150,110 30,90" fill="#1c2820" stroke="#171e19" />
                    <polygon points="360,40 540,50 520,160 350,140" fill="#19231c" stroke="#171e19" />
                    <polygon points="80,220 220,230 200,340 70,330" fill="#162019" stroke="#171e19" />
                    <polygon points="380,260 560,270 540,360 370,350" fill="#1c2820" stroke="#171e19" />
                    <rect x="120" y="50" width="16" height="14" fill="#475569" />
                    <rect x="145" y="55" width="14" height="12" fill="#334155" />
                    <rect x="420" y="80" width="18" height="14" fill="#475569" />
                    
                    {/* NEW STRUCTURES */}
                    <rect x="220" y="110" width="34" height="28" fill="#e2e8f0" stroke="#94a3b8" />
                    <rect x="260" y="115" width="28" height="24" fill="#cbd5e1" stroke="#94a3b8" />
                    <rect x="235" y="145" width="45" height="30" fill="#f8fafc" stroke="#94a3b8" />
                    <rect x="470" y="180" width="38" height="32" fill="#e2e8f0" stroke="#94a3b8" />
                    
                    <path d="M 10 70 L 260 90 L 320 180 L 480 320 L 590 330" stroke="#475569" strokeWidth="3" fill="none" />
                    <path d="M 260 90 L 250 160 L 470 190" stroke="#64748b" strokeWidth="2.5" strokeDasharray="4,2" fill="none" />

                    {!suppressFalseAlarms && (
                      <>
                        <ellipse cx="220" cy="130" rx="45" ry="15" fill="#fef08a" opacity="0.6" />
                        <ellipse cx="400" cy="230" rx="60" ry="30" fill="#000000" opacity="0.8" />
                      </>
                    )}
                  </svg>
                </div>
              </div>

              {/* Masks Overlay */}
              {showHeatmap && (
                <div className="absolute inset-0 pointer-events-none">
                  <div
                    className="absolute border border-white bg-white/10 rounded"
                    style={{ left: "35%", top: "27%", width: "17%", height: "26%" }}
                  >
                    <div className="absolute -top-5 left-0 bg-black text-white text-[9px] font-sans px-1.5 py-0.2 border border-neutral-700">
                      NEW BUILDINGS (98.4%)
                    </div>
                  </div>
                  <div
                    className="absolute border border-white bg-white/10 rounded"
                    style={{ left: "76%", top: "46%", width: "12%", height: "15%" }}
                  >
                    <div className="absolute -top-5 left-0 bg-black text-white text-[9px] font-sans px-1.5 py-0.2 border border-neutral-700">
                      STRUCTURE +1
                    </div>
                  </div>
                </div>
              )}

              {/* Slider Divider */}
              <div
                className="absolute top-0 bottom-0 w-px bg-white z-30"
                style={{ left: `${sliderPosition}%` }}
              >
                <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-6 h-6 rounded-full bg-black border border-white flex items-center justify-center text-white text-[9px] font-sans font-bold">
                  ◀▶
                </div>
              </div>

              <input
                type="range"
                min="0"
                max="100"
                value={sliderPosition}
                onChange={(e) => setSliderPosition(Number(e.target.value))}
                className="absolute inset-0 w-full h-full opacity-0 cursor-ew-resize z-40"
              />

              <div className="absolute top-3 left-3 bg-black/80 border border-neutral-800 px-2.5 py-1 text-[10px] font-sans text-neutral-300 z-20 pointer-events-none">
                T1 BASELINE: {selectedPreset.dateBefore}
              </div>
              <div className="absolute top-3 right-3 bg-black/80 border border-neutral-800 px-2.5 py-1 text-[10px] font-sans text-white z-20 pointer-events-none">
                T2 OBSERVATION: {selectedPreset.dateAfter}
              </div>
            </div>

            <div className="flex items-center justify-between text-xs font-sans text-neutral-500 mt-2">
              <span>Drag slider to compare baseline vs. observation</span>
              <span>Position: {sliderPosition}%</span>
            </div>
          </div>

          {/* Right Intel Summary */}
          <div className="lg:col-span-4 bg-neutral-950 border border-neutral-800 rounded p-5 space-y-4 text-xs font-sans">
            <div className="text-neutral-300 font-semibold uppercase tracking-wider border-b border-neutral-800 pb-2">
              Analysis Findings
            </div>

            <div className="space-y-2">
              <span className="text-neutral-500 block text-[11px]">SUMMARY</span>
              <p className="text-neutral-200 leading-relaxed">
                {selectedPreset.changeSummary}
              </p>
            </div>

            <div className="pt-3 border-t border-neutral-800 space-y-1">
              <div className="flex justify-between">
                <span className="text-neutral-500">Method:</span>
                <span className="text-neutral-300">Prithvi-EO Feature Diff</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Confidence:</span>
                <span className="text-white font-semibold">{(selectedPreset.changeScore * 100).toFixed(1)}%</span>
              </div>
            </div>

            <div className="pt-3 border-t border-neutral-800 space-y-2">
              <span className="text-neutral-500 block text-[11px]">ANALYST VERIFICATION</span>
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => setAnalystDecision("confirmed")}
                  className={`py-2 text-xs font-sans transition border ${
                    analystDecision === "confirmed"
                      ? "bg-white text-black border-white font-semibold"
                      : "bg-black text-neutral-300 border-neutral-800 hover:border-neutral-600"
                  }`}
                >
                  ✓ CONFIRM
                </button>
                <button
                  onClick={() => setAnalystDecision("rejected")}
                  className={`py-2 text-xs font-sans transition border ${
                    analystDecision === "rejected"
                      ? "bg-neutral-800 text-white border-neutral-600 font-semibold"
                      : "bg-black text-neutral-400 border-neutral-800 hover:border-neutral-600"
                  }`}
                >
                  ✗ REJECT
                </button>
              </div>

              {analystDecision !== "none" && (
                <div className="text-[11px] font-sans text-neutral-300 bg-neutral-900 border border-neutral-800 p-2 text-center">
                  {analystDecision === "confirmed" ? "Result verified and recorded." : "Marked as false alarm."}
                </div>
              )}
            </div>

            <div className="pt-2">
              <button
                onClick={handleExport}
                className="w-full py-2.5 bg-white text-black font-sans font-semibold text-xs tracking-wider uppercase hover:bg-neutral-200 transition"
              >
                Export GIS Packet
              </button>
              {exportNotice && (
                <div className="mt-2 text-[10px] font-sans text-neutral-300 bg-neutral-900 border border-neutral-800 p-2">
                  {exportNotice}
                </div>
              )}
            </div>

          </div>

        </div>

      </div>
    </section>
  );
}
