"use client";

import { useRef, useState } from "react";

interface Props {
  onTextSearch: (query: string) => void;
  onImageSearch: (file: File) => void;
  loading: boolean;
}

export default function SearchBar({ onTextSearch, onImageSearch, loading }: Props) {
  const [query, setQuery] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  return (
    <div className="relative flex items-center w-full bg-neutral-900/80 backdrop-blur-md border border-neutral-700/50 rounded-full shadow-lg p-1.5 transition-all focus-within:border-emerald-600/60 focus-within:ring-1 focus-within:ring-emerald-600/30">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && query.trim() && onTextSearch(query.trim())}
        placeholder='ENTER QUERY... E.G. "NEW BUILDINGS NEAR A RIVER"'
        className="flex-1 bg-transparent border-none px-4 py-2 text-sm text-emerald-100 placeholder-neutral-500 focus:outline-none font-mono tracking-wide"
      />
      
      <div className="flex items-center gap-2 pr-1">
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={loading}
          className="p-2 rounded-full bg-neutral-800/50 hover:bg-neutral-700 border border-transparent hover:border-neutral-500 text-neutral-400 transition-all flex items-center justify-center disabled:opacity-50"
          title="Upload Reference Image"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
        </button>
        <button
          onClick={() => query.trim() && onTextSearch(query.trim())}
          disabled={loading}
          className="px-4 py-2 rounded-full bg-emerald-900/40 border border-emerald-800/50 hover:bg-emerald-800/60 hover:border-emerald-500 text-emerald-400 text-[11px] uppercase tracking-widest font-mono font-bold transition-all disabled:opacity-50"
        >
          {loading ? "..." : "SEARCH ↵"}
        </button>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,.tif,.tiff,.geotiff"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onImageSearch(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}
