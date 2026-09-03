"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import TopNav from "@/components/TopNav";
import { getSystemStatus, SystemStatus } from "@/lib/api";

export default function DashboardPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    getSystemStatus().then(setStatus).catch(() => {});
  }, []);

  const kpis = [
    { label: "INDEXED TILES", value: "12,842", change: "+1,284 today", highlight: "emerald" },
    { label: "ACQUIRED SCENES", value: "3,421", change: "Sentinel-2 & Landsat", highlight: "cyan" },
    { label: "DATA QUALITY", value: "98.2%", change: "Quality gate Q>0.25", highlight: "emerald" },
    { label: "DETECTED CHANGES", value: "184", change: "Multi-temporal stack", highlight: "amber" },
    { label: "ANALYST REVIEWED", value: "27", change: "100% audit integrity", highlight: "cyan" },
    { label: "CRITICAL ALERTS", value: "12", change: "High urgency queue", highlight: "red" },
  ];

  const recentDiscoveries = [
    {
      type: "NEW CONSTRUCTION",
      candidates: 12,
      trend: "↑ 4 since yesterday",
      hotspot: "Yamuna Riverbank Corridor",
      confidence: "94%",
      color: "amber",
      icon: "🏗️",
      query: "new buildings near river",
    },
    {
      type: "WATER EXTENT VARIATION",
      candidates: 8,
      trend: "Seasonal baseline shift",
      hotspot: "Okhla Wetland Reserve",
      confidence: "88%",
      color: "cyan",
      icon: "💧",
      query: "water extent variation wetland",
    },
    {
      type: "ROAD DEVELOPMENT",
      candidates: 5,
      trend: "↑ 2 new corridor alignments",
      hotspot: "Hindon Canal Link",
      confidence: "91%",
      color: "blue",
      icon: "🛣️",
      query: "road expansion transport corridor",
    },
    {
      type: "VEGETATION CLEARANCE",
      candidates: 7,
      trend: "Near urban boundary",
      hotspot: "Surajpur Reserve Perimeter",
      confidence: "84%",
      color: "orange",
      icon: "🌲",
      query: "cleared vegetation near settlements",
    },
  ];

  const activityFeed = [
    { time: "10:42:15", event: "Automated Siamese pass verified new masonry compound at 28.5684°N, 77.2912°E (94% confidence)", type: "DETECT" },
    { time: "09:18:40", event: "Analyst confirmed Road Expansion candidate #02 (Hindon Link, 2,310 m²)", type: "CONFIRM" },
    { time: "08:55:12", event: "False-alarm suppressed: Cloud shadow transient rejected on scene S2_20260518", type: "SUPPRESS" },
    { time: "07:30:00", event: "Ingested GeoTIFF scene S2B_MSIL2A_20260518_T43RER (64 chips indexed)", type: "INGEST" },
  ];

  return (
    <main className="min-h-screen w-screen bg-black text-neutral-300 font-sans flex flex-col select-none">
      <TopNav status={status} />

      <div className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8 space-y-8">
        
        {/* Page Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b border-neutral-800 pb-8">
          <div className="space-y-3">
            <div className="font-mono text-xs text-radar font-semibold tracking-widest uppercase flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-radar animate-pulse"></span>
              <span>SYSTEM OVERVIEW:</span>
              <span>TELEMETRY ACTIVE</span>
            </div>
            
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-white font-sans leading-[1.1]">
              Geospatial intelligence
              <br />
              <span className="text-neutral-400 font-light">dashboard.</span>
            </h1>

            <p className="text-base text-neutral-300 font-sans font-light max-w-2xl leading-relaxed">
              TerreX pairs high-resolution optical imagery with bitemporal Sentinel SAR radar data under an agentic vision-language model, returning calibrated confidence vectors and verifiable pixel evidence.
            </p>
          </div>

          <div className="flex items-center gap-3 pt-2">
            <Link
              href="/workspace"
              className="px-6 py-3 bg-white text-black font-sans font-semibold text-xs tracking-widest uppercase hover:bg-neutral-200 transition-colors"
            >
              LAUNCH WORKSPACE
            </Link>
            <Link
              href="/review"
              className="px-6 py-3 bg-black text-white font-sans text-xs tracking-widest uppercase border border-neutral-700 hover:border-white transition-colors"
            >
              TRIAGE QUEUE (12)
            </Link>
          </div>
        </div>

        {/* System Overview KPIs Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 font-mono">
          {kpis.map((k, i) => (
            <div key={i} className="p-4 rounded-lg bg-neutral-950 border border-neutral-800/90 space-y-1">
              <span className="text-[9px] uppercase tracking-widest text-neutral-500 font-semibold block">
                {k.label}
              </span>
              <span className={`text-2xl font-bold tracking-tight block font-sans ${
                k.highlight === "emerald" ? "text-emerald-400" :
                k.highlight === "cyan" ? "text-cyan-400" :
                k.highlight === "amber" ? "text-amber-400" :
                k.highlight === "red" ? "text-red-400" : "text-white"
              }`}>
                {k.value}
              </span>
              <span className="text-[10px] text-neutral-400 block truncate font-sans font-light">
                {k.change}
              </span>
            </div>
          ))}
        </div>

        {/* Middle Section: Categorized Recent Discoveries */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg sm:text-xl font-bold tracking-tight text-white font-sans flex items-center gap-2">
              Recent discoveries <span className="text-neutral-400 font-light">&amp; clusters.</span>
            </h2>
            <Link href="/changes" className="text-xs font-sans font-semibold text-cyan-400 hover:text-cyan-300 uppercase tracking-widest">
              WIDE-AREA SCANNER →
            </Link>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 font-mono">
            {recentDiscoveries.map((d, i) => (
              <div
                key={i}
                className="p-5 rounded-lg bg-neutral-950 border border-neutral-800 hover:border-neutral-700 transition-all flex flex-col justify-between space-y-4 group"
              >
                <div>
                  <div className="flex items-start justify-between">
                    <span className="text-2xl">{d.icon}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-neutral-900 border border-neutral-700 text-emerald-400 font-bold">
                      {d.confidence} CONF
                    </span>
                  </div>

                  <h3 className="text-xs font-bold text-white uppercase tracking-wider mt-3">
                    {d.type}
                  </h3>
                  <div className="text-2xl font-black text-neutral-100 mt-1">
                    {d.candidates} <span className="text-xs font-normal text-neutral-500 font-sans">candidates</span>
                  </div>
                  <p className="text-[11px] text-neutral-400 font-sans mt-1">
                    {d.trend}
                  </p>
                </div>

                <div className="pt-3 border-t border-neutral-800/80 space-y-2">
                  <div className="flex justify-between text-[10px] text-neutral-500">
                    <span>HOTSPOT:</span>
                    <span className="text-neutral-300 truncate max-w-[120px]">{d.hotspot}</span>
                  </div>
                  <Link
                    href={`/workspace`}
                    className="block w-full text-center py-1.5 rounded bg-neutral-900 hover:bg-neutral-800 border border-neutral-700 text-cyan-400 text-[10px] uppercase font-bold tracking-wider transition-all"
                  >
                    INSPECT CLUSTER →
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Bottom Section: Hotspot Geospatial Overview & Audit Feed */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 font-mono text-xs">
          
          {/* Geospatial Hotspot Map Card */}
          <div className="lg:col-span-2 p-5 rounded-lg bg-neutral-950 border border-neutral-800 space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-bold text-white font-sans tracking-tight flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                Geospatial hotspots <span className="text-neutral-400 font-light">&middot; NCR Delhi</span>
              </span>
              <span className="text-[10px] text-neutral-500 font-mono">EPSG:32645</span>
            </div>

            <div className="relative h-64 rounded bg-neutral-900 border border-neutral-800 overflow-hidden flex items-center justify-center">
              {/* Tactical Grid Visual Representation */}
              <div className="absolute inset-0 bg-[radial-gradient(#22c55e_1px,transparent_1px)] [background-size:16px_16px] opacity-20" />
              
              {/* Simulated Hotspots Coordinates */}
              <div className="absolute top-16 left-28 p-2 rounded-full bg-amber-500/20 border border-amber-500 flex items-center justify-center animate-pulse">
                <span className="text-[9px] text-amber-300 font-bold">12 Const.</span>
              </div>
              <div className="absolute bottom-20 left-48 p-2 rounded-full bg-cyan-500/20 border border-cyan-500 flex items-center justify-center">
                <span className="text-[9px] text-cyan-300 font-bold">8 Water</span>
              </div>
              <div className="absolute top-24 right-36 p-2 rounded-full bg-blue-500/20 border border-blue-500 flex items-center justify-center">
                <span className="text-[9px] text-blue-300 font-bold">5 Road</span>
              </div>
              <div className="absolute bottom-12 right-24 p-2 rounded-full bg-orange-500/20 border border-orange-500 flex items-center justify-center">
                <span className="text-[9px] text-orange-300 font-bold">7 Clear.</span>
              </div>

              <div className="z-10 text-center space-y-1">
                <p className="font-bold text-white text-sm font-sans tracking-tight">TARGET AOI: NATIONAL CAPITAL REGION (NCR)</p>
                <p className="text-xs text-neutral-400 font-sans font-light">Coverage: 18,420 km² &middot; Optical + SAR Synthetic Grid</p>
                <Link
                  href="/workspace"
                  className="inline-block mt-2 px-4 py-1.5 bg-white text-black font-sans font-semibold text-xs tracking-widest uppercase hover:bg-neutral-200"
                >
                  ENTER LIVE WORKSPACE →
                </Link>
              </div>
            </div>
          </div>

          {/* Real-time Telemetry & Verification Feed */}
          <div className="p-5 rounded-lg bg-neutral-950 border border-neutral-800 space-y-4 flex flex-col justify-between">
            <div className="space-y-3">
              <span className="text-sm font-bold text-white font-sans tracking-tight flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-cyan-400"></span>
                System telemetry <span className="text-neutral-400 font-light">audit.</span>
              </span>

              <div className="space-y-2.5">
                {activityFeed.map((act, idx) => (
                  <div key={idx} className="p-2.5 rounded bg-neutral-900/50 border border-neutral-800/80 space-y-1">
                    <div className="flex items-center justify-between text-[9px]">
                      <span className="text-neutral-500">{act.time}</span>
                      <span className={`font-bold px-1.5 py-0.2 rounded ${
                        act.type === "DETECT" ? "bg-amber-950 text-amber-400" :
                        act.type === "CONFIRM" ? "bg-emerald-950 text-emerald-400" :
                        act.type === "SUPPRESS" ? "bg-cyan-950 text-cyan-400" : "bg-neutral-800 text-neutral-300"
                      }`}>
                        {act.type}
                      </span>
                    </div>
                    <p className="text-[11px] text-neutral-300 font-sans leading-snug">
                      {act.event}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <Link
              href="/review"
              className="block w-full text-center py-2 rounded bg-neutral-900 border border-neutral-700 hover:border-neutral-500 text-neutral-300 text-[10px] uppercase font-bold tracking-wider transition-all mt-4"
            >
              OPEN FULL ANALYST QUEUE →
            </Link>
          </div>

        </div>

      </div>
    </main>
  );
}
