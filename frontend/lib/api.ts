// Thin fetch wrapper around the TerreX FastAPI backend.
// Base URL is injected at build/run time via NEXT_PUBLIC_API_URL so the
// frontend never hardcodes a hostname (works in docker-compose and locally).

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  thumbnail_path: string | null;
  embedding_model: string | null;
  embedding_is_placeholder: boolean;
}

export interface TextSearchResponse {
  query: string;
  embedding_model: string;
  embedding_is_placeholder: boolean;
  results: SearchResult[];
}

export interface ChangeDetectionResponse {
  status: string;
  message?: string;
  change_id?: string;
  before?: any;
  after?: any;
  change_score?: number;
  quality_score?: number;
  confidence?: number;
  change_area_m2?: number;
  change_mask_path?: string;
  reasons?: string[];
  method?: string;
  is_placeholder_model?: boolean;
  registration_correlation?: number;
  earliest_supported_observation?: string;
}

export interface SystemStatus {
  offline_mode: boolean;
  processing_version: string;
  models: {
    remoteclip: { staged: boolean; active_model: string };
    prithvi: { staged: boolean; active_model: string };
  };
}

export interface FilterState {
  sensor?: string;
  dateFrom?: string;
  dateTo?: string;
  minSimilarity?: number;
}

export async function searchByText(query: string, filters: FilterState = {}): Promise<TextSearchResponse> {
  const params = new URLSearchParams({ q: query, top_k: "20" });
  if (filters.sensor) params.set("sensor", filters.sensor);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  if (filters.minSimilarity !== undefined) params.set("min_similarity", String(filters.minSimilarity));
  const res = await fetch(`${API_BASE}/api/search/text?${params.toString()}`);
  if (!res.ok) throw new Error(`Search failed: ${res.status}`);
  return res.json();
}

export async function searchByImage(file: File, filters: FilterState = {}): Promise<TextSearchResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("top_k", "20");
  if (filters.sensor) form.append("sensor", filters.sensor);
  if (filters.dateFrom) form.append("date_from", filters.dateFrom);
  if (filters.dateTo) form.append("date_to", filters.dateTo);
  const res = await fetch(`${API_BASE}/api/search/image`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Image search failed: ${res.status}`);
  return res.json();
}

export async function detectChange(lon: number, lat: number, dateFrom: string, dateTo: string): Promise<ChangeDetectionResponse> {
  const params = new URLSearchParams({ lon: String(lon), lat: String(lat), date_from: dateFrom, date_to: dateTo });
  const res = await fetch(`${API_BASE}/api/change/detect?${params.toString()}`);
  if (!res.ok) throw new Error(`Change detection failed: ${res.status}`);
  return res.json();
}

export async function submitFeedback(targetType: string, targetId: string, verdict: "confirm" | "reject", note?: string) {
  const res = await fetch(`${API_BASE}/api/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_type: targetType, target_id: targetId, verdict, note }),
  });
  if (!res.ok) throw new Error(`Feedback submit failed: ${res.status}`);
  return res.json();
}

export async function getSystemStatus(): Promise<SystemStatus> {
  const res = await fetch(`${API_BASE}/api/system/status`);
  if (!res.ok) throw new Error(`Status fetch failed: ${res.status}`);
  return res.json();
}

export async function listScenes() {
  const res = await fetch(`${API_BASE}/api/ingest/scenes`);
  if (!res.ok) throw new Error(`Scenes fetch failed: ${res.status}`);
  return res.json();
}

export async function processIncoming() {
  const res = await fetch(`${API_BASE}/api/ingest/process-incoming`, { method: "POST" });
  if (!res.ok) throw new Error(`Process-incoming failed: ${res.status}`);
  return res.json();
}

export function thumbnailUrl(path: string | null): string {
  if (!path) return "";
  // backend serves tile thumbnails as static files under /static (mounted to DATA_DIR)
  const marker = "/data/";
  const idx = path.indexOf(marker);
  const rel = idx >= 0 ? path.slice(idx + marker.length) : path;
  return `${API_BASE}/static/${rel}`;
}
