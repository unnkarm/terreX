"use client";

import React, { useState, useEffect } from "react";

export interface AnalysisSettings {
  temporalThreshold: number;
  changeProbabilityThreshold: number;
  changeMapThreshold: number;
  baselineN: number;
  persistenceK: number;
}

export const DEFAULT_ANALYSIS_SETTINGS: AnalysisSettings = {
  temporalThreshold: 0.18,
  changeProbabilityThreshold: 0.5,
  changeMapThreshold: 0.2,
  baselineN: 3,
  persistenceK: 2,
};

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  settings: AnalysisSettings;
  onSave: (newSettings: AnalysisSettings) => void;
}

export default function SettingsModal({
  isOpen,
  onClose,
  settings,
  onSave,
}: SettingsModalProps) {
  const [localSettings, setLocalSettings] = useState<AnalysisSettings>(settings);
  const [activePreset, setActivePreset] = useState<"sensitive" | "balanced" | "strict" | "custom">("balanced");
  const [savedNotice, setSavedNotice] = useState(false);

  useEffect(() => {
    setLocalSettings(settings);
  }, [settings, isOpen]);

  if (!isOpen) return null;

  const applyPreset = (preset: "sensitive" | "balanced" | "strict") => {
    setActivePreset(preset);
    const presets: Record<typeof preset, AnalysisSettings> = {
      sensitive: {
        temporalThreshold: 0.12,
        changeProbabilityThreshold: 0.35,
        changeMapThreshold: 0.12,
        baselineN: 2,
        persistenceK: 2,
      },
      balanced: DEFAULT_ANALYSIS_SETTINGS,
      strict: {
        temporalThreshold: 0.28,
        changeProbabilityThreshold: 0.65,
        changeMapThreshold: 0.35,
        baselineN: 3,
        persistenceK: 3,
      },
    };
    setLocalSettings(presets[preset]);
  };

  const handleSliderChange = (key: keyof AnalysisSettings, val: number) => {
    setActivePreset("custom");
    setLocalSettings((prev) => ({ ...prev, [key]: val }));
  };

  const handleSave = () => {
    onSave(localSettings);
    try {
      window.localStorage.setItem("terrex.changeAnalysisSettings", JSON.stringify(localSettings));
    } catch {
      /* ignore */
    }
    setSavedNotice(true);
    setTimeout(() => {
      setSavedNotice(false);
      onClose();
    }, 600);
  };

  const handleReset = () => {
    setActivePreset("balanced");
    setLocalSettings(DEFAULT_ANALYSIS_SETTINGS);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn select-none font-mono">
      <div className="bg-neutral-950 border border-neutral-800 rounded-lg shadow-2xl max-w-md w-full overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-800 bg-neutral-900/60">
          <div className="flex items-center gap-2.5">
            <span className="w-8 h-8 rounded bg-cyan-950/50 border border-cyan-800/80 flex items-center justify-center text-cyan-400 flex-shrink-0">
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M6 14v6" />
              </svg>
            </span>
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-white flex items-center gap-2">
                GLOBAL ANALYSIS THRESHOLDS
                <span className="text-[9px] px-1.5 py-0.2 rounded bg-cyan-950 border border-cyan-800 text-cyan-400 font-bold">
                  ACTIVE
                </span>
              </h3>
              <p className="text-[9px] text-neutral-400 mt-0.5 tracking-tight">
                Controls change-point sensitivity across all target regions and passes
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-7 h-7 rounded border border-neutral-700 bg-black/60 flex items-center justify-center text-neutral-400 hover:text-white hover:border-neutral-500 transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="p-5 overflow-y-auto space-y-4">
          {/* Presets */}
          <div>
            <span className="block text-[9px] uppercase tracking-wider text-neutral-400 font-bold mb-1.5">
              ANALYSIS PROFILE PRESET
            </span>
            <div className="grid grid-cols-3 gap-2">
              {(["sensitive", "balanced", "strict"] as const).map((preset) => {
                const isActive = activePreset === preset;
                return (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => applyPreset(preset)}
                    className={`py-2 px-1 rounded border text-[10px] uppercase tracking-wider font-bold transition-all ${
                      isActive
                        ? "bg-cyan-950/60 border-cyan-500 text-cyan-300 shadow-[0_0_12px_rgba(6,182,212,0.25)]"
                        : "bg-neutral-900 border-neutral-800 text-neutral-400 hover:text-white hover:border-neutral-700"
                    }`}
                  >
                    {preset}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Continuous Sliders */}
          <div className="space-y-3.5 bg-neutral-900/50 border border-neutral-800 rounded p-3.5">
            {/* Temporal Change Threshold */}
            <label className="block space-y-1.5">
              <div className="flex items-center justify-between text-[10px] uppercase tracking-wider">
                <span className="text-neutral-300 font-bold">Temporal Change Threshold</span>
                <span className="px-2 py-0.5 rounded bg-black border border-neutral-700 text-emerald-400 font-bold text-xs">
                  {localSettings.temporalThreshold.toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                value={localSettings.temporalThreshold}
                min={0.05}
                max={0.5}
                step={0.01}
                onChange={(e) => handleSliderChange("temporalThreshold", Number(e.target.value))}
                className="timeline-scrubber w-full accent-cyan-400"
              />
              <span className="block text-[9px] text-neutral-500">
                Threshold for multi-pass persistence. Lower detects subtler persistent change.
              </span>
            </label>

            {/* Spectral Signal Threshold */}
            <label className="block space-y-1.5">
              <div className="flex items-center justify-between text-[10px] uppercase tracking-wider">
                <span className="text-neutral-300 font-bold">Spectral Signal Threshold</span>
                <span className="px-2 py-0.5 rounded bg-black border border-neutral-700 text-cyan-400 font-bold text-xs">
                  {localSettings.changeProbabilityThreshold.toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                value={localSettings.changeProbabilityThreshold}
                min={0.1}
                max={0.9}
                step={0.05}
                onChange={(e) => handleSliderChange("changeProbabilityThreshold", Number(e.target.value))}
                className="timeline-scrubber w-full accent-cyan-400"
              />
              <span className="block text-[9px] text-neutral-500">
                Controls corroborating spectral signal sensitivity (ΔNDVI, ΔNDBI, ΔNDWI).
              </span>
            </label>

            {/* Change Mask Threshold */}
            <label className="block space-y-1.5">
              <div className="flex items-center justify-between text-[10px] uppercase tracking-wider">
                <span className="text-neutral-300 font-bold">Change Mask Threshold</span>
                <span className="px-2 py-0.5 rounded bg-black border border-neutral-700 text-amber-400 font-bold text-xs">
                  {localSettings.changeMapThreshold.toFixed(2)}
                </span>
              </div>
              <input
                type="range"
                value={localSettings.changeMapThreshold}
                min={0.05}
                max={0.8}
                step={0.05}
                onChange={(e) => handleSliderChange("changeMapThreshold", Number(e.target.value))}
                className="timeline-scrubber w-full accent-cyan-400"
              />
              <span className="block text-[9px] text-neutral-500">
                Binarization cutoff for pixel change mask. Lower includes more pixels and candidate regions.
              </span>
            </label>
          </div>

          {/* Baseline & Persistence Passes */}
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="block text-[9px] text-neutral-400 uppercase tracking-wider font-bold mb-1">
                Baseline Passes (N)
              </span>
              <select
                value={localSettings.baselineN}
                onChange={(e) => handleSliderChange("baselineN", Number(e.target.value))}
                className="w-full bg-neutral-900 border border-neutral-700 rounded px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500 font-bold"
              >
                {[1, 2, 3, 4, 5].map((val) => (
                  <option key={val} value={val}>
                    {val} pass{val > 1 ? "es" : ""}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="block text-[9px] text-neutral-400 uppercase tracking-wider font-bold mb-1">
                Persistence Passes (K)
              </span>
              <select
                value={localSettings.persistenceK}
                onChange={(e) => handleSliderChange("persistenceK", Number(e.target.value))}
                className="w-full bg-neutral-900 border border-neutral-700 rounded px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-cyan-500 font-bold"
              >
                {[2, 3, 4, 5].map((val) => (
                  <option key={val} value={val}>
                    {val} pass{val > 1 ? "es" : ""}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {/* Mode Note */}
          <div className="p-2.5 rounded bg-neutral-900/60 border border-neutral-800/80 flex items-center justify-between text-[10px]">
            <span className="text-neutral-400">
              Dense Mode Minimum:{" "}
              <strong className="text-white">
                {localSettings.baselineN + localSettings.persistenceK} observations
              </strong>
            </span>
            <button
              type="button"
              onClick={handleReset}
              className="text-cyan-400 hover:text-cyan-300 font-bold uppercase tracking-wider text-[9px]"
            >
              Reset Defaults
            </button>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-3 border-t border-neutral-800 bg-neutral-900/40">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-1.5 rounded border border-neutral-700 text-neutral-400 hover:text-white hover:border-neutral-500 text-xs uppercase tracking-wider font-bold transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="px-5 py-1.5 rounded bg-cyan-600 hover:bg-cyan-500 text-black font-bold text-xs uppercase tracking-wider transition-all shadow-[0_0_15px_rgba(6,182,212,0.4)] flex items-center gap-1.5"
          >
            {savedNotice ? "✓ Applied!" : "Save & Apply Globally"}
          </button>
        </div>
      </div>
    </div>
  );
}
