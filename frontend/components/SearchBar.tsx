"use client";

import React, { useState, useRef } from "react";

import { ParsedFilters } from "@/lib/api";

export type SearchMode = "semantic" | "image";

interface Props {
  onTextSearch: (q: string) => void;
  onImageSearch: (file: File) => void;
  onModeChange?: (mode: SearchMode) => void;
  activeMode?: SearchMode;
  loading?: boolean;
  parsedFilters?: ParsedFilters | null;
  activeSensor?: string;
  suggestions?: string[];
}

export default function SearchBar({
  onTextSearch,
  onImageSearch,
  onModeChange,
  activeMode,
  loading,
  parsedFilters,
  activeSensor,
  suggestions: customSuggestions,
}: Props) {
  const [query, setQuery] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [internalMode, setInternalMode] = useState<SearchMode>("semantic");
  const [selectedFileName, setSelectedFileName] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const currentMode = activeMode ?? internalMode;

  const defaultSuggestions = [
    "water bodies and rivers",
    "flooded agricultural land and terrain",
    "new buildings and urban development",
    "dense vegetation and forest cover",
    "industrial infrastructure and roads",
  ];
  const suggestions = customSuggestions && customSuggestions.length > 0 ? customSuggestions : defaultSuggestions;

  const handleRunQuery = (text: string) => {
    setQuery(text);
    onTextSearch(text);
    setIsFocused(false);
  };

  const modes: { id: SearchMode; label: string }[] = [
    { id: "semantic", label: "Semantic Text" },
    { id: "image", label: "Reference Chip" },
  ];

  const handleModeChange = (mode: SearchMode) => {
    setInternalMode(mode);
    onModeChange?.(mode);
  };

  return (
    <div className="flex max-h-[46vh] min-h-[220px] flex-col gap-2.5 overflow-y-auto w-full bg-neutral-950 border border-neutral-800 rounded-lg p-3 font-sans text-xs">
      {/* Search Mode Switcher (Semantic vs Image) */}
      <div className="flex items-center gap-1 border-b border-neutral-800/80 pb-2">
        {modes.map((m) => {
          const isSelected = currentMode === m.id;
          return (
            <button
              key={m.id}
              onClick={() => handleModeChange(m.id)}
              className={`flex-1 py-1.5 px-2 rounded font-sans text-xs uppercase tracking-widest font-semibold transition-all text-center ${
                isSelected
                  ? "bg-white text-black shadow-sm"
                  : "text-neutral-400 hover:text-neutral-200 border border-transparent"
              }`}
            >
              {m.label}
            </button>
          );
        })}
      </div>

      {/* Mode Description / Prompt Header */}
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 font-sans font-bold text-white tracking-tight text-xs">
          <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          {currentMode === "semantic" ? (
            <span>What are you <span className="text-neutral-400 font-light">looking for?</span></span>
          ) : (
            <span>Upload reference <span className="text-neutral-400 font-light">optical / SAR chip</span></span>
          )}
        </span>
        <span className="text-[9px] font-mono text-cyan-400 font-semibold uppercase tracking-wider">
          REMOTECLIP &middot; {activeSensor ? activeSensor.toUpperCase() : "ALL SENSORS"}
        </span>
      </div>

      {/* Semantic Input */}
      {currentMode === "semantic" && (
        <div className="space-y-2.5">
          <div className="relative flex items-center bg-black border border-neutral-800 rounded focus-within:border-white focus-within:ring-1 focus-within:ring-white/30 transition-all">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onFocus={() => setIsFocused(true)}
              onKeyDown={(e) => e.key === "Enter" && query.trim() && handleRunQuery(query.trim())}
              placeholder='e.g. "large new structures within 5km of rivers after January 2024"'
              className="flex-1 bg-transparent px-3 py-2 text-xs text-white placeholder-neutral-500 outline-none font-sans font-light"
            />

            <button
              onClick={() => query.trim() && handleRunQuery(query.trim())}
              disabled={loading}
              className="m-1 px-4 py-2 rounded bg-white text-black font-sans font-semibold text-xs tracking-widest uppercase hover:bg-neutral-200 transition-colors disabled:opacity-50 shadow-md"
            >
              {loading ? "SEARCHING..." : "SEARCH"}
            </button>
          </div>



          {/* 1-Click Suggestions */}
          <div className="space-y-1">
            <span className="text-[9px] font-mono uppercase tracking-widest text-neutral-500 block">
              SUGGESTED INTENTS (SENTINEL-2):
            </span>
            <div className="flex flex-wrap gap-1">
              {suggestions.map((s, idx) => (
                <button
                  key={idx}
                  onClick={() => handleRunQuery(s)}
                  className="text-[10px] text-left px-2 py-1 rounded bg-neutral-900/80 border border-neutral-800/80 text-neutral-300 hover:text-white hover:border-neutral-600 transition-all font-sans font-light"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Image Search Mode */}
      {currentMode === "image" && (
        <div
          onClick={() => fileInputRef.current?.click()}
          className="border-2 border-dashed border-neutral-800 hover:border-emerald-500/60 rounded p-6 text-center cursor-pointer transition-colors bg-black/40 group"
        >
          <svg className="w-8 h-8 text-neutral-600 group-hover:text-emerald-400 mx-auto mb-2 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          <p className="font-sans text-xs text-white font-semibold uppercase tracking-wider">
            Upload Optical Reference Chip
          </p>
          <p className="text-[10px] text-neutral-400 font-sans font-light mt-1">
            PNG, JPEG, or Sentinel-2 GeoTIFF / COG
          </p>
          {selectedFileName && (
            <p className="mt-2 truncate text-[10px] text-emerald-400 font-mono" title={selectedFileName}>
              READY: {selectedFileName}
            </p>
          )}
        </div>
      )}

      {/* Hidden File Input */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,.tif,.tiff,.geotiff"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) {
            setSelectedFileName(f.name);
            onImageSearch(f);
          }
          e.target.value = "";
        }}
      />
    </div>
  );
}
