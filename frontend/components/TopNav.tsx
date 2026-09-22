"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Logo from "@/components/Logo";
import { SystemStatus } from "@/lib/api";

interface TopNavProps {
  status?: SystemStatus | null;
  onExportClick?: () => void;
  onSettingsClick?: () => void;
}

export default function TopNav({ status, onExportClick, onSettingsClick }: TopNavProps) {
  const pathname = usePathname();

  const navLinks = [
    { href: "/workspace", label: "WORKSPACE" },
    { href: "/ingest", label: "INGESTION PIPELINE" },
  ];

  return (
    <header className="h-12 border-b border-neutral-800/80 bg-black/90 backdrop-blur px-4 flex items-center justify-between select-none z-50">
      {/* Left: Branding & Core Navigation */}
      <div className="flex items-center gap-6">
        <Logo size={28} />

        <nav className="flex items-center gap-1">
          {navLinks.map((link) => {
            const isActive = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`px-3 py-1 rounded text-xs font-sans font-semibold tracking-wider transition-colors ${
                  isActive
                    ? "bg-neutral-800 text-white border border-neutral-700"
                    : "text-neutral-400 hover:text-neutral-200 hover:bg-neutral-900"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Right: Telemetry & Actions */}
      <div className="flex items-center gap-3">
        {/* Offline & Model Diagnostics */}
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

        {/* Global Settings & Export Actions */}
        <div className="flex items-center gap-2">
          {onSettingsClick && (
            <button
              type="button"
              onClick={onSettingsClick}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-neutral-700 text-neutral-300 hover:border-cyan-500 hover:text-cyan-400 transition-all bg-neutral-950/80 font-sans font-semibold text-xs tracking-widest uppercase"
              title="Global Analysis Thresholds Settings"
            >
              <svg className="w-3.5 h-3.5 text-cyan-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M6 14v6" />
              </svg>
              SETTINGS
            </button>
          )}

          {onExportClick && (
            <button
              type="button"
              onClick={onExportClick}
              className="px-3.5 py-1.5 rounded border border-neutral-700 text-neutral-300 hover:border-emerald-500 hover:text-emerald-400 transition-all bg-neutral-950/80 font-sans font-semibold text-xs tracking-widest uppercase"
            >
              EXPORT
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
