"use client";

import { SearchResult, thumbnailUrl } from "@/lib/api";

interface Props {
  results: SearchResult[];
  selectedTileId: string | null;
  onSelect: (r: SearchResult) => void;
  placeholderWarning: boolean;
}

function scoreColor(score: number) {
  if (score > 0.7) return "text-emerald-400";
  if (score > 0.4) return "text-amber-400";
  return "text-red-400";
}

export default function ResultsList({ results, selectedTileId, onSelect, placeholderWarning }: Props) {
  return (
    <div className="flex flex-col h-full scanlines">
      <div className="px-3 py-2 border-b border-neutral-800 flex items-center justify-between bg-black">
        <span className="text-xs uppercase tracking-widest text-neutral-500 font-bold">
          Results <span className="text-emerald-500">[{results.length}]</span>
        </span>
        {placeholderWarning && (
          <span className="text-[9px] px-2 py-0.5 rounded-sm bg-amber-950/40 text-amber-500 border border-amber-900/50 uppercase tracking-widest font-mono">
            Placeholder
          </span>
        )}
      </div>
      <div className="flex-1 overflow-y-auto divide-y divide-neutral-900">
        {results.length === 0 && (
          <div className="p-4 text-xs font-mono text-neutral-600 text-center mt-10">AWAITING QUERY...</div>
        )}
        {results.map((r) => (
          <button
            key={r.tile_id}
            onClick={() => onSelect(r)}
            className={`w-full text-left p-3 flex gap-3 hover:bg-neutral-900 transition-all ${
              r.tile_id === selectedTileId ? "bg-neutral-900 border-l-2 border-emerald-500" : "border-l-2 border-transparent"
            }`}
          >
            <div className="w-16 h-16 rounded-sm overflow-hidden bg-black border border-neutral-800 flex-shrink-0 relative">
              {r.thumbnail_path && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={thumbnailUrl(r.thumbnail_path)} alt="tile" className="w-full h-full object-cover filter grayscale-0 hover:grayscale-[20%] transition duration-300" />
              )}
              {r.tile_id === selectedTileId && (
                 <div className="absolute top-0 right-0 w-2 h-2 bg-emerald-500 rounded-bl-sm"></div>
              )}
            </div>
            <div className="flex-1 min-w-0 flex flex-col justify-center">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-neutral-300 truncate uppercase tracking-wide">
                  {r.sensor ?? "UNKNOWN SENSOR"}
                </span>
                <span className={`text-xs font-mono font-bold ${scoreColor(r.final_score)}`}>
                  {r.final_score.toFixed(2)}
                </span>
              </div>
              <div className="text-[10px] text-neutral-500 font-mono mt-1">
                {r.acquisition_date?.slice(0, 10) ?? "DATE UNKNOWN"}
              </div>
              <div className="text-[10px] text-neutral-600 font-mono mt-0.5">
                SIM {r.similarity_score.toFixed(2)} <span className="mx-1 text-neutral-700">|</span> Q {(r.quality_score ?? 0).toFixed(2)}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
