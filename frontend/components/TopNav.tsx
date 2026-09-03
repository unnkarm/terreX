"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Logo from "@/components/Logo";
import { SystemStatus } from "@/lib/api";

interface TopNavProps {
  status?: SystemStatus | null;
  onExportClick?: () => void;
}

export default function TopNav({ status, onExportClick }: TopNavProps) {
  const pathname = usePathname();

  const navLinks = [
    { href: "/workspace", label: "WORKSPACE" },
    { href: "/ingest", label: "INGESTION PIPELINE" },
  ];

  return (
    <header className="w-full flex items-center justify-between px-6 py-2.5 bg-black/90 backdrop-blur-md border-b border-neutral-800/80 z-50 select-none">
      {/* Brand & Subtitle */}
      <div className="flex items-center gap-6">
        <Link href="/" className="flex items-center gap-3 group">
          <Logo size={28} showText={true} />
          <span className="hidden lg:inline-block text-[9px] tracking-[0.2em] text-neutral-500 uppercase font-sans font-medium border-l border-neutral-800 pl-3 py-0.5">
            ISRO GEOSPATIAL INTELLIGENCE PORTAL
          </span>
        </Link>

        {/* Focused MVP Nav Tabs */}
        <nav className="flex items-center gap-2 font-sans text-xs uppercase tracking-widest font-semibold">
          {navLinks.map((link) => {
            const isActive = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`px-4 py-1.5 rounded transition-all duration-150 ${
                  isActive
                    ? "bg-white text-black font-semibold shadow-sm"
                    : "text-neutral-400 hover:text-white hover:bg-neutral-900 border border-neutral-800"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Telemetry Status Bar & Actions */}
      <div className="flex items-center gap-4 text-[10px] font-mono tracking-widest text-neutral-400 uppercase">
        <span className="hidden xl:inline-block text-[9px] px-2.5 py-1 rounded border border-neutral-800 text-neutral-300 bg-neutral-950 font-mono">
          AIR-GAPPED &middot; SENTINEL-2 &middot; EPSG:32645
        </span>

        {/* Model Status Pills */}
        <div className="hidden md:flex items-center gap-2 font-mono">
          <span className="px-2 py-0.5 rounded border border-emerald-900/40 text-emerald-400 bg-emerald-950/20 text-[10px]">
            RemoteCLIP ✓
          </span>
          <span className="px-2 py-0.5 rounded border border-emerald-900/40 text-emerald-400 bg-emerald-950/20 text-[10px]">
            Prithvi-EO ✓
          </span>
          <span className="flex items-center gap-1.5 text-cyan-400 font-bold ml-1">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_8px_#06b6d4] animate-pulse" />
            {status?.offline_mode !== false ? "OFFLINE GRID" : "SECURE LOCAL"}
          </span>
        </div>

        {/* Quick Action / Ingest */}
        {onExportClick && (
          <button
            onClick={onExportClick}
            className="px-3.5 py-1.5 rounded border border-neutral-700 text-neutral-300 hover:border-cyan-500 hover:text-cyan-400 transition-all bg-neutral-950/80 font-sans font-semibold text-xs tracking-widest uppercase"
          >
            EXPORT
          </button>
        )}

        <Link
          href="/ingest"
          className="px-3.5 py-1.5 rounded border border-neutral-700 text-neutral-300 hover:border-emerald-500 hover:text-emerald-400 transition-all bg-neutral-950/80 font-sans font-semibold text-xs tracking-widest uppercase"
        >
          + INGEST
        </Link>
      </div>
    </header>
  );
}
