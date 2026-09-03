"use client";

const CAPABILITIES = [
  {
    code: "01",
    title: "100% Air-Gapped Operation",
    description:
      "TerreX runs entirely on your local infrastructure with zero cloud egress. Strict OFFLINE_MODE guarantees no external API calls at runtime.",
    metric: "0.00 B",
    metricLabel: "Cloud Egress",
  },
  {
    code: "02",
    title: "Multimodal Semantic Search",
    description:
      "Search imagery in natural language or by uploading reference patch chips. RemoteCLIP generates 512-dim visual embeddings for instant tile retrieval.",
    metric: "< 140ms",
    metricLabel: "Search Latency",
  },
  {
    code: "03",
    title: "False-Alarm Suppression",
    description:
      "Automated spectral algorithms filter out sun-glint on water bodies, cloud shadows, and seasonal vegetation browning—leaving only verified structural development.",
    metric: "99.4%",
    metricLabel: "Noise Rejection",
  },
  {
    code: "04",
    title: "Sub-Pixel Change Head",
    description:
      "Prithvi-EO foundation features paired with a feature-differencing head isolate physical infrastructure changes (buildings, roads, runways) across dates.",
    metric: "0.28m",
    metricLabel: "Resolution Support",
  },
  {
    code: "05",
    title: "Multi-Sensor Fusion",
    description:
      "Native support for Cartosat-3, Sentinel-2, Landsat-8/9, PlanetScope, and Sentinel-1 SAR imagery with automated pyramid tiling and reprojection.",
    metric: "5+ Constellations",
    metricLabel: "Native Support",
  },
  {
    code: "06",
    title: "Cryptographic Provenance & Export",
    description:
      "Every change records the exact model weights version, tile IDs, similarity reasons, and analyst verification status. Export to GeoTIFF, GeoJSON, or KML.",
    metric: "100%",
    metricLabel: "Traceability",
  },
];

export default function CapabilitiesGrid() {
  return (
    <section className="py-24 bg-black border-t border-neutral-900">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        
        <div className="space-y-3 mb-12">
          <div className="font-mono text-xs text-radar font-semibold tracking-widest uppercase flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-radar animate-pulse" />
            <span>CORE CAPABILITIES</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-bold text-white tracking-tight font-sans leading-[1.1]">
            Engineered for <span className="text-neutral-400 font-light">precision intelligence.</span>
          </h2>
          <p className="text-base text-neutral-300 max-w-xl font-sans font-light leading-relaxed">
            High-speed semantic search, sub-pixel change detection, and air-gapped security for geospatial analysts.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {CAPABILITIES.map((cap) => (
            <div
              key={cap.code}
              className="bg-neutral-950 border border-neutral-800 p-6 rounded flex flex-col justify-between hover:border-neutral-700 transition"
            >
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-neutral-500">{cap.code}</span>
                  <span className="text-xs font-mono text-neutral-300 font-semibold">{cap.metric}</span>
                </div>
                <h3 className="text-base font-bold text-white font-sans">{cap.title}</h3>
                <p className="text-xs text-neutral-400 font-sans leading-relaxed font-light">
                  {cap.description}
                </p>
              </div>

              <div className="mt-4 pt-3 border-t border-neutral-900 text-[10px] font-sans text-neutral-500 uppercase tracking-wider">
                {cap.metricLabel}
              </div>
            </div>
          ))}
        </div>

      </div>
    </section>
  );
}
