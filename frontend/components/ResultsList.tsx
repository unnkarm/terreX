"use client";

import { SearchResult, thumbnailUrl } from "@/lib/api";

interface Props {
  results: SearchResult[];
  selectedTileId: string | null;
  onSelect: (r: SearchResult) => void;
  placeholderWarning: boolean;
}

function scoreColor(score: number) {
  if (score > 0.7) return "text-ok";
  if (score > 0.4) return "text-warn";
  return "text-danger";
}

export default function ResultsList({ results, selectedTileId, onSelect, placeholderWarning }: Props) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-gray-800 flex items-center justify-between">
        <span className="text-xs uppercase tracking-wide text-gray-500 font-medium">
          Results ({results.length})
        </span>
        {placeholderWarning && (
          <span className="text-[10px] px-2 py-0.5 rounded bg-warn/20 text-warn border border-warn/40">
            placeholder embeddings
          </span>
        )}
      </div>
      <div className="flex-1 overflow-y-auto divide-y divide-gray-800">
        {results.length === 0 && (
          <div className="p-4 text-sm text-gray-500">Run a search to see ranked results here.</div>
        )}
        {results.map((r) => (
          <button
            key={r.tile_id}
            onClick={() => onSelect(r)}
            className={`w-full text-left p-3 flex gap-3 hover:bg-panel2 transition-colors ${
              r.tile_id === selectedTileId ? "bg-panel2 border-l-2 border-accent" : ""
            }`}
          >
            <div className="w-16 h-16 rounded overflow-hidden bg-gray-800 flex-shrink-0">
              {r.thumbnail_path && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={thumbnailUrl(r.thumbnail_path)} alt="tile" className="w-full h-full object-cover" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-100 truncate">
                  {r.sensor ?? "Unknown sensor"}
                </span>
                <span className={`text-sm font-semibold ${scoreColor(r.final_score)}`}>
                  {r.final_score.toFixed(2)}
                </span>
              </div>
              <div className="text-xs text-gray-500">
                {r.acquisition_date?.slice(0, 10) ?? "date unknown"} · {r.lat.toFixed(4)}, {r.lon.toFixed(4)}
              </div>
              <div className="text-xs text-gray-500">
                similarity {r.similarity_score.toFixed(2)} · quality {(r.quality_score ?? 0).toFixed(2)}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
