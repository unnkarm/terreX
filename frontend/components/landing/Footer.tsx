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
            <h3 className="text-xl sm:text-3xl font-bold tracking-tight text-white font-sans">
              Launch TerreX <span className="text-neutral-400 font-light">console.</span>
            </h3>
            <p className="text-neutral-300 text-sm font-sans font-light">
              Start querying and comparing air-gapped satellite scenes with zero cloud egress.
            </p>
          </div>

          <Link
            href="/workspace"
            className="px-8 py-3.5 bg-white text-black font-sans font-semibold text-xs tracking-widest uppercase hover:bg-neutral-200 transition"
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
            <p className="text-[11px] text-neutral-400 font-sans font-light leading-relaxed">
              Offline satellite intelligence and change detection for defense analysts.
            </p>
          </div>

          <div className="space-y-2">
            <div className="text-white font-semibold uppercase tracking-wider text-[11px]">CONSOLES</div>
            <ul className="space-y-1 text-neutral-400 text-[11px] font-sans">
              <li><Link href="/workspace" className="hover:text-white transition">Workspace</Link></li>
              <li><Link href="/changes" className="hover:text-white transition">Change Scanner</Link></li>
              <li><Link href="/review" className="hover:text-white transition">Review Queue</Link></li>
              <li><Link href="/data" className="hover:text-white transition">Data Catalog</Link></li>
              <li><Link href="/system" className="hover:text-white transition">System Status</Link></li>
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
