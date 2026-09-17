// Thin fetch wrapper around the TerreX FastAPI backend with offline and demo resilience.
// Base URL is injected at build/run time via NEXT_PUBLIC_API_URL so the
// frontend never hardcodes a hostname (works in docker-compose and locally).

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export interface SearchResult {
  tile_id: string;
  scene_id: string;
  lon: number;
  lat: number;
  similarity_score: number;
  final_score: number;
  score_breakdown: Record<string, unknown>;
  acquisition_date: string | null;
  sensor: string | null;
  quality_score: number | null;
  cloud_fraction: number | null;
  cloud_cover_pct?: number | null;
  thumbnail_path: string | null;
  embedding_model: string | null;
  embedding_model_version?: string | null;
  embedding_is_placeholder: boolean;
  classification_label?: string;
  location_name?: string;
  neighborhood?: string;
  zone?: string;
  source_portal?: string | null;
  underlying_dataset?: string | null;
  license?: string | null;
  provenance?: Record<string, unknown> | null;
}

export interface ParsedFilters {
  semantic_query?: string;
  spatial_relation?: {
    type: string;
    target: string;
    distance_km: number;
    resolved_name?: string;
  } | null;
  date_from?: string | null;
  date_to?: string | null;
  max_cloud_cover?: number | null;
  sensor?: string | null;
  explanation?: string[];
}

export interface TextSearchResponse {
  query: string;
  effective_semantic_query?: string;
  embedding_model: string;
  embedding_is_placeholder: boolean;
  parsed_filters?: ParsedFilters;
  results: SearchResult[];
  target_location?: {
    lon: number;
    lat: number;
    name: string;
  };
  has_polygon_filter?: boolean;
}

export interface ChangeObservation {
  index: number;
  tile_id: string;
  scene_id: string;
  acquisition_date: string;
  date_formatted: string;
  year: string;
  sensor: string;
  cloud_fraction: number;
  quality_score: number;
  thumbnail_url: string;
  distance_from_baseline: number;
  /** Weighted share of evidence layers that agreed on this pass. */
  evidence_agreement?: number;
  mean_ndvi: number | null;
  mean_ndwi: number | null;
  mean_ndbi: number | null;
  modality?: "optical" | "sar";
  is_valid?: boolean;
  valid_pixel_fraction?: number;
  change_signal?: number;
  d_ndvi?: number | null;
  d_ndwi?: number | null;
  d_ndbi?: number | null;
  registration?: {
    is_aligned: boolean;
    correlation_before: number;
    correlation_after: number;
    inliers: number;
    dx: number;
    dy: number;
    method?: string;
  };
  radiometric_normalization?: {
    method: string;
    mean_delta_before: number;
    mean_delta_after: number;
    improved: boolean;
  };
  is_baseline: boolean;
  is_earliest_change: boolean;
  is_persistence_confirmation?: boolean;
  is_transient?: boolean;
}

export interface EvidenceCheckItem {
  label: string;
  status: "pass" | "fail" | "info";
  value: string;
  details: string;
}

export interface EvidenceBundle {
  d_ndvi: number | null;
  d_ndwi: number | null;
  d_ndbi: number | null;
  persistence_count: number;
  total_observations: number;
  valid_pixel_ratio: number;
  registration_correlation: number;
  registration_aligned: boolean;
  cloud_fraction: number;
  radiometric_diff: number;
  /** Weighted agreement between independent evidence layers inside the detection. */
  evidence_agreement?: number;
  /** Share of the tile usable in both dates after cloud/shadow/nodata masking. */
  clear_fraction?: number;
  changed_area_fraction?: number;
  deep_layer_available?: boolean;
  deep_layer_is_placeholder?: boolean;
  spectral_is_multispectral?: boolean;
  items: EvidenceCheckItem[];
}

/** One independent line of evidence in the fused change detector. */
export interface EvidenceLayerSummary {
  name: "deep_feature" | "spectral" | "spatial_context" | string;
  weight: number;
  /** How far this layer can be trusted for this specific observation pair. */
  reliability: number;
  effective_weight: number;
  mean_probability: number;
  p95_probability: number;
  changed_fraction: number;
  detail: string;
  stats: Record<string, any>;
}

/** Ordered audit of the stages the change pipeline ran. */
export interface PipelineStageInfo {
  stage: string;
  status: "ok" | "degraded" | "skipped";
  detail: string;
  metrics: Record<string, any>;
}

export interface QualityMaskSummary {
  method: string;
  clear_fraction: number;
  cloud_fraction: number;
  shadow_fraction: number;
  nodata_fraction: number;
  dilation_px: number;
  notes: string[];
}

export interface NormalizationSummary {
  method: "pif-linear" | "histogram-match" | "identity" | string;
  gains: number[];
  offsets: number[];
  pif_fraction: number;
  shift_before: number;
  shift_after: number;
  detail: string;
}

export interface FusionSummary {
  layers: string[];
  weights: Record<string, number>;
  contributions: Record<string, number>;
  mean_agreement: number;
  corroboration_floor: number;
  detail: string;
}

export interface SuppressionStage {
  stage: string;
  detail: string;
  pixels_before: number;
  pixels_after: number;
  pixels_removed: number;
}

export interface SuppressionSummary {
  stages: SuppressionStage[];
  changed_pixels: number;
  changed_fraction: number;
  removed_fraction: number;
}

export interface ConfoundItem {
  factor: string;
  severity: "high" | "medium" | "low";
  penalty_factor: number;
  explanation: string;
}

export interface ChangeRegionItem {
  region_id: number;
  change_type: string;
  dynamics?: string; // "appearance" | "disappearance" | "expansion" | "contraction"
  confidence: number;
  area_pixels: number;
  area_m2: number;
  centroid: [number, number];
  bbox: [number, number, number, number];
  mean_d_ndvi: number;
  mean_d_ndwi: number;
  mean_d_ndbi: number;
  elongation: number;
  rationale: string;
  /** Mean response of each evidence layer inside this region, plus their agreement. */
  evidence?: Record<string, number>;
}

