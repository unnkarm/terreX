"use client";

export default function SpecsComparison() {
  const comparisonRows = [
    {
      feature: "Air-Gapped / Zero Cloud Egress",
      terrex: "100% On-Prem & SCIF Verified",
      cloudGis: "Requires AWS/GCP/Cloud Upload",
      manual: "Air-gapped (Slow)",
    },
    {
      feature: "Search Speed across 100k+ Tiles",
      terrex: "< 140ms (RemoteCLIP Vector Index)",
      cloudGis: "3 - 8 seconds",
      manual: "Hours to Days of manual browsing",
    },
    {
      feature: "Multimodal Natural Language Query",
      terrex: "Native Zero-Shot Vision-Language",
      cloudGis: "Limited / Cloud API Dependent",
      manual: "None (Manual visual scanning)",
    },
    {
      feature: "Automated False-Alarm Suppression",
      terrex: "Dual-Stage Spectral (Glint, Cloud, Phenology)",
      cloudGis: "Basic threshold difference only",
      manual: "High fatigue & error rate",
    },
    {
      feature: "Bi-Temporal Sub-Pixel Alignment",
      terrex: "Prithvi-EO Foundation Head",
      cloudGis: "Proprietary cloud license",
      manual: "Manual optical blinking",
    },
    {
      feature: "Audit Provenance & Export",
      terrex: "Signed Hash + GeoTIFF/GeoJSON/KML",
      cloudGis: "Proprietary format lock-in",
      manual: "Manual PDF reports",
    },
  ];

  return (
    <section id="specs" className="py-24 bg-black border-t border-neutral-900">
      <div className="max-w-7xl mx-auto px-6 sm:px-8">
        
        <div className="space-y-3 mb-12">
          <div className="text-xs font-sans uppercase tracking-widest text-neutral-500 font-medium">
            System Specifications
          </div>
          <h2 className="text-3xl sm:text-4xl font-bold text-white tracking-tight font-sans">
            Air-gapped performance benchmark.
          </h2>
          <p className="text-neutral-400 max-w-xl text-sm font-sans font-light">
            Engineered to remove the operational bottleneck of manual satellite tile analysis in secure environments.
          </p>
        </div>

        <div className="bg-neutral-950 border border-neutral-800 rounded overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left font-sans text-xs">
              <thead>
                <tr className="bg-black border-b border-neutral-800 text-neutral-400 uppercase text-[11px]">
                  <th className="py-4 px-6 font-semibold">Capability</th>
                  <th className="py-4 px-6 text-white font-bold bg-neutral-900 border-l border-r border-neutral-800">
                    TerreX (Air-Gapped)
                  </th>
                  <th className="py-4 px-6">Cloud GIS Platforms</th>
                  <th className="py-4 px-6">Manual Analyst Browsing</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-800">
                {comparisonRows.map((row, idx) => (
                  <tr key={idx} className="hover:bg-neutral-900/50 transition">
                    <td className="py-3.5 px-6 font-medium text-white">{row.feature}</td>
                    <td className="py-3.5 px-6 text-white font-semibold bg-neutral-900 border-l border-r border-neutral-800">
                      ✓ {row.terrex}
                    </td>
                    <td className="py-3.5 px-6 text-neutral-400">{row.cloudGis}</td>
                    <td className="py-3.5 px-6 text-neutral-500">{row.manual}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

      </div>
    </section>
  );
}
