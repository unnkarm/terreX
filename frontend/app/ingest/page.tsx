"use client";

import { useState, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Logo from "@/components/Logo";
import { processIncoming, uploadFileAndIngest } from "@/lib/api";

type Tab = "STATIC" | "REALTIME";

export default function IngestPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<Tab>("STATIC");
  const [isProcessing, setIsProcessing] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [metrics, setMetrics] = useState<any | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const addLog = (msg: string) => {
    setLogs((prev) => [...prev, `[${new Date().toISOString().split("T")[1].slice(0, 8)}] ${msg}`]);
  };

  const handleProcessIncoming = async () => {
    setIsProcessing(true);
    setLogs([]);
    setMetrics(null);
    addLog("INITIATING BATCH INGESTION FROM data/incoming/...");
    try {
      addLog("Scanning local directory for unprocessed GeoTIFFs...");
      const res = await processIncoming();
      setMetrics(res.metrics || null);
      addLog(`SUCCESS: Processed ${res.processed.length} new scene(s).`);
      if (res.metrics) addLog(`METRICS: ${res.metrics.tiles_created} created | ${res.metrics.tiles_skipped} skipped | ${res.metrics.tiles_discarded} discarded | ${res.metrics.elapsed_seconds}s`);
      if (res.skipped?.length) addLog(`INCREMENTAL: Skipped ${res.skipped.length} already-indexed scene(s).`);
      if (res.failed.length > 0) {
        addLog(`WARNING: ${res.failed.length} scenes failed to process.`);
        res.failed.forEach((f: any) => addLog(` -> ${f.file}: ${f.error}`));
      }
      addLog("Database indexing complete. Ready for grid query.");
    } catch (err: any) {
      addLog(`ERROR: ${err.message || "Failed to process incoming directory."}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleFileUpload = async (file: File) => {
    setIsProcessing(true);
    setLogs([]);
    setMetrics(null);
    addLog(`INITIATING UPLOAD & INGESTION FOR: ${file.name}`);
    try {
      addLog("Uploading file to server...");
      addLog("Extracting windowed chips & generating embeddings...");
      const res = await uploadFileAndIngest(file);
      setMetrics({ tiles_created: res.created_tiles ?? res.tiles ?? 0, tiles_skipped: res.skipped_tiles ?? 0, tiles_discarded: res.discarded_tiles ?? 0, elapsed_seconds: res.elapsed_seconds ?? 0 });
      addLog(`SUCCESS: Ingested scene ${res.scene_id} (${res.tiles} tiles created).`);
      addLog(`METRICS: ${res.skipped_tiles || 0} skipped | ${res.discarded_tiles || 0} discarded | ${res.elapsed_seconds || 0}s`);
      addLog(`Avg Quality: ${res.quality_score} | Cloud Fraction: ${res.cloud_fraction}`);
      addLog("Database indexing complete. Ready for grid query.");
    } catch (err: any) {
      addLog(`ERROR: ${err.message || "Upload failed."}`);
    } finally {
      setIsProcessing(false);
    }
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFileUpload(file);
    }
  };

  return (
    <main className="min-h-screen w-screen bg-black text-neutral-300 font-sans relative overflow-hidden flex flex-col scanlines">
      {/* Header */}
      <header className="w-full flex items-center justify-between px-6 py-4 bg-black/60 border-b border-neutral-800 z-50">
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2 group">
            <Logo size={28} showText={true} />
          </Link>
          <span className="text-[10px] uppercase font-mono tracking-[0.2em] px-2 py-0.5 rounded-sm border border-emerald-900/50 text-emerald-500 bg-emerald-950/20">
            INGESTION DASHBOARD
          </span>
        </div>
        <Link
          href="/workspace"
          className="px-4 py-2 rounded-sm border border-neutral-700 text-neutral-400 hover:text-white hover:border-neutral-500 transition-all font-mono text-[10px] tracking-widest uppercase"
        >
          ← CANCEL / RETURN TO GRID
        </Link>
      </header>

      <div className="flex-1 max-w-5xl w-full mx-auto p-8 flex flex-col gap-8 z-10">
        
        {/* Tabs */}
        <div className="flex border-b border-neutral-800 font-mono text-sm uppercase tracking-widest">
          <button
            onClick={() => !isProcessing && setActiveTab("STATIC")}
            disabled={isProcessing}
            className={`px-8 py-4 border-b-2 transition-all ${
              activeTab === "STATIC" ? "border-emerald-500 text-emerald-400 font-bold bg-emerald-950/10" : "border-transparent text-neutral-500 hover:text-neutral-300"
            } ${isProcessing ? "opacity-50 cursor-not-allowed" : ""}`}
          >
            Static Ingestion
          </button>
          <button
            onClick={() => !isProcessing && setActiveTab("REALTIME")}
            disabled={isProcessing}
            className={`px-8 py-4 border-b-2 transition-all ${
              activeTab === "REALTIME" ? "border-cyan-500 text-cyan-400 font-bold bg-cyan-950/10" : "border-transparent text-neutral-500 hover:text-neutral-300"
            } ${isProcessing ? "opacity-50 cursor-not-allowed" : ""}`}
          >
            Real-Time Feed
          </button>
        </div>

        <div className="flex gap-8 flex-1 min-h-0">
          
          {/* Main Action Area */}
          <div className="flex-1 flex flex-col gap-6">
            {activeTab === "STATIC" ? (
              <div className="flex flex-col gap-6 h-full">
                {/* Drag and Drop Zone */}
                <div 
                  className="flex-1 border-2 border-dashed border-neutral-800 hover:border-emerald-500/50 rounded-xl bg-neutral-900/20 flex flex-col items-center justify-center gap-4 transition-colors cursor-pointer group"
                  onClick={() => !isProcessing && fileInputRef.current?.click()}
                >
                  <svg className={`w-12 h-12 text-neutral-600 group-hover:text-emerald-500/80 transition-colors ${isProcessing && "animate-pulse"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <div className="text-center">
                    <p className="font-mono text-emerald-400 font-bold uppercase tracking-widest mb-1">Upload GeoTIFF</p>
                    <p className="text-xs text-neutral-500">Click to browse or drag and drop (.tif, .tiff)</p>
                  </div>
                  <input ref={fileInputRef} type="file" accept=".tif,.tiff,.geotiff" className="hidden" onChange={onFileChange} disabled={isProcessing} />
                </div>

                {/* Local Directory Button */}
                <div className="p-6 border border-neutral-800 rounded-xl bg-black/40 flex items-center justify-between">
                  <div>
                    <h3 className="font-mono text-emerald-400 font-bold uppercase tracking-widest text-sm mb-1">Process Local Directory</h3>
                    <p className="text-xs text-neutral-500">Scan data/incoming/ for unprocessed satellite scenes.</p>
                  </div>
                  <button
                    onClick={handleProcessIncoming}
                    disabled={isProcessing}
                    className="px-6 py-2.5 bg-neutral-900 border border-neutral-700 hover:border-emerald-500 text-neutral-300 hover:text-emerald-400 font-mono text-xs uppercase tracking-widest font-bold rounded-sm transition-all disabled:opacity-50"
                  >
                    {isProcessing ? "PROCESSING..." : "PROCESS DIR"}
                  </button>
                </div>
              </div>
            ) : (
              /* Real-Time Placeholder */
              <div className="flex-1 border border-cyan-900/30 rounded-xl bg-black/40 flex flex-col items-center justify-center gap-6 relative overflow-hidden">
                <div className="absolute inset-0 bg-[linear-gradient(to_bottom,transparent_0%,rgba(6,182,212,0.05)_50%,transparent_100%)] animate-[scan_4s_linear_infinite]" />
                <svg className="w-16 h-16 text-cyan-700/50 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
                </svg>
                <div className="text-center z-10">
                  <p className="font-mono text-cyan-400 font-bold uppercase tracking-widest mb-2">Awaiting Data Link</p>
                  <p className="text-xs text-cyan-700/70 max-w-xs mx-auto">Real-time pipeline from drone swarm / satellite downlink is currently offline or not configured.</p>
                </div>
              </div>
            )}
          </div>

          {/* Terminal / Logs Area */}
          <div className="w-[400px] flex flex-col border border-neutral-800 rounded-xl bg-black/80 overflow-hidden shadow-2xl">
            <div className="px-4 py-2 bg-neutral-900 border-b border-neutral-800 flex items-center justify-between">
              <span className="font-mono text-[10px] text-neutral-500 uppercase tracking-widest">System Logs</span>
              <div className="flex gap-1.5">
                <div className="w-2 h-2 rounded-full bg-red-500/50" />
                <div className="w-2 h-2 rounded-full bg-amber-500/50" />
                <div className="w-2 h-2 rounded-full bg-emerald-500/50" />
              </div>
            </div>
            <div className="flex-1 p-4 font-mono text-[10px] text-emerald-500/70 overflow-y-auto flex flex-col gap-1.5 leading-relaxed">
              {logs.length === 0 ? (
                <span className="text-neutral-700 italic">SYSTEM IDLE. AWAITING INGESTION COMMAND...</span>
              ) : (
                logs.map((log, i) => (
                  <div key={i} className={`${log.includes("ERROR") || log.includes("WARNING") ? "text-amber-500" : log.includes("SUCCESS") ? "text-emerald-400 font-bold" : ""}`}>
                    {log}
                  </div>
                ))
              )}
              {isProcessing && (
                <div className="animate-pulse mt-2 flex items-center gap-2">
                  <div className="w-1.5 h-3 bg-emerald-500" />
                  <span>PROCESSING...</span>
                </div>
              )}
            </div>

            {metrics && (
              <div className="grid grid-cols-2 gap-px border-t border-neutral-800 bg-neutral-800">
                <Metric label="TILES CREATED" value={metrics.tiles_created ?? 0} />
                <Metric label="TILES SKIPPED" value={metrics.tiles_skipped ?? 0} />
                <Metric label="TILES DISCARDED" value={metrics.tiles_discarded ?? 0} />
                <Metric label="ELAPSED" value={`${metrics.elapsed_seconds ?? 0}s`} />
              </div>
            )}
            
            {/* Proceed Button (Enabled only if logs indicate success and not processing) */}
            <div className="p-4 border-t border-neutral-800 bg-neutral-900/30">
              <button
                onClick={() => router.push("/workspace")}
                disabled={isProcessing || logs.length === 0}
                className="w-full py-3 bg-emerald-900/40 border border-emerald-700 hover:bg-emerald-800 hover:border-emerald-400 text-emerald-400 font-mono text-xs uppercase tracking-widest font-bold rounded-sm transition-all disabled:opacity-30 disabled:hover:bg-emerald-900/40 disabled:hover:border-emerald-700"
              >
                PROCEED TO GRID →
              </button>
            </div>
          </div>

        </div>
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="bg-black px-3 py-2"><div className="font-mono text-[9px] uppercase tracking-wider text-neutral-600">{label}</div><div className="mt-1 font-mono text-sm text-emerald-400">{value}</div></div>;
}
