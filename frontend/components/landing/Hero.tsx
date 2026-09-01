"use client";

import Link from "next/link";
import Globe3D from "./Globe3D";

export default function Hero() {
  return (
    <section className="relative min-h-[90vh] flex items-center justify-center pt-24 pb-16 bg-black overflow-hidden">
      <div className="max-w-7xl mx-auto px-6 sm:px-8 w-full relative z-10">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-center">
          
          {/* Left Column: Hero Content */}
          <div className="lg:col-span-6 space-y-8">
            
            {/* Status Line */}
            <div className="font-mono text-xs text-radar font-semibold tracking-widest uppercase flex items-center gap-2">
              <span>MISSION STATUS:</span>
              <span>READY FOR ANALYSIS</span>
            </div>

            {/* Main Headline (Clean, crisp typography matching reference image) */}
            <div className="space-y-0">
              <h1 className="text-5xl sm:text-7xl font-bold tracking-tight text-white leading-[1.05] font-sans">
                Geospatial
                <br />
                intelligence
                <br />
                <span className="text-neutral-400 font-light">at scale.</span>
              </h1>
            </div>

            {/* Paragraph Text (Clean Inter sans-serif) */}
            <p className="text-base sm:text-lg text-neutral-300 max-w-xl leading-relaxed font-sans font-light">
              TerreX pairs high-resolution optical imagery with bitemporal Sentinel SAR radar data under an agentic vision-language model, returning calibrated confidence vectors and verifiable pixel evidence.
            </p>

            {/* Action Buttons (Exact black & white composition from reference screenshot) */}
            <div className="flex flex-wrap items-center gap-4 pt-2">
              <Link
                href="/workspace"
                className="px-8 py-3.5 bg-white text-black font-sans font-semibold text-xs tracking-widest uppercase hover:bg-neutral-200 transition-colors"
              >
                LAUNCH WORKSPACE
              </Link>

              <a
                href="#simulator"
                className="px-8 py-3.5 bg-black text-white font-sans text-xs tracking-widest uppercase border border-neutral-700 hover:border-white transition-colors"
              >
                LEARN MORE
              </a>
            </div>

          </div>

          {/* Right Column: 3D Wireframe Globe & Telemetry */}
          <div className="lg:col-span-6 relative flex items-center justify-center">
            <div className="w-full max-w-[540px] aspect-square relative">
              <Globe3D />
            </div>
          </div>

        </div>
      </div>

      {/* Subtle Bottom-Left Circular Badge '( N' )' from Reference Image */}
      <div className="absolute bottom-6 left-6 hidden sm:flex items-center justify-center w-8 h-8 rounded-full border border-neutral-800 text-[10px] font-sans text-neutral-500 select-none">
        N&apos;
      </div>
    </section>
  );
}
