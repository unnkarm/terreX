"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { ChangeObservation, thumbnailUrl } from "@/lib/api";

interface Props {
  onSelectDate?: (date: string, observation?: ChangeObservation) => void;
  earliestDate?: string; registrationConfidence?: number; observations?: ChangeObservation[];
  confirmedDate?: string; uncertaintyDays?: number; persistenceStatus?: string;
}

const dayGap = (a: ChangeObservation, b: ChangeObservation) =>
  Math.round((new Date(b.acquisition_date).getTime() - new Date(a.acquisition_date).getTime()) / 86400000);

export default function ChangeTimeline({ onSelectDate, earliestDate, registrationConfidence,
  observations = [], confirmedDate, uncertaintyDays, persistenceStatus }: Props) {
  const nodes = useMemo(() => [...observations].sort((a, b) =>
    new Date(a.acquisition_date).getTime() - new Date(b.acquisition_date).getTime()), [observations]);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const axisRef = useRef<HTMLDivElement>(null);
  const needsScroll = nodes.length > 10;

  const select = (idx: number) => {
    if (!nodes.length) return;
    const next = Math.max(0, Math.min(nodes.length - 1, idx));
    setSelectedIdx(next);
    onSelectDate?.(nodes[next].date_formatted, nodes[next]);
  };

  useEffect(() => {
    const early = nodes.findIndex((node) => node.is_earliest_change);
    const next = early >= 0 ? early : Math.max(0, nodes.length - 1);
    setSelectedIdx(next);
    if (nodes[next]) onSelectDate?.(nodes[next].date_formatted, nodes[next]);
  }, [earliestDate, nodes]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!playing || nodes.length < 2) return;
    const timer = window.setInterval(() => setSelectedIdx((current) => {
      const next = (current + 1) % nodes.length;
      onSelectDate?.(nodes[next].date_formatted, nodes[next]);
      return next;
    }), 1250);
    return () => window.clearInterval(timer);
  }, [playing, nodes, onSelectDate]);

  useEffect(() => {
    if (!needsScroll) return;
    axisRef.current?.querySelector<HTMLElement>(`[data-axis-index="${selectedIdx}"]`)?.scrollIntoView({
      behavior: playing ? "smooth" : "auto", block: "nearest", inline: "center",
    });
  }, [selectedIdx, needsScroll, playing]);

  if (!nodes.length) return <div className="p-4 bg-neutral-900 border border-neutral-800 rounded font-mono text-[11px] text-neutral-400">Select an AOI to load its actual acquisition dates.</div>;

  const selected = nodes[selectedIdx] || nodes[0];
  const timelineWidth = needsScroll ? Math.max(620, nodes.length * 58) : undefined;
  const displayEarliest = earliestDate?.slice(0, 10) || nodes.find((n) => n.is_earliest_change)?.date_formatted;
  const displayConfirmed = confirmedDate?.slice(0, 10) || nodes.find((n) => n.is_persistence_confirmation)?.date_formatted;

  return <div className="space-y-3.5 p-3.5 bg-neutral-900/90 border border-neutral-800/80 backdrop-blur-xl rounded shadow-2xl font-mono text-xs select-none">
    <div className="flex items-center justify-between gap-3 border-b border-neutral-800/80 pb-3">
      <div className="flex items-center gap-2.5 min-w-0">
        <button type="button" onClick={() => setPlaying((value) => !value)}
          className={`w-9 h-9 rounded flex items-center justify-center border transition-all flex-shrink-0 ${playing ? "bg-emerald-500 border-emerald-300 text-black shadow-[0_0_14px_rgba(52,211,153,0.28)]" : "bg-emerald-950/40 border-emerald-700/70 text-emerald-400 hover:bg-emerald-900/50 hover:border-emerald-500"}`}
          aria-label={playing ? "Pause timeline" : "Play timeline"}>
          {playing ? <svg className="w-3.5 h-3.5" viewBox="0 0 16 16" fill="currentColor"><path d="M3 2h3v12H3zm7 0h3v12h-3z" /></svg> : <svg className="w-3.5 h-3.5 ml-0.5" viewBox="0 0 16 16" fill="currentColor"><path d="M4 2.5v11l9-5.5z" /></svg>}
        </button>
        <div className="min-w-0">
          <div className="font-bold text-white uppercase tracking-wider truncate">Acquisition Timeline</div>
          <div className="text-[9px] text-neutral-500 tracking-wide">SCRUB OR AUTO-PLAY · 1.25S / FRAME</div>
        </div>
      </div>
      <span className="px-2 py-1 rounded border border-emerald-900/80 bg-emerald-950/30 text-[9px] font-bold tracking-wider text-emerald-400 whitespace-nowrap">{nodes.length} PASSES</span>
    </div>

    <div className="flex items-center justify-between gap-3 text-[9px] uppercase tracking-wider">
      <div className="flex gap-3 text-neutral-400">
        <span className="flex items-center gap-1.5"><i className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_5px_rgba(34,211,238,0.5)]" />Optical · S2</span>
        <span className="flex items-center gap-1.5"><i className="w-2 h-2 rotate-45 bg-fuchsia-400" />Radar · S1 SAR</span>
      </div>
      <span className="text-neutral-600">UTC</span>
    </div>

    <div ref={axisRef} className={needsScroll ? "overflow-x-auto pb-1 timeline-axis-scroll" : "overflow-hidden"}>
      <div className="relative h-[78px]" style={timelineWidth ? { minWidth: `${timelineWidth}px` } : undefined}>
        <div className="absolute top-[31px] h-px bg-neutral-700" style={{ left: `${50 / nodes.length}%`, right: `${50 / nodes.length}%` }} />
        <div className="absolute top-[31px] h-px bg-emerald-500/70 transition-all duration-300"
          style={{ left: `${50 / nodes.length}%`, width: `${nodes.length > 1 ? (selectedIdx / (nodes.length - 1)) * (100 - 100 / nodes.length) : 0}%` }} />
        <div className="grid h-full" style={{ gridTemplateColumns: `repeat(${nodes.length}, minmax(0, 1fr))` }}>
        {nodes.map((node, index) => {
          const gap = index ? dayGap(nodes[index - 1], node) : 0;
          const sar = node.modality === "sar" || /sar|radar/i.test(node.sensor);
          const active = index === selectedIdx;
          return <div key={`${node.tile_id}-${index}`} className="relative h-full flex justify-center">
            {gap >= 5 && gap <= 7 && <span className="absolute top-0 left-0 -translate-x-1/2 whitespace-nowrap text-[8px] text-emerald-300 bg-emerald-950/90 border border-emerald-800/80 rounded px-1.5 py-px z-10">{gap}D</span>}
            <button type="button" data-axis-index={index} onClick={() => select(index)} title={`${node.date_formatted} · ${node.sensor}`}
              className={`absolute top-[24px] left-1/2 -translate-x-1/2 w-[15px] h-[15px] border-2 transition-all duration-200 z-10 ${sar ? "rotate-45 bg-fuchsia-500 border-fuchsia-200" : "rounded-full bg-cyan-500 border-cyan-200"} ${active ? "ring-4 ring-emerald-400/20 scale-125 shadow-[0_0_10px_rgba(52,211,153,0.65)]" : "opacity-70 hover:opacity-100 hover:scale-110"}`} />
            <span className={`absolute top-[52px] left-1/2 -translate-x-1/2 text-[8px] whitespace-nowrap tracking-wide ${active ? "text-white font-bold" : "text-neutral-500"}`}>{node.date_formatted.slice(5)}</span>
          </div>;
        })}
        </div>
      </div>
    </div>

    <div className="flex items-center gap-2">
      <span className="text-[8px] text-neutral-600">T0</span>
      <input type="range" min={0} max={nodes.length - 1} step={1} value={selectedIdx} onChange={(event) => select(Number(event.target.value))} className="timeline-scrubber flex-1" aria-label="Scrub acquisition date" />
      <span className="text-[8px] text-neutral-600">T{nodes.length - 1}</span>
    </div>

    <div className="relative aspect-[16/8.5] overflow-hidden rounded border border-neutral-700/80 bg-black shadow-inner">
      {selected.thumbnail_url ? <>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img key={selected.tile_id} src={thumbnailUrl(selected.thumbnail_url)} alt={`${selected.sensor} acquisition on ${selected.date_formatted}`} className="w-full h-full object-cover animate-fadeIn" />
        <div className="absolute inset-x-0 top-0 h-12 bg-gradient-to-b from-black/55 to-transparent" />
        <div className="absolute top-2 left-2 px-1.5 py-0.5 rounded-sm bg-black/70 border border-white/10 text-[8px] tracking-wider text-neutral-300">FRAME {String(selectedIdx + 1).padStart(2, "0")} / {String(nodes.length).padStart(2, "0")}</div>
        <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 bg-gradient-to-t from-black via-black/80 to-transparent px-3 pt-10 pb-2.5 text-[9px]">
          <div><span className="block text-neutral-500 text-[8px] tracking-wider">ACQUIRED</span><span className="font-bold text-white text-[10px]">{selected.date_formatted}</span></div>
          <span className={`font-bold tracking-wider text-right ${selected.modality === "sar" ? "text-fuchsia-300" : "text-cyan-300"}`}>{selected.sensor} · {selected.modality === "sar" ? "RADAR" : "OPTICAL"}</span>
        </div>
      </> : <div className="h-full flex flex-col items-center justify-center gap-1 text-neutral-600 text-[9px] tracking-wider"><span className="w-6 h-6 rounded border border-neutral-800 flex items-center justify-center">×</span>PREVIEW UNAVAILABLE</div>}
    </div>

    <div className="bg-neutral-950 rounded border border-neutral-800 overflow-hidden">
      <div className="flex items-center justify-between gap-3 px-3 py-2 border-b border-neutral-800/80">
        <div className="flex items-center gap-2"><span className="font-bold text-white">{selected.date_formatted}</span><span className={`px-1.5 py-0.5 rounded border text-[8px] font-bold ${selected.modality === "sar" ? "text-fuchsia-300 bg-fuchsia-950/40 border-fuchsia-900" : "text-cyan-300 bg-cyan-950/40 border-cyan-900"}`}>{selected.sensor}</span></div>
        <div className="flex items-center gap-3 text-[9px]"><span className="text-neutral-500">CLOUD <strong className="text-neutral-200">{Math.round((selected.cloud_fraction || 0) * 100)}%</strong></span><span className="text-neutral-500">QUALITY <strong className="text-emerald-400">{Math.round((selected.quality_score || 0) * 100)}%</strong></span></div>
      </div>
      <div className="grid grid-cols-4 gap-px bg-neutral-800/80 text-center">
        {([['NDVI', selected.mean_ndvi, 'text-emerald-400'], ['NDWI', selected.mean_ndwi, 'text-cyan-400'], ['NDBI', selected.mean_ndbi, 'text-amber-400'], ['Δ BASE', selected.distance_from_baseline, 'text-purple-400']] as [string, number | null | undefined, string][]).map(([label, value, color]) => <div key={label} className="bg-neutral-950 px-1 py-2.5"><div className="text-[8px] text-neutral-500 tracking-wider">{label}</div><div className={`font-bold text-[11px] mt-0.5 ${color}`}>{typeof value === "number" ? value.toFixed(2) : "N/A"}</div></div>)}
      </div>
    </div>

    {displayEarliest && displayConfirmed ? <div className="flex items-center justify-between gap-3 text-[9px] text-emerald-300 bg-emerald-950/25 border border-emerald-900/70 rounded px-2.5 py-2"><span className="font-bold tracking-wider">● CONFIRMED CHANGE</span><span className="text-right">{displayEarliest} → {displayConfirmed} · ±{uncertaintyDays?.toFixed(1) ?? "N/A"}D · REG {registrationConfidence ?? "N/A"}%</span></div> : persistenceStatus && <div className="flex items-center justify-between gap-3 text-[9px] bg-neutral-950/60 border border-neutral-800 rounded px-2.5 py-2"><span className="text-neutral-500 tracking-wider">PERSISTENCE STATUS</span><span className={`font-bold uppercase tracking-wider ${persistenceStatus === "ok" ? "text-emerald-400" : "text-neutral-300"}`}>{persistenceStatus.replaceAll("_", " ")}</span></div>}
  </div>;
}
