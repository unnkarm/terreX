"use client";

import Link from "next/link";
import Logo from "@/components/Logo";

export default function Footer() {
  return (
    <footer className="bg-black border-t border-neutral-900 py-16 text-neutral-400 font-sans text-xs">
      <div className="max-w-7xl mx-auto px-6 sm:px-8 space-y-12">
        
        {/* Top Callout */}
        <div className="bg-neutral-950 border border-neutral-800 p-8 rounded flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="space-y-1 text-center md:text-left">
            <h3 className="text-xl sm:text-2xl font-bold text-white">
              Launch TerreX Console
            </h3>
            <p className="text-neutral-400 text-xs sm:text-sm font-light">
              Start querying and comparing air-gapped satellite scenes.
            </p>
          </div>

          <Link
            href="/workspace"
            className="px-8 py-3 bg-white text-black font-semibold text-xs tracking-widest uppercase hover:bg-neutral-200 transition"
          >
            LAUNCH WORKSPACE
          </Link>
        </div>

        {/* Links */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 pt-4">
          <div className="col-span-2 md:col-span-1 space-y-2">
            <div className="flex items-center gap-2">
              <Logo size={32} showText={true} />
            </div>
            <p className="text-[11px] text-neutral-500 font-light leading-relaxed">
              Offline satellite intelligence and change detection for defense analysts.
            </p>
          </div>

          <div className="space-y-2">
            <div className="text-white font-semibold uppercase tracking-wider text-[11px]">PLATFORM</div>
            <ul className="space-y-1 text-neutral-400 text-[11px]">
              <li><a href="#technology" className="hover:text-white transition">Technology</a></li>
              <li><a href="#simulator" className="hover:text-white transition">Simulator</a></li>
              <li><a href="#specs" className="hover:text-white transition">Specifications</a></li>
            </ul>
          </div>

          <div className="space-y-2">
            <div className="text-white font-semibold uppercase tracking-wider text-[11px]">MODELS</div>
            <ul className="space-y-1 text-neutral-400 text-[11px]">
              <li>RemoteCLIP ViT-B/32</li>
              <li>Prithvi-EO 100M</li>
              <li>Qdrant Local Vector Engine</li>
            </ul>
          </div>

          <div className="space-y-2">
            <div className="text-white font-semibold uppercase tracking-wider text-[11px]">SECURITY</div>
            <ul className="space-y-1 text-neutral-400 text-[11px]">
              <li>100% Air-Gapped Operation</li>
              <li>Zero Cloud Egress</li>
              <li>PostgreSQL + PostGIS</li>
            </ul>
          </div>
        </div>

        <div className="pt-6 border-t border-neutral-900 flex flex-col sm:flex-row items-center justify-between text-[10px] text-neutral-600 gap-3">
          <div>&copy; {new Date().getFullYear()} TerreX. Offline Geospatial Intelligence.</div>
          <div>CRS: EPSG:4326 / EPSG:32645 &middot; ISRO SPEC</div>
        </div>

      </div>
    </footer>
  );
}
