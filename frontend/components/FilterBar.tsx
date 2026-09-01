"use client";

import { FilterState } from "@/lib/api";

interface Props {
  filters: FilterState;
  onChange: (f: FilterState) => void;
  sensors: string[];
}

export default function FilterBar({ filters, onChange, sensors }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-gray-400">
      <span className="uppercase tracking-wide text-gray-500 font-medium">Filters</span>

      <div className="flex items-center gap-1.5">
        <span>Date</span>
        <input
          type="date"
          value={filters.dateFrom ?? ""}
          onChange={(e) => onChange({ ...filters, dateFrom: e.target.value })}
          className="bg-panel2 border border-gray-700 rounded px-2 py-1 text-gray-200"
        />
        <span>→</span>
        <input
          type="date"
          value={filters.dateTo ?? ""}
          onChange={(e) => onChange({ ...filters, dateTo: e.target.value })}
          className="bg-panel2 border border-gray-700 rounded px-2 py-1 text-gray-200"
        />
      </div>

      <div className="flex items-center gap-1.5">
        <span>Sensor</span>
        <select
          value={filters.sensor ?? ""}
          onChange={(e) => onChange({ ...filters, sensor: e.target.value || undefined })}
          className="bg-panel2 border border-gray-700 rounded px-2 py-1 text-gray-200"
        >
          <option value="">Any</option>
          {sensors.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-1.5">
        <span>Min. similarity</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={filters.minSimilarity ?? 0}
          onChange={(e) => onChange({ ...filters, minSimilarity: parseFloat(e.target.value) })}
        />
        <span className="w-8 text-right">{(filters.minSimilarity ?? 0).toFixed(2)}</span>
      </div>
    </div>
  );
}
