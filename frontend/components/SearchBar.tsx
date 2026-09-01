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
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 relative">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && query.trim() && onTextSearch(query.trim())}
          placeholder='Search satellite imagery… e.g. "new buildings near a river"'
          className="w-full bg-panel2 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-accent/60"
        />
      </div>
      <button
        onClick={() => query.trim() && onTextSearch(query.trim())}
        disabled={loading}
        className="px-4 py-2.5 rounded-lg bg-accent/90 hover:bg-accent text-black text-sm font-medium disabled:opacity-50"
      >
        {loading ? "Searching…" : "Search"}
      </button>
      <button
        onClick={() => fileInputRef.current?.click()}
        disabled={loading}
        className="px-4 py-2.5 rounded-lg border border-gray-700 hover:border-gray-500 text-sm text-gray-300"
        title="Search by reference image"
      >
        Image search
      </button>
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