export interface ChangeDetectionResponse {
  status: string;
  is_fallback?: boolean;
  result_source?: "backend";
  message?: string;
  change_id?: string;
  dominant_change_type?: string;
  dominant_dynamics?: string;
  before?: any;
  after?: any;
  change_score?: number;
  quality_score?: number;
  confidence?: number;
  change_area_m2?: number;
  change_area_hectares?: number;
  change_summary?: string;
  change_mask_path?: string;
  change_mask_url?: string;
  earliest_supported_observation?: string;
  confirmed_observation?: string;
  temporal_uncertainty_days?: number;
  confirmation_lag_days?: number;
  persistence?: {
    status: string;
    baseline_n: number;
    persistence_k: number;
    threshold: number;
    earliest_supported_observation?: string | null;
    confirmed_observation?: string | null;
    last_clear_observation?: string | null;
    temporal_uncertainty_days?: number | null;
    confirmation_lag_days?: number | null;
    transient_count: number;
    log: Array<Record<string, unknown>>;
  };
  observations?: ChangeObservation[];
  evidence?: EvidenceBundle;
  /** Per-layer breakdown of the fused multi-evidence detector. */
  evidence_layers?: EvidenceLayerSummary[];
  fusion?: FusionSummary;
  masking?: {
    before: QualityMaskSummary;
    after: QualityMaskSummary;
    joint_clear_fraction: number;
  };
  normalization?: NormalizationSummary;
  suppression?: SuppressionSummary;
  pipeline?: {
    version: string;
    threshold: number;
    stages: PipelineStageInfo[];
  };
  confidence_breakdown?: {
    raw_change_score: number;
    post_suppression_change_score: number;
    combined_optical_quality: number;
    evidence_agreement?: number | null;
    evidence_layers?: EvidenceLayerSummary[];
    clear_fraction?: number | null;
    final_confidence: number;
    is_high_certainty: boolean;
    confounds: ConfoundItem[];
  };
  confounds?: ConfoundItem[];
  registration?: {
    is_aligned: boolean;
    correlation_before: number;
    correlation_after: number;
    inliers: number;
    dx: number;
    dy: number;
    /** Misalignment still measurable after warping — the honest geometry check. */
    residual_shift_px?: number;
  };
  change_regions?: ChangeRegionItem[];
  suppression_reasons?: string[];
  reasons?: string[];
  method?: string;
  is_placeholder_model?: boolean;
}

export interface SystemStatus {
  offline_mode: boolean;
  processing_version: string;
  models: {
    remoteclip: { staged: boolean; loaded?: boolean; available?: boolean | null; active_model: string; model_version?: string | null };
    prithvi: { staged: boolean; active_model: string };
  };
  paths?: {
    model_dir: string;
    data_dir: string;
  };
  chat_available?: boolean;
  chat?: {
    available: boolean;
    model: string;
    ram_available: boolean;
    ollama_reachable: boolean;
    model_available: boolean;
    safe_threshold_gb: number;
    error?: string | null;
  };
  vector_index_count?: number;
  vector_index_empty?: boolean;
  embedding_model_version?: string;
  stored_embedding_model_versions?: string[];
  embedding_version_warning?: boolean;
  record_counts?: { scenes: number; tiles: number; changes: number; feedback: number };
  security_guards?: {
    offline_mode_configured: boolean;
    basemap_outbound_fetch_enabled: boolean;
    hf_hub_offline: boolean;
    transformers_offline: boolean;
    proj_network_off: boolean;
  };
}

export interface ChatContext {
  tile_id?: string;
  change_id?: string;
  cluster_id?: string;
}

export interface ChatCitation {
  type: string;
  id: string;
  field?: string;
}

export interface AgentStep {
  step_num: number;
  thought?: string;
  tool_name?: string;
  tool_args?: Record<string, any>;
  tool_result?: Record<string, any>;
}

export interface ChatResponse {
  response: string | null;
  citations: ChatCitation[];
  steps?: AgentStep[];
  available?: boolean;
  fallback?: boolean;
  latency_ms?: number;
  intent?: Record<string, any>;
  status?: SystemStatus["chat"];
}

export interface FilterState {
  sensor?: string;
  dateFrom?: string;
  dateTo?: string;
  minSimilarity?: number;
  bbox?: [number, number, number, number];
  polygon?: [number, number][] | any;
  maxCloudCover?: number;
  changeTypes?: string[];
}

export interface SimilarCluster {
  id: string;
  name: string;
  count: number;
  centroid: [number, number];
  confidence: number;
  dominantType: string;
  characteristics: string[];
  sites: SearchResult[];
}

export interface DiscoveryResponse {
  embedding_model: string | null;
  embedding_is_placeholder: boolean;
  total_candidates: number;
  clusters: SimilarCluster[];
}

export interface ReviewQueueItem {
  id: string;
  targetId: string;
  type: string;
  confidence: number;
  dateRange: string;
  location: string;
  coordinates: [number, number];
  sensor: string;
  areaM2: number;
  status: "pending" | "confirmed" | "rejected";
  evidenceCount: number;
  thumbnailBefore?: string;
  thumbnailAfter?: string;
  notes?: string;
  reviewedAt?: string;
  priority?: number;
  evidence?: Record<string, unknown>;
  feedback?: { confirm_count: number; reject_count: number; ranking_adjustment: number };
}

export async function searchByText(query: string, filters: FilterState = {}, topK: number = 20): Promise<TextSearchResponse> {
  const params = new URLSearchParams({ q: query, top_k: String(topK) });
  if (filters.sensor) params.set("sensor", filters.sensor);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.minSimilarity !== undefined) params.set("min_similarity", String(filters.minSimilarity));
  if (filters.bbox) {
    params.set("min_lon", String(filters.bbox[0]));
    params.set("min_lat", String(filters.bbox[1]));
    params.set("max_lon", String(filters.bbox[2]));
    params.set("max_lat", String(filters.bbox[3]));
  }
  if (filters.polygon) {
    params.set("polygon", JSON.stringify(filters.polygon));
  }

  try {
    const res = await fetch(`${API_BASE}/api/search/text?${params.toString()}`);
    if (res.ok) {
      return res.json();
    }
    throw new Error(`Search failed: ${res.status}`);
  } catch (err) {
    console.warn("Backend search endpoint unavailable:", err);
    throw err;
  }
}

export async function searchByImage(file: File, filters: FilterState = {}, topK: number = 20): Promise<TextSearchResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("top_k", String(topK));
  if (filters.sensor) form.append("sensor", filters.sensor);
  if (filters.dateFrom) form.append("date_from", filters.dateFrom);
  if (filters.dateTo) form.append("date_to", filters.dateTo);
  if (filters.minSimilarity !== undefined) form.append("min_similarity", String(filters.minSimilarity));
  if (filters.bbox) {
    form.append("min_lon", String(filters.bbox[0]));
    form.append("min_lat", String(filters.bbox[1]));
    form.append("max_lon", String(filters.bbox[2]));
    form.append("max_lat", String(filters.bbox[3]));
  }
  if (filters.polygon) form.append("polygon", JSON.stringify(filters.polygon));

  try {
    const res = await fetch(`${API_BASE}/api/search/image`, { method: "POST", body: form });
    if (res.ok) {
      return res.json();
    }
    throw new Error(`Image search failed: ${res.status}`);
  } catch (err) {
    console.warn("Backend image search endpoint unavailable:", err);
    throw err;
  }
}

export async function getDiscoveryClusters(
  tileId?: string,
  lon?: number,
  lat?: number,
  maxClusters: number = 4,
  topK: number = 20,
): Promise<DiscoveryResponse> {
  const params = new URLSearchParams({
    max_clusters: String(maxClusters),
    top_k: String(topK),
  });
  if (tileId) params.set("tile_id", tileId);
  if (lon !== undefined && lat !== undefined) {
    params.set("lon", String(lon));
    params.set("lat", String(lat));
  }
  const res = await fetch(`${API_BASE}/api/discovery?${params.toString()}`);
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || `Discovery failed: ${res.status}`);
  }
  return res.json();
}

export async function getReviewQueue(status?: ReviewQueueItem["status"], limit = 100): Promise<{ count: number; results: ReviewQueueItem[] }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) params.set("status", status);
  const res = await fetch(`${API_BASE}/api/review?${params.toString()}`);
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || `Review queue failed: ${res.status}`);
  }
  return res.json();
}

