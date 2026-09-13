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
        {/* Model Status Pills */}
        <div className="hidden md:flex items-center gap-2 font-mono">
          <span className={`px-2 py-0.5 rounded border text-[10px] transition-colors ${
            status?.models?.remoteclip?.staged
              ? "border-emerald-900/40 text-emerald-400 bg-emerald-950/20"
              : "border-neutral-800 text-neutral-500 bg-neutral-950"
          }`}>
            RemoteCLIP {status?.models?.remoteclip?.staged ? "✓" : "✗"}
          </span>
          <span className={`px-2 py-0.5 rounded border text-[10px] transition-colors ${
            status?.models?.prithvi?.staged
              ? "border-emerald-900/40 text-emerald-400 bg-emerald-950/20"
              : "border-neutral-800 text-neutral-500 bg-neutral-950"
          }`}>
            Prithvi-EO {status?.models?.prithvi?.staged ? "✓" : "✗"}
          </span>
          <span className={`flex items-center gap-1.5 px-2 py-0.5 rounded border text-[10px] transition-colors ml-1 ${
            status?.offline_mode !== false
              ? "border-emerald-900/40 text-emerald-400 bg-emerald-950/20"
              : "border-neutral-800 text-neutral-500 bg-neutral-950"
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${status?.offline_mode !== false ? 'bg-emerald-400 shadow-[0_0_8px_#34d399] animate-pulse' : 'bg-neutral-600'}`} />
            OFFLINE {status?.offline_mode !== false ? "✓" : "✗"}
          </span>
        </div>

        {/* Quick Action / Ingest */}
        {onExportClick && (
          <button
            onClick={onExportClick}
            className="px-3.5 py-1.5 rounded border border-neutral-700 text-neutral-300 hover:border-emerald-500 hover:text-emerald-400 transition-all bg-neutral-950/80 font-sans font-semibold text-xs tracking-widest uppercase"
          >
            EXPORT
          </button>
        )}
      </div>
    </header>
  );
}
