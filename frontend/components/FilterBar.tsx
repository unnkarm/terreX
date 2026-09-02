"use client";

import { FilterState } from "@/lib/api";

interface Props {
  filters: FilterState;
  onChange: (f: FilterState) => void;
  sensors: string[];
}

export default function FilterBar({ filters, onChange, sensors }: Props) {
  return (
    <div className="flex flex-wrap items-center justify-center gap-4 text-[10px] text-neutral-400 font-mono tracking-widest uppercase bg-neutral-900/60 backdrop-blur-sm px-4 py-1.5 rounded-full border border-neutral-800/50">
      <div className="flex items-center gap-2">
        <span className="text-neutral-500">DATE</span>
        <input
          type="date"
          value={filters.dateFrom ?? ""}
          onChange={(e) => onChange({ ...filters, dateFrom: e.target.value })}
          className="bg-transparent border-none text-emerald-100 focus:outline-none focus:ring-0 cursor-pointer"
        />
        <span className="text-neutral-600">-</span>
        <input
          type="date"
          value={filters.dateTo ?? ""}
          onChange={(e) => onChange({ ...filters, dateTo: e.target.value })}
          className="bg-transparent border-none text-emerald-100 focus:outline-none focus:ring-0 cursor-pointer"
        />
      </div>

      <div className="w-px h-3 bg-neutral-700/50" />

      <div className="flex items-center gap-2">
        <span className="text-neutral-500">SENSOR</span>
        <select
          value={filters.sensor ?? ""}
          onChange={(e) => onChange({ ...filters, sensor: e.target.value || undefined })}
          className="bg-transparent border-none text-emerald-100 focus:outline-none focus:ring-0 uppercase cursor-pointer"
        >
          <option value="" className="bg-neutral-900">ANY</option>
          {sensors.map((s) => (
            <option key={s} value={s} className="bg-neutral-900">{s}</option>
          ))}
        </select>
      </div>

      <div className="w-px h-3 bg-neutral-700/50" />

      <div className="flex items-center gap-2">
        <span className="text-neutral-500">MIN. SIM</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={filters.minSimilarity ?? 0}
          onChange={(e) => onChange({ ...filters, minSimilarity: parseFloat(e.target.value) })}
          className="w-20 accent-emerald-500 h-1 bg-neutral-800 rounded-full appearance-none cursor-pointer"
        />
        <span className="w-6 text-right text-emerald-400 font-bold">{(filters.minSimilarity ?? 0).toFixed(2)}</span>
      </div>
    </div>
  );
}