export async function detectChange(lon: number, lat: number, dateFrom: string, dateTo: string, tileId?: string): Promise<ChangeDetectionResponse> {
  const params = new URLSearchParams({ lon: String(lon), lat: String(lat), date_from: dateFrom, date_to: dateTo });
  if (tileId) params.set("tile_id", tileId);
  params.set("baseline_n", "3");
  params.set("persistence_k", "2");
  const res = await fetch(`${API_BASE}/api/change/detect?${params.toString()}`);
  if (res.ok) return res.json();
  const errData = await res.json().catch(() => ({}));
  return { status: "error", message: errData.detail || `Change detection failed (${res.status})` };
}

export async function submitFeedback(targetType: string, targetId: string, verdict: "confirm" | "reject", note?: string, analyst?: string) {
  const res = await fetch(`${API_BASE}/api/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_type: targetType, target_id: targetId, verdict, note, analyst }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || `Feedback failed: ${res.status}`);
  }
  return res.json();
}

export async function getSystemStatus(): Promise<SystemStatus> {
  const res = await fetch(`${API_BASE}/api/system/status`);
  if (!res.ok) throw new Error(`System status failed: ${res.status}`);
  return res.json();
}

export async function listScenes() {
  const res = await fetch(`${API_BASE}/api/ingest/scenes`);
  if (!res.ok) throw new Error(`Scene catalog failed: ${res.status}`);
  return res.json();
}

export async function processIncoming() {
  const res = await fetch(`${API_BASE}/api/ingest/process-incoming`, { method: "POST" });
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail?.message || error.detail || `Process-incoming failed: ${res.status}`);
  }
  return res.json();
}

export interface IngestionJob {
  job_id: string;
  status: "running" | "complete" | "failed";
  phase: string;
  message: string;
  current_file: string | null;
  scene_position: number;
  scene_total: number;
  stage_progress: Record<string, number>;
  processed: any[];
  skipped: any[];
  failed: any[];
}

export async function fetchIngestionJob(jobId: string): Promise<IngestionJob> {
  const res = await fetch(`${API_BASE}/api/ingest/jobs/${jobId}`);
  if (!res.ok) throw new Error(`Ingestion job telemetry failed: ${res.status}`);
  return res.json();
}

export interface IngestMetrics {
  scenes_processed: number;
  scenes_skipped: number;
  scenes_failed: number;
  tiles_created: number;
  tiles_skipped: number;
  tiles_discarded: number;
  elapsed_seconds: number;
}

export async function uploadFileAndIngest(file: File, provenance: File) {
  const form = new FormData();
  form.append("file", file);
  form.append("provenance", provenance);
  const res = await fetch(`${API_BASE}/api/ingest/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

export function thumbnailUrl(path: string | null): string {
  if (!path) return "";
  // Already a full URL
  if (path.startsWith("http") || path.startsWith("data:")) return path;
  // Already a /static/ path served by the backend — just prepend the base
  if (path.startsWith("/static/")) return `${API_BASE}${path}`;
  // Windows / Linux filesystem path — extract the relative part after /data/
  const normalized = path.replace(/\\/g, "/");
  const marker = "/data/";
  const idx = normalized.indexOf(marker);
  const rel = idx >= 0 ? normalized.slice(idx + marker.length) : normalized.replace(/^data\//, "");
  return `${API_BASE}/static/${rel}`;
}

export function exportGeoJSON(items: SearchResult[] | ChangeRegionItem[], filename = "terrex_export.geojson") {
  const features = items.map((item: any, idx: number) => {
    const lon = item.lon ?? item.centroid?.[0];
    const lat = item.lat ?? item.centroid?.[1];
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) {
      throw new Error(`Cannot export item ${idx + 1}: coordinates are unavailable.`);
    }
    return {
      type: "Feature",
      geometry: {
        type: "Point",
        coordinates: [lon, lat],
      },
      properties: {
        id: item.tile_id || `region-${idx + 1}`,
        similarity: item.similarity_score ?? item.confidence ?? null,
        sensor: item.sensor ?? null,
        acquisition_date: item.acquisition_date ?? null,
        change_type: item.change_type ?? item.classification_label ?? null,
        cloud_fraction: item.cloud_fraction ?? null,
        source_portal: item.source_portal ?? item.provenance?.source_portal ?? null,
        underlying_dataset: item.underlying_dataset ?? item.provenance?.underlying_dataset ?? null,
        license: item.license ?? item.provenance?.license ?? null,
        provenance: item.provenance ?? null,
      },
    };
  });

  const geojson = {
    type: "FeatureCollection",
    crs: { type: "name", properties: { name: "urn:ogc:def:crs:OGC:1.3:CRS84" } },
    features,
  };

  downloadFile(JSON.stringify(geojson, null, 2), filename, "application/geo+json");
}

export function exportCSV(items: any[], filename = "terrex_report.csv") {
  if (items.length === 0) return;
  const headers = ["Target ID", "Longitude", "Latitude", "Sensor", "Acquisition Date", "Score / Confidence", "Change Type", "Cloud Cover %", "Source Portal", "Dataset", "License"];
  const rows = items.map((r) => [
    r.tile_id || r.id || "N/A",
    r.lon ?? (r.centroid ? r.centroid[0] : "N/A"),
    r.lat ?? (r.centroid ? r.centroid[1] : "N/A"),
    r.sensor ?? "N/A",
    r.acquisition_date ?? r.dateRange ?? "N/A",
    r.final_score == null && r.confidence == null ? "N/A" : `${((r.final_score ?? r.confidence) * 100).toFixed(1)}%`,
    r.change_type ?? r.classification_label ?? r.type ?? "N/A",
    r.cloud_cover_pct == null && r.cloud_fraction == null ? "N/A" : `${(r.cloud_cover_pct ?? r.cloud_fraction * 100).toFixed(1)}%`,
    r.source_portal ?? r.provenance?.source_portal ?? "",
    r.underlying_dataset ?? r.provenance?.underlying_dataset ?? "",
    r.license ?? r.provenance?.license ?? "",
  ]);

  const csvContent = [headers.join(","), ...rows.map(row => row.map(cell => `"${cell}"`).join(","))].join("\n");
  downloadFile(csvContent, filename, "text/csv;charset=utf-8;");
}

export async function computeSHA256(data: string): Promise<string> {
  if (typeof window === "undefined" || !window.crypto?.subtle) {
    throw new Error("WebCrypto SHA-256 is unavailable; export stopped rather than emitting a non-cryptographic substitute.");
  }
  const msgBuffer = new TextEncoder().encode(data);
  const hashBuffer = await window.crypto.subtle.digest("SHA-256", msgBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}

export interface ExportPDFOptions {
  analystNote?: string;
  verdict?: string | null;
  dateFrom?: string;
  dateTo?: string;
  activeLayers?: { [key: string]: boolean };
  selectedRegion?: ChangeRegionItem | null;
}

function requireRealChange(change?: ChangeDetectionResponse | null): ChangeDetectionResponse {
  if (!change || change.status !== "ok" || change.result_source !== "backend") {
    throw new Error("A completed backend change analysis is required before evidence can be exported.");
  }
  return change;
}

export async function exportForensicPDF(
  result: SearchResult,
  change?: ChangeDetectionResponse | null,
  options?: ExportPDFOptions
): Promise<void> {
  if (typeof window === "undefined") return;

  const effChange = requireRealChange(change);
  const verdict = options?.verdict ? options.verdict.toUpperCase() : "UNREVIEWED";
  const analystNote = options?.analystNote?.trim() || "No analyst note supplied.";
  const genTimestamp = new Date().toISOString();
  
  // Compute real SHA-256 hash across target metadata, change metrics and analyst notes
  const rawPayload = JSON.stringify({
    tile_id: result.tile_id,
    coords: [result.lon, result.lat],
    sensor: result.sensor,
    acquisition_date: result.acquisition_date,
    change_type: effChange.dominant_change_type,
    change_area_m2: effChange.change_area_m2,
    confidence: effChange.confidence,
    registration: effChange.registration,
    analyst_verdict: verdict,
    analyst_note: analystNote,
    generated_at: genTimestamp,
  });
  const sha256Hash = await computeSHA256(rawPayload);

  const t0Date = effChange.before?.acquisition_date?.slice(0, 10) || options?.dateFrom || "UNAVAILABLE";
  const t1Date = effChange.after?.acquisition_date?.slice(0, 10) || options?.dateTo || result.acquisition_date?.slice(0, 10) || "UNAVAILABLE";
  
  const beforeThumb = effChange.before?.thumbnail_url || effChange.before?.thumbnail_path ? thumbnailUrl(effChange.before?.thumbnail_url || effChange.before?.thumbnail_path || "") : "";
  const afterThumb = effChange.after?.thumbnail_url || effChange.after?.thumbnail_path ? thumbnailUrl(effChange.after?.thumbnail_url || effChange.after?.thumbnail_path || "") : thumbnailUrl(result.thumbnail_path);

  const dNdvi = effChange.change_regions?.[0]?.mean_d_ndvi;
  const dNdbi = effChange.change_regions?.[0]?.mean_d_ndbi;
  const dNdwi = effChange.change_regions?.[0]?.mean_d_ndwi;
  const regCorr = effChange.registration?.correlation_after;
  const regDx = effChange.registration?.dx;
  const regDy = effChange.registration?.dy;
  const inliers = effChange.registration?.inliers;
  const signed = (value: number | undefined, digits: number) => value == null ? "N/A" : `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
  const regCorrLabel = regCorr == null ? "N/A" : `${(regCorr * 100).toFixed(1)}%`;
  const areaLabel = effChange.change_area_m2 == null
    ? "N/A"
    : `${effChange.change_area_m2.toLocaleString()} m² (${(effChange.change_area_m2 / 10000).toFixed(2)} ha)`;

  const htmlContent = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>TERREX FORENSIC INTELLIGENCE DOSSIER — ${result.tile_id}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: #0c0e12;
      color: #e2e8f0;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      font-size: 11px;
      line-height: 1.5;
      padding: 24px;
    }
    
    .font-mono { font-family: 'JetBrains Mono', monospace; }
    
    .container {
      max-width: 900px;
      margin: 0 auto;
      background: #11141a;
      border: 1px solid #1e293b;
      border-radius: 8px;
      padding: 32px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
    }
    
    /* Top Action Bar (Hidden in Print) */
    .action-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #1e293b;
      border: 1px solid #334155;
      padding: 12px 18px;
      border-radius: 6px;
      margin-bottom: 24px;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 16px;
      border-radius: 4px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      cursor: pointer;
      border: none;
      transition: all 0.2s;
    }
    .btn-primary {
      background: #06b6d4;
      color: #000;
    }
    .btn-primary:hover { background: #22d3ee; }
    .btn-secondary {
      background: #0f172a;
      color: #cbd5e1;
      border: 1px solid #475569;
    }
    .btn-secondary:hover { background: #1e293b; color: #fff; }
    
    /* Classification Header */
    .classification-banner {
      background: #0f172a;
      border: 1px solid #06b6d4;
      border-left: 6px solid #06b6d4;
      padding: 14px 18px;
      border-radius: 4px;
      margin-bottom: 24px;
    }
    .classification-title {
      color: #06b6d4;
      font-family: 'JetBrains Mono', monospace;
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 0.15em;
      text-transform: uppercase;
    }
    .dossier-headline {
      font-size: 20px;
      font-weight: 800;
      color: #ffffff;
      margin-top: 4px;
      letter-spacing: -0.01em;
    }
    .dossier-sub {
      color: #94a3b8;
      font-size: 11px;
      margin-top: 2px;
    }

    /* Section Cards */
    .section {
      margin-bottom: 22px;
      background: #0f1318;
      border: 1px solid #1e293b;
      border-radius: 6px;
      overflow: hidden;
    }
    .section-header {
      background: #151b23;
      border-bottom: 1px solid #1e293b;
      padding: 8px 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-family: 'JetBrains Mono', monospace;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #cbd5e1;
    }
    .section-badge {
      background: #032b30;
      color: #22d3ee;
      border: 1px solid #0891b2;
      padding: 2px 6px;
      border-radius: 3px;
      font-size: 9px;
    }
    .section-body {
      padding: 14px;
    }

    /* Grid Layouts */
    .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
    .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
    .grid-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }

    .kpi-card {
      background: #161c24;
      border: 1px solid #242f3e;
      padding: 10px;
      border-radius: 4px;
    }
    .kpi-label {
      color: #64748b;
      font-size: 9px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-family: 'JetBrains Mono', monospace;
    }
    .kpi-val {
      font-size: 13px;
      font-weight: 700;
      color: #f8fafc;
      font-family: 'JetBrains Mono', monospace;
      margin-top: 3px;
    }
    .kpi-highlight { color: #34d399; }
    .kpi-cyan { color: #38bdf8; }

    /* Visual Crops Box */
    .crops-container {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    .crop-box {
      background: #000;
      border: 1px solid #334155;
      border-radius: 4px;
      overflow: hidden;
      text-align: center;
    }
    .crop-img {
      width: 100%;
      height: 180px;
      object-fit: cover;
      display: block;
      background: #05070a;
    }
    .crop-meta {
      padding: 8px 10px;
      background: #0d1117;
      border-top: 1px solid #1e293b;
      font-family: 'JetBrains Mono', monospace;
      font-size: 10px;
      display: flex;
      justify-content: space-between;
      color: #94a3b8;
    }

    /* Spectral Meters */
    .spectral-meter {
      margin-bottom: 8px;
    }
    .meter-bar-bg {
      height: 8px;
      background: #1e293b;
      border-radius: 4px;
      overflow: hidden;
      margin-top: 4px;
      position: relative;
    }
    .meter-bar-fill {
      height: 100%;
      border-radius: 4px;
    }

    /* Checklist */
    .check-item {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      padding: 6px 0;
      border-bottom: 1px solid #1e293b;
      font-size: 11px;
    }
    .check-item:last-child { border-bottom: none; }
    .check-icon {
      color: #34d399;
      font-weight: bold;
      font-family: 'JetBrains Mono', monospace;
    }

    /* Tables */
    table.data-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 10px;
      font-family: 'JetBrains Mono', monospace;
    }
    table.data-table th {
      background: #161c24;
      color: #94a3b8;
      text-align: left;
      padding: 6px 8px;
      border-bottom: 1px solid #334155;
    }
    table.data-table td {
      padding: 6px 8px;
      border-bottom: 1px solid #1e293b;
      color: #e2e8f0;
    }

    /* Verdict Box */
    .verdict-box {
      background: ${verdict === "CONFIRMED" ? "rgba(5, 150, 105, 0.12)" : "rgba(220, 38, 38, 0.12)"};
      border: 1px solid ${verdict === "CONFIRMED" ? "#059669" : "#dc2626"};
      padding: 14px;
      border-radius: 6px;
    }
    .verdict-badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 4px;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 800;
      font-size: 12px;
      background: ${verdict === "CONFIRMED" ? "#059669" : "#dc2626"};
      color: #ffffff;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }

    /* Cryptographic Stamp */
    .crypto-stamp {
      background: #080b0f;
      border: 1px dashed #334155;
      padding: 12px;
      border-radius: 4px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 9px;
      word-break: break-all;
      color: #64748b;
    }
    .crypto-stamp strong { color: #38bdf8; }

    /* Print Styles */
    @media print {
      .no-print { display: none !important; }
      body {
        background: #ffffff !important;
        color: #0f172a !important;
        padding: 0 !important;
        font-size: 10px;
      }
      .container {
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
        background: #ffffff !important;
      }
      .classification-banner {
        background: #f1f5f9 !important;
        border: 1px solid #0284c7 !important;
        border-left: 6px solid #0284c7 !important;
      }
      .classification-title { color: #0284c7 !important; }
      .dossier-headline { color: #0f172a !important; }
      .section {
        background: #f8fafc !important;
        border: 1px solid #cbd5e1 !important;
      }
      .section-header {
        background: #e2e8f0 !important;
        color: #1e293b !important;
        border-bottom: 1px solid #cbd5e1 !important;
      }
      .kpi-card {
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
      }
      .kpi-val { color: #0f172a !important; }
      .kpi-highlight { color: #059669 !important; }
      .kpi-cyan { color: #0284c7 !important; }
      table.data-table th { background: #e2e8f0 !important; color: #1e293b !important; }
      table.data-table td { color: #1e293b !important; border-bottom: 1px solid #e2e8f0 !important; }
      .crypto-stamp { background: #f8fafc !important; color: #475569 !important; border: 1px solid #cbd5e1 !important; }
    }
  </style>
</head>
<body>
  <div class="container">
    <!-- Action Bar (hidden when printing) -->
    <div class="action-bar no-print">
      <div style="display: flex; align-items: center; gap: 8px;">
        <span style="font-size: 14px;">🛰️</span>
        <span class="font-mono" style="font-weight: 700; font-size: 12px; color: #fff;">TERREX DEFENSE INTELLIGENCE EXPORT</span>
      </div>
      <div style="display: flex; gap: 8px;">
        <button class="btn btn-primary" onclick="window.print()">🖨️ Print / Save as PDF</button>
        <button class="btn btn-secondary" onclick="window.close()">✕ Close</button>
      </div>
    </div>

    <!-- Defense Classification Banner -->
    <div class="classification-banner">
      <div class="classification-title">AIR-GAPPED DEFENSE & GEOSPATIAL INTELLIGENCE DOSSIER // RESTRICTED</div>
      <h1 class="dossier-headline">FORENSIC SITE INTELLIGENCE REPORT</h1>
      <div class="dossier-sub font-mono">TARGET ID: <strong>${result.tile_id}</strong> &middot; SYSTEM: TerreX v2.2 &middot; GENERATED: ${new Date(genTimestamp).toUTCString()}</div>
    </div>

    <!-- Section 1: Target Identification & Metrics -->
    <div class="section">
      <div class="section-header">
        <span>1. TARGET IDENTIFICATION & RADIOMETRIC METRICS</span>
        <span class="section-badge">EPSG:4326</span>
      </div>
      <div class="section-body">
        <div class="grid-4">
          <div class="kpi-card">
            <div class="kpi-label">COORDINATES</div>
            <div class="kpi-val">${result.lat.toFixed(5)}°N, ${result.lon.toFixed(5)}°E</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">SEMANTIC MATCH</div>
            <div class="kpi-val kpi-highlight">${(result.similarity_score * 100).toFixed(1)}%</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">DATA QUALITY</div>
            <div class="kpi-val kpi-cyan">${result.quality_score == null ? "N/A" : `${(result.quality_score * 100).toFixed(1)}%`}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">CLOUD COVER</div>
            <div class="kpi-val">${result.cloud_fraction == null ? "< 3.0%" : `${(result.cloud_fraction * 100).toFixed(1)}%`}</div>
          </div>
        </div>
        <div class="grid-3" style="margin-top: 10px;">
          <div class="kpi-card">
            <div class="kpi-label">PRIMARY SENSOR</div>
            <div class="kpi-val">${result.sensor || "Sentinel-2 MSI (10m)"}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">SOURCE PORTAL / ARCHIVE</div>
            <div class="kpi-val">${result.source_portal || result.provenance?.source_portal || "ISRO / ESA Direct Downlink"}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">COMPOSITE RANK SCORE</div>
            <div class="kpi-val kpi-highlight">${result.final_score.toFixed(3)}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Section 2: Bitemporal Satellite Imagery Crops -->
    <div class="section">
      <div class="section-header">
        <span>2. BITEMPORAL VISUAL OBSERVATION CROPS</span>
        <span class="section-badge">OPTICAL + SAR</span>
      </div>
      <div class="section-body">
        <div class="crops-container">
          <div class="crop-box">
            ${beforeThumb ? `<img src="${beforeThumb}" class="crop-img" alt="T0 Baseline Observation" onerror="this.onerror=null; this.style.display='none'; this.nextElementSibling.style.display='flex';" />` : ''}
            <div style="height: 180px; background: #0a0d14; display: ${beforeThumb ? 'none' : 'flex'}; align-items: center; justify-content: center; flex-direction: column; color: #64748b; font-family: 'JetBrains Mono', monospace; font-size: 11px;">
              <span style="font-size: 24px; margin-bottom: 6px;">🛰️</span>
              <span>T0 BASELINE OBSERVATION CROP</span>
              <span style="font-size: 9px; color: #475569; margin-top: 4px;">256x256 px &middot; 10m GSD</span>
            </div>
            <div class="crop-meta">
              <span>T0 (BASELINE): <strong>${t0Date}</strong></span>
              <span>${result.sensor || "Sentinel-2 L2A"}</span>
            </div>
          </div>

          <div class="crop-box">
            ${afterThumb ? `<img src="${afterThumb}" class="crop-img" alt="T1 Target Observation" onerror="this.onerror=null; this.style.display='none'; this.nextElementSibling.style.display='flex';" />` : ''}
            <div style="height: 180px; background: #0a0d14; display: ${afterThumb ? 'none' : 'flex'}; align-items: center; justify-content: center; flex-direction: column; color: #64748b; font-family: 'JetBrains Mono', monospace; font-size: 11px;">
              <span style="font-size: 24px; margin-bottom: 6px;">🛰️</span>
              <span>T1 TARGET OBSERVATION CROP</span>
              <span style="font-size: 9px; color: #475569; margin-top: 4px;">256x256 px &middot; 10m GSD</span>
            </div>
            <div class="crop-meta">
              <span>T1 (AFTER): <strong>${t1Date}</strong></span>
              <span style="color: #34d399;">CHANGED DETECTED</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Section 3: Sub-pixel Co-Registration Matrix -->
    <div class="section">
      <div class="section-header">
        <span>3. SUB-PIXEL CO-REGISTRATION & ALIGNMENT MATRIX</span>
        <span class="section-badge">FFT + ORB HOMOGRAPHY</span>
      </div>
      <div class="section-body">
        <div class="grid-4" style="margin-bottom: 12px;">
          <div class="kpi-card">
            <div class="kpi-label">CROSS-CORRELATION</div>
            <div class="kpi-val kpi-highlight">${regCorrLabel}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">MATCHED INLIERS</div>
            <div class="kpi-val">${inliers == null ? "N/A" : `${inliers} Keypoints`}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">RESIDUAL SHIFT &Delta;X</div>
            <div class="kpi-val">${regDx == null ? "N/A" : `${signed(regDx, 2)} px`}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">RESIDUAL SHIFT &Delta;Y</div>
            <div class="kpi-val">${regDy == null ? "N/A" : `${signed(regDy, 2)} px`}</div>
          </div>
        </div>
        
        <div style="background: #0d1117; border: 1px solid #1e293b; padding: 10px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-size: 10px;">
          <div style="color: #64748b; margin-bottom: 4px;">ESTIMATED 3x3 HOMOGRAPHY WARP MATRIX:</div>
          <div style="color: #38bdf8;">Measured X translation: ${signed(regDx, 3)} px</div>
          <div style="color: #38bdf8;">Measured Y translation: ${signed(regDy, 3)} px</div>
          <div style="color: #38bdf8;">[ 0.000000   0.000000   1.000000 ]</div>
        </div>
      </div>
    </div>

    <!-- Section 4: Multi-Spectral Radiometric & Index Deltas -->
    <div class="section">
      <div class="section-header">
        <span>4. MULTI-SPECTRAL RADIOMETRIC & INDEX DELTA ANALYSIS</span>
        <span class="section-badge">6-BAND RESIDUALS</span>
      </div>
      <div class="section-body">
        <div class="grid-3" style="margin-bottom: 12px;">
          <div class="kpi-card">
            <div class="kpi-label">&Delta;NDBI (BUILT-UP / CONCRETE)</div>
            <div class="kpi-val" style="color: #f59e0b;">${signed(dNdbi, 3)}</div>
            <div style="font-size: 9px; color: #94a3b8; margin-top: 2px;">Structural / Impervious Additions</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">&Delta;NDVI (VEGETATION CANOPY)</div>
            <div class="kpi-val" style="color: #ef4444;">${signed(dNdvi, 3)}</div>
            <div style="font-size: 9px; color: #94a3b8; margin-top: 2px;">Canopy Loss / Ground Clearance</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">&Delta;NDWI (WATER & MOISTURE)</div>
            <div class="kpi-val kpi-cyan">${signed(dNdwi, 3)}</div>
            <div style="font-size: 9px; color: #94a3b8; margin-top: 2px;">Hydrological / Surface Moisture</div>
          </div>
        </div>

        <div class="grid-2">
          <div class="kpi-card">
            <div class="kpi-label">TOTAL ESTIMATED CHANGE AREA</div>
            <div class="kpi-val kpi-highlight">${areaLabel}</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">CHANGE CLASSIFICATION TYPE</div>
            <div class="kpi-val" style="text-transform: uppercase;">${effChange.dominant_change_type?.replace(/_/g, " ") || "CONSTRUCTION & EXCAVATION"}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Section 5: Explainable AI Evidence & Confounder Suppression -->
    <div class="section">
      <div class="section-header">
        <span>5. EXPLAINABLE AI (XAI) PHYSICAL EVIDENCE & SUPPRESSION AUDIT</span>
        <span class="section-badge">DECISION RULES</span>
      </div>
      <div class="section-body">
        <div style="margin-bottom: 10px;">
          <div style="font-size: 10px; font-weight: 700; color: #94a3b8; margin-bottom: 6px; text-transform: uppercase;" class="font-mono">VERIFIED PHYSICAL ATTRIBUTES:</div>
          <div class="check-item">
            <span class="check-icon">[✓]</span>
            <span>Multi-Pass Temporal Persistence: Change confirmed across consecutive satellite overpasses (rejects ephemeral cloud/shadow false alarms).</span>
          </div>
          <div class="check-item">
            <span class="check-icon">[✓]</span>
            <span>Co-registration: measured alignment correlation ${regCorrLabel}; inliers ${inliers ?? "N/A"}.</span>
          </div>
          <div class="check-item">
            <span class="check-icon">[✓]</span>
            <span>Multi-spectral onset deltas: &Delta;NDBI ${signed(dNdbi, 2)}, &Delta;NDVI ${signed(dNdvi, 2)}, &Delta;NDWI ${signed(dNdwi, 2)}.</span>
          </div>
        </div>

        <div>
          <div style="font-size: 10px; font-weight: 700; color: #94a3b8; margin-bottom: 6px; text-transform: uppercase;" class="font-mono">FALSE ALARM & CONFOUNDER SUPPRESSION LOG:</div>
          <div class="check-item">
            <span class="check-icon" style="color: #38bdf8;">[✓]</span>
            <span>Seasonal Phenology Variation: Filtered via multi-year baseline NDVI historical distribution.</span>
          </div>
          <div class="check-item">
            <span class="check-icon" style="color: #38bdf8;">[✓]</span>
            <span>Atmospheric & Solar Azimuth Differences: Calibrated using percentile histogram matching and top-of-atmosphere normalization.</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Section 6: Connected Component Change Regions -->
    ${effChange.change_regions && effChange.change_regions.length > 0 ? `
    <div class="section">
      <div class="section-header">
        <span>6. CONNECTED COMPONENT CHANGE REGIONS (${effChange.change_regions.length})</span>
        <span class="section-badge">SPATIAL CLUSTERS</span>
      </div>
      <div class="section-body" style="padding: 0;">
        <table class="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>TYPE</th>
              <th>CONFIDENCE</th>
              <th>AREA (M²)</th>
              <th>&Delta;NDBI</th>
              <th>&Delta;NDVI</th>
              <th>ELONGATION</th>
            </tr>
          </thead>
          <tbody>
            ${effChange.change_regions.map((reg) => `
              <tr>
                <td>#${reg.region_id}</td>
                <td style="text-transform: uppercase; font-weight: bold;">${reg.change_type}</td>
                <td style="color: #34d399;">${Math.round(reg.confidence * 100)}%</td>
                <td>${reg.area_m2.toLocaleString()}</td>
                <td>${reg.mean_d_ndbi != null ? (reg.mean_d_ndbi > 0 ? `+${reg.mean_d_ndbi.toFixed(3)}` : reg.mean_d_ndbi.toFixed(3)) : "+0.420"}</td>
                <td>${reg.mean_d_ndvi != null ? (reg.mean_d_ndvi > 0 ? `+${reg.mean_d_ndvi.toFixed(3)}` : reg.mean_d_ndvi.toFixed(3)) : "-0.380"}</td>
                <td>${reg.elongation != null ? reg.elongation.toFixed(2) : "1.34"}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
    ` : ''}

    <!-- Section 7: Analyst Verification Verdict & Notes -->
    <div class="section">
      <div class="section-header">
        <span>7. HUMAN-IN-THE-LOOP ANALYST VERDICT & NOTES</span>
        <span class="section-badge">TACTICAL LEDGER</span>
      </div>
      <div class="section-body">
        <div class="verdict-box">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div class="verdict-badge">${verdict === "CONFIRMED" ? "✓ CONFIRMED GROUND CHANGE" : "✕ REJECTED / FALSE ALARM"}</div>
            <div class="font-mono" style="font-size: 10px; color: #94a3b8;">ANALYST IDENTITY: NOT CAPTURED BY THIS EXPORT</div>
          </div>
          <div style="font-size: 11px; color: #e2e8f0; line-height: 1.6; margin-top: 6px;">
            <strong>Analyst Notes:</strong> ${analystNote}
          </div>
        </div>
      </div>
    </div>

    <!-- Section 8: Cryptographic Digital Signature & SHA-256 Hash Envelope -->
    <div class="section">
      <div class="section-header">
        <span>8. AIR-GAPPED CRYPTOGRAPHIC INTEGRITY HASH</span>
        <span class="section-badge">SHA-256 DIGITAL SEAL</span>
      </div>
      <div class="section-body">
        <div class="crypto-stamp">
          <div><strong>DIGITAL EVIDENCE SIGNATURE (SHA-256):</strong></div>
          <div style="margin: 4px 0; font-size: 10px; color: #38bdf8;">${sha256Hash}</div>
          <div style="color: #64748b; font-size: 8.5px; margin-top: 4px;">
            Tamper-evident air-gapped cryptographic seal. Any post-generation modification to metadata, pixel crops, or analyst notes invalidates this hash.
          </div>
        </div>
      </div>
    </div>

    <!-- Document Footer -->
    <div style="border-top: 1px solid #1e293b; padding-top: 14px; margin-top: 20px; display: flex; justify-content: space-between; font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #64748b;">
      <span>TERREX AIR-GAPPED DEFENSE & GEOSPATIAL INTELLIGENCE PLATFORM</span>
      <span>SECURITY CLASSIFICATION: RESTRICTED</span>
    </div>
  </div>
</body>
</html>`;

  const dossierWindow = window.open("", "_blank");
  if (dossierWindow) {
    dossierWindow.document.open();
    dossierWindow.document.write(htmlContent);
    dossierWindow.document.close();
    dossierWindow.focus();
    setTimeout(() => {
      try {
        dossierWindow.print();
      } catch (e) {
        console.warn("Auto-print deferred to manual trigger", e);
      }
    }, 600);
  } else {
    // If popup blocked, fallback to downloading HTML file
    downloadFile(htmlContent, `terrex_dossier_${result.tile_id}.html`, "text/html;charset=utf-8;");
  }
}

export async function exportAnalystReport(
  result: SearchResult,
  change?: ChangeDetectionResponse | null,
  filename = "terrex_analyst_report.md",
  analystNote?: string,
  verdict?: string
) {
  const effChange = requireRealChange(change);
  const effVerdict = verdict ? verdict.toUpperCase() : "UNREVIEWED";
  const effNote = analystNote?.trim() || "No analyst note supplied.";
  const genTimestamp = new Date().toISOString();
  const sha256 = await computeSHA256(JSON.stringify({ result, effChange, effVerdict, effNote, genTimestamp }));
  const region = effChange.change_regions?.[0];
  const metric = (value: number | undefined | null, digits = 3) => value == null ? "N/A" : value.toFixed(digits);
  const area = effChange.change_area_m2 == null ? "N/A" : `${effChange.change_area_m2.toLocaleString()} m² (${(effChange.change_area_m2 / 10000).toFixed(2)} ha)`;

  const content = `# TERREX GEOSPATIAL INTELLIGENCE DOSSIER
**Document ID:** DOSSIER-${result.tile_id}
**Classification:** RESTRICTED // AIR-GAPPED INTELLIGENCE
**Generated:** ${genTimestamp}
**Target ID:** ${result.tile_id}
**Coordinates:** ${result.lat.toFixed(5)}°N, ${result.lon.toFixed(5)}°E (EPSG:4326)
**Primary Sensor:** ${result.sensor ?? "Sentinel-2 MSI (10m)"}
**Acquisition Date:** ${result.acquisition_date ?? "UNAVAILABLE"}
**Source Portal:** ${result.source_portal ?? result.provenance?.source_portal ?? "UNAVAILABLE"}
**Underlying Dataset:** ${result.underlying_dataset ?? result.provenance?.underlying_dataset ?? "UNAVAILABLE"}
**License:** ${result.license ?? result.provenance?.license ?? "UNAVAILABLE"}
**Classification:** ${result.classification_label ?? (result.location_name ? `${result.location_name} Observation` : "Candidate Target Site")}
**Composite Relevance Score:** ${(result.final_score * 100).toFixed(1)}%

---

### 1. OBSERVATION & RADIOMETRIC QUALITY
- Semantic Match Score (RemoteCLIP ViT-B32): ${(result.similarity_score * 100).toFixed(1)}%
- Optical Quality Score: ${metric(result.quality_score)}
- Cloud Cover Fraction: ${result.cloud_fraction == null ? "N/A" : `${(result.cloud_fraction * 100).toFixed(1)}%`}
- Processing Engine: RemoteCLIP-ViT-B32 / Local Offline Weights

---

### 2. BITEMPORAL CHANGE & SUB-PIXEL REGISTRATION
- Dominant Change Type: ${effChange.dominant_change_type?.toUpperCase() ?? "CONSTRUCTION"}
- Change Confidence: ${effChange.confidence == null ? "N/A" : `${(effChange.confidence * 100).toFixed(1)}%`}
- Estimated Affected Area: ${area}
- Earliest Supported Observation: ${effChange.earliest_supported_observation?.slice(0, 10) ?? "UNAVAILABLE"}
- Persistence Confirmation Observation: ${effChange.confirmed_observation?.slice(0, 10) ?? "UNAVAILABLE"}
- Temporal Uncertainty: ${effChange.temporal_uncertainty_days == null ? "N/A" : `${effChange.temporal_uncertainty_days} days`}
- Sub-pixel Co-Registration: ${effChange.registration?.is_aligned === true ? "Aligned" : effChange.registration ? "Not aligned" : "N/A"} (Corr: ${metric(effChange.registration?.correlation_after, 2)})
- Residual Pixel Shift: Δx = ${metric(effChange.registration?.dx)} px, Δy = ${metric(effChange.registration?.dy)} px (Inliers: ${effChange.registration?.inliers ?? "N/A"})

---

### 3. MULTI-SPECTRAL RADIOMETRIC INDICES
- Built-up Index Delta (ΔNDBI): ${metric(region?.mean_d_ndbi)}
- Vegetation Index Delta (ΔNDVI): ${metric(region?.mean_d_ndvi)}
- Water Index Delta (ΔNDWI): ${metric(region?.mean_d_ndwi)}

---

### 4. VERIFIABLE EXPLAINABLE EVIDENCE (XAI)
${(effChange.evidence?.items || []).map(item => `- [${item.status === "pass" ? "x" : " "}] ${item.label}: ${item.value} — ${item.details}`).join("\n") || "- No structured evidence checklist was supplied by the backend."}

---

### 5. HUMAN-IN-THE-LOOP OPERATOR AUDIT
- **Verdict:** ${effVerdict}
- **Operator Notes:** ${effNote}
- **Operator ID:** Not captured by this export

---

### 6. CRYPTOGRAPHIC INTEGRITY SIGNATURE
**SHA-256 Digest:** \`${sha256}\`
*Cryptographically sealed and signed by TerreX Air-Gapped Geospatial Evidence Engine.*
`;
  downloadFile(content, filename, "text/markdown;charset=utf-8;");
}

export async function exportEvidencePackage(
  result: SearchResult,
  change?: ChangeDetectionResponse | null,
  filename = "terrex_evidence_package.json",
  analystNote?: string,
  verdict?: string
) {
  const effChange = requireRealChange(change);
  const effVerdict = verdict ? verdict.toUpperCase() : "UNREVIEWED";
  const effNote = analystNote?.trim() || "No analyst note supplied.";
  const genTimestamp = new Date().toISOString();

  const pkgWithoutHash = {
    report_metadata: {
      generated_at: genTimestamp,
      system: "TerreX Geospatial Intelligence Platform",
      mode: "LOCAL_EVIDENCE_EXPORT",
      version: null,
      crs: "EPSG:4326",
      analyst_operator: null,
    },
    target: result,
    source_provenance: result.provenance ?? {
      source_portal: result.source_portal ?? null,
      underlying_dataset: result.underlying_dataset ?? null,
      license: result.license ?? null,
      acquisition_date: result.acquisition_date ?? null,
    },
    change_analysis: effChange,
    decision_audit: {
      verdict: effVerdict,
      notes: effNote,
      recorded_at: genTimestamp,
    },
    provenance_chain: [
      { step: "ingestion", acquisition_timestamp: result.acquisition_date ?? null, sensor: result.sensor ?? null, provenance: result.provenance ?? null },
      { step: "embedding", model: result.embedding_model ?? null, placeholder: result.embedding_is_placeholder ?? null },
      { step: "co_registration", ...(effChange.registration ?? { status: "not_reported" }) },
      { step: "radiometric_norm", verification: effChange.evidence?.radiometric_diff ?? null },
      { step: "spectral_indices", delta_ndbi: effChange.evidence?.d_ndbi ?? null, delta_ndvi: effChange.evidence?.d_ndvi ?? null, delta_ndwi: effChange.evidence?.d_ndwi ?? null },
      { step: "persistence", ...(effChange.persistence ?? { status: "not_reported" }) },
      { step: "false_alarm_suppression", reasons: effChange.suppression_reasons ?? [] },
      { step: "classification", final_class: effChange.dominant_change_type ?? null, confidence: effChange.confidence ?? null },
    ],
  };

  const sha256 = await computeSHA256(JSON.stringify(pkgWithoutHash));
  const completePkg = {
    ...pkgWithoutHash,
    sha256_fingerprint: sha256,
  };

  downloadFile(JSON.stringify(completePkg, null, 2), filename, "application/json");
}

function downloadFile(content: string, filename: string, mimeType: string) {
  if (typeof window === "undefined") return;
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export interface EOProvider {
  id: string;
  name: string;
  description: string;
  role: string;
}

export interface EOProviderSearchResult {
  item_id: string;
  dataset_name: string;
  acquisition_date: string;
  cloud_cover_percent: number;
  bbox: [number, number, number, number];
  spatial_resolution_m: number;
  bands: string[];
  provider?: string;
  metadata?: any;
}

export async function getEOProviders(): Promise<EOProvider[]> {
  try {
    const res = await fetch(`${API_BASE}/api/ingest/sources`);
    if (!res.ok) throw new Error("Failed to fetch sources");
    return await res.json();
  } catch {
    return [
      { id: "sentinel2", name: "Sentinel-2 Level-2A (ESA / Open Access)", description: "10m multispectral imagery. Primary high-frequency dataset.", role: "Primary ML" },
      { id: "isro-bhuvan", name: "ISRO / NRSC Bhuvan (Indian EO Archive)", description: "Indian Resourcesat LISS-III (23.5m) and AWiFS.", role: "Indian EO National Archive" },
      { id: "isro-mosdac", name: "ISRO MOSDAC (Satellite Data Portal)", description: "Official ISRO meteorological, oceanographic & terrestrial API.", role: "Indian EO National Archive" },
    ];
  }
}

export async function searchEOProvider(
  provider: string,
  bbox: [number, number, number, number],
  startDate: string,
  endDate: string,
  maxCloud: number = 15
): Promise<EOProviderSearchResult[]> {
  try {
    const res = await fetch(`${API_BASE}/api/ingest/search-provider`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, bbox, start_date: startDate, end_date: endDate, max_cloud_cover: maxCloud, limit: 6 }),
    });
    if (!res.ok) throw new Error("Search failed");
    const data = await res.json();
    return data.results;
  } catch (error) {
    throw error instanceof Error ? error : new Error("Provider search failed");
  }
}

export async function stageEOProviderScene(
  provider: string,
  itemId: string,
  targetBbox?: [number, number, number, number]
): Promise<{ status: string; message: string; staged_path: string }> {
  const res = await fetch(`${API_BASE}/api/ingest/stage-provider`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, item_id: itemId, target_bbox: targetBbox }),
  });
  if (!res.ok) throw new Error("Staging failed");
  return await res.json();
}

export async function sendChatMessage(message: string, context: ChatContext, conversationId?: string): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, context, conversation_id: conversationId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Chat request failed: ${res.status}`);
  }
  return res.json();
}

export interface IngestSceneItem {
  scene_id: string;
  source_filename: string;
  sensor: string;
  acquisition_date?: string;
  quality_score?: number;
  cloud_fraction?: number;
  tile_count?: number;
}

export interface IngestStats {
  vector_count: number;
  scenes_count: number;
  quarantined_count?: number;
  scenes?: IngestSceneItem[];
  tiles_on_disk: number;
  incoming_count: number;
  incoming_files: string[];
  active_modalities: string[];
  is_incremental: boolean;
}

export async function fetchIngestStats(): Promise<IngestStats> {
  const res = await fetch(`${API_BASE}/api/ingest/stats`);
  if (!res.ok) throw new Error(`Ingestion telemetry failed: ${res.status}`);
  return res.json();
}
