---
name: terrex-frontend-ui
description: Component map, routing structure, and UI conventions for the TerreX Next.js frontend. Use this skill when working on UI components, map interactions, API integration from the frontend, or adding new pages/routes.
---

# TerreX Frontend UI

## When to Use
- Adding or modifying a component in `frontend/components/`
- Adding a new page/route in `frontend/app/`
- Working on MapLibre map layers, tile sources, or AOI drawing
- Integrating a new backend API call from the frontend

## Stack
Next.js 14 App Router · TypeScript · Tailwind CSS · MapLibre GL JS (offline only)

## App Routes (`frontend/app/`)
`/` landing · `/workspace` analyst dashboard · `/changes` change results · `/review` confirm/reject queue · `/ingest` upload imagery · `/data` scene browser · `/system` model health

## Component Map

| Component | Purpose |
|-----------|---------|
| `MapView.tsx` | MapLibre map — footprints, change overlays, AOI selection |
| `SearchBar.tsx` | NL + image-upload search input |
| `FilterBar.tsx` | Date, sensor, cloud cover, quality filters |
| `ResultsList.tsx` | Ranked tile result cards with placeholder badges |
| `ResultDetail.tsx` | Full result detail — metadata, thumbnails, spectral |
| `EvidencePanel.tsx` | Change evidence: crops, deltas, classification |
| `BeforeAfterSlider.tsx` | Swipe compare of bi-temporal imagery |
| `ChangeTimeline.tsx` | Time-series change score chart |
| `ProvenanceDrawer.tsx` | Scene provenance: source, license, download date |
| `ExportModal.tsx` | Export as GeoJSON / PDF |
| `ChatPanel.tsx` | Ollama analyst chat UI |

## Rules
- All API calls go through `frontend/lib/api.ts`. Never use raw `fetch()` in components.
- MapLibre: local tile sources only — `GET /api/basemap/tiles/{z}/{x}/{y}`. No Mapbox tokens.
- Placeholder UI: `is_placeholder=true` ? orange "DEMO EMBEDDINGS" badge. `is_placeholder_model=true` ? warning banner in EvidencePanel.

## Adding a Page
1. Create `frontend/app/<route>/page.tsx`
2. Add nav link to `TopNav.tsx`
3. Add typed API helper to `lib/api.ts`
4. Check `frontend/AGENTS.md` for Next.js version-specific notes before using new APIs
