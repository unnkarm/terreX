# TerreX: Geospatial Intelligence Console — Changes, Additions & Modifications

This document provides a comprehensive log of all architectural enhancements, codebase modifications, and merge resolutions implemented in the **TerreX** platform.

---

## 📑 Table of Contents
1. [Git Merge Conflict Resolution (`c75d628`)](#1-git-merge-conflict-resolution-c75d628)
2. [Detailed Inventory of Files (Added vs. Modified)](#2-detailed-inventory-of-files-added-vs-modified)
3. [The 5 Core MVP Capabilities Implemented](#3-the-5-core-mvp-capabilities-implemented)
4. [Indian Earth Observation (EO) Integration](#4-indian-earth-observation-eo-integration)
5. [Premier Indian Demonstration Corridors](#5-premier-indian-demonstration-corridors)
6. [Operational Staging & Execution Guide](#6-operational-staging--execution-guide)
7. [API Endpoint Directory](#7-api-endpoint-directory)

---

## 1. Git Merge Conflict Resolution (`c75d628`)

Branch `enhanced` was reconciled with remote `origin/main` (incorporating upstream commits `121c0d0`, `1d91596`, and `047af89`). All 5 file conflicts were resolved cleanly:

| File | Nature of Conflict | Resolution |
| :--- | :--- | :--- |
| **`backend/api/routes_ingest.py`** | Import clashes between Indian EO sources and upstream vector index counters. | Preserved both `data_sources` registry imports and `services.vector_store.vector_store` metric counters. |
| **`frontend/lib/api.ts`** | Clashing `SystemStatus` interface definitions and end-of-file export routines. | Merged `paths` with upstream chat status fields (`chat_available`, `ram_available`, etc.), preserved all EO Provider client methods, and integrated `sendChatMessage`. |
| **`frontend/components/ResultDetail.tsx`** | Upstream AI chat assistant vs. enhanced bitemporal split slider and evidence panels. | Integrated the **"Ask AI"** toggle and floating `ChatPanel` dropdown directly into the site inspection header alongside the split slider, timeline, and evidence checklist. |
| **`frontend/app/workspace/page.tsx`** | Upstream vector index empty-state overlay vs. 3-column operational layout and Indian AOI selector. | Preserved both the `hasData === false` empty state warning and the 3-column layout with the Indian AOI fast-selector bar. |
| **`frontend/app/ingest/page.tsx`** | Upstream ingestion metric tiles vs. the multi-tab Indian EO deck and execution logs. | Unified both: multi-tab source selector (Sentinel-2, Bhuvan, MOSDAC), metric counters (`TILES CREATED`, `TILES SKIPPED`, etc.), and terminal execution logs. |

---

## 2. Detailed Inventory of Files (Added vs. Modified)

### A. New Files (`[NEW]`)

#### 🇮🇳 Indian EO Data Source Adapters
- `backend/data_sources/__init__.py`: Central provider registry with `get_data_source()` and `list_available_sources()`.
- `backend/data_sources/base.py`: Abstract contract (`BaseEODataSource`) and standardized data model (`EOSearchResult`).
- `backend/data_sources/sentinel2.py`: Primary ML dataset adapter for Sentinel-2 L2A 10m multispectral imagery.
- `backend/data_sources/bhuvan.py`: **ISRO / NRSC Bhuvan** open data adapter for Resourcesat-1/2 (LISS-III at 23.5m, AWiFS at 56m) and national geographical context layers.
- `backend/data_sources/mosdac.py`: **ISRO MOSDAC** official API adapter supporting `datasetId`, `startTime`, `endTime`, and `boundingBox` queries for INSAT-3D/3DR, Oceansat-3 (OCM-3), and EOS-04 SAR.

#### 🤖 Upstream AI Evidence Assistant
- `backend/api/routes_chat.py`: REST endpoint (`POST /api/chat`) for conversational geospatial reasoning.
- `backend/services/chat_agent.py`: Scoped chat agent with strict RAM-safe guardrails and citation grounding.
- `frontend/components/ChatPanel.tsx`: Scoped conversational assistant UI with evidence citations.
- `frontend/components/GlobalChatWidget.tsx`: Floating global workspace chat assistant widget.
- `docs/architecture.md`: Upstream system architecture documentation.

#### 🛠️ Automation & Weights Downloaders
- `scripts/download_remoteclip_weights.py`: Automates downloading the official `RemoteCLIP-ViT-B-32.pt` checkpoint (600 MB) from Hugging Face into `models/remoteclip/`.
- `powershell.cmd`: Environment execution wrapper ensuring reliable shell execution on Windows host systems.

---

### B. Modified Files (`[MODIFY]`)

#### Backend Services & API
- `backend/api/routes_ingest.py`: Added `GET /api/ingest/sources`, `POST /api/ingest/search-provider`, and `POST /api/ingest/stage-provider`.
- `backend/api/routes_change.py`: Added `POST /api/change/detect` with support for JSON request bodies containing bounding boxes or coordinates.
- `backend/services/change_detection.py`: Added `change_area_hectares` calculation (`m2 / 10000.0`) and human-readable `change_summary` string.
- `backend/main.py`: Registered the new chat router (`/api/chat`).
- `.gitignore`: Added `powershell.cmd` and model weight exclusions.

#### Frontend Console & Intelligence HUD
- `frontend/app/workspace/page.tsx`: Added the **Indian Location Fast Selector Bar** (Kolkata, Delhi NCR, Bengaluru, Ahmedabad, Mumbai), default landing on Kolkata New Town (`[88.4754, 22.5867]`), restored `runImageSearch`, and connected citation cross-highlighting.
- `frontend/app/ingest/page.tsx`: Added multi-tab Indian EO deck (**Sentinel-2 L2A**, **ISRO Bhuvan**, **ISRO MOSDAC**), 1-click `[ STAGE TO TERREX ]` action, and pipeline metric counters.
- `frontend/components/SearchBar.tsx`: Streamlined to 2 operational modes (**Semantic Text** and **Reference Chip**); added Indian intent suggestions.
- `frontend/components/FilterBar.tsx`: Streamlined to Spatial AOI (`◇ DRAW AOI`), Sentinel-2 sensor, Date range, and Cloud Cover slider.
- `frontend/components/ResultsList.tsx`: Focused card actions on `[ INSPECT TARGET → ]`.
- `frontend/components/ResultDetail.tsx`: Integrated **Basic Provenance Card**, **"Ask AI"** toggle, `ChatPanel`, and hectares/m² area measurements.
- `frontend/components/EvidencePanel.tsx`: Restructured into a clean 2-tier breakdown: **Physical Evidence** vs. **Observation Quality**.
- `frontend/lib/api.ts`: Added EO Provider client methods (`getEOProviders`, `searchEOProvider`, `stageEOProviderScene`) and `sendChatMessage`.
- `scripts/download_planetary_scenes.py`: Added `--preset kolkata` and `--preset delhi` CLI arguments.

---

## 3. The 5 Core MVP Capabilities Implemented

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. SEMANTIC SATELLITE SEARCH                                                │
│    Text Query ("new buildings near water in New Town, Kolkata")             │
│    ↓ RemoteCLIP ViT-B/32 (Local 512-dim embedding)                          │
│    ↓ Qdrant Vector Store (Cosine HNSW)                                      │
│    ↓ PostGIS Spatial & Temporal Filters (AOI, Date, Cloud)                  │
│    → Ranked Results Queue (#01, #02, #03...)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. REAL SATELLITE INGESTION                                                 │
│    Sentinel-2 / ISRO Multi-Band GeoTIFF                                     │
│    ↓ Sliding Window Tiling (256x256 pixel chips)                            │
│    ↓ Quality Gate (Cloud < 5%, Valid Pixels > 95%)                          │
│    ↓ RemoteCLIP 512-dim Vector Upsert                                       │
│    → Live and searchable in Workspace                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. BEFORE / AFTER CHANGE DETECTION                                          │
│    T0 (2023) ─────────────── T1 (2025)                                      │
│    ↓ Interactive Before/After Split Slider                                  │
│    ↓ Multi-Spectral Difference (NDBI, NDVI, NDWI)                           │
│    → Dominant Type (CONSTRUCTION, WATER, CLEARANCE, OTHER)                  │
│    → Area in Hectares & m² (e.g. 2.8 ha / 28,400 m²)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ 4. EXPLAINABLE CONFIDENCE & EVIDENCE                                        │
│    • Physical Evidence:                                                     │
│      ✓ Built-up index increased (ΔNDBI: +0.42)                              │
│      ✓ Vegetation decreased (ΔNDVI: -0.38)                                  │
│      ✓ Multi-pass persistence verified                                      │
│      ✓ Sub-pixel registration confidence: 96%                               │
│    • Observation Quality:                                                   │
│      ✓ Cloud contamination < 4%                                             │
│      ✓ Valid pixel ratio > 95%                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ 5. ANALYST CONFIRM / REJECT AUDIT                                           │
│    [ ✓ CONFIRM ]        [ ✕ REJECT ]                                        │
│    ↓ Operator notes & station telemetry                                     │
│    → Immutable record saved to PostGIS feedback audit log via POST /feedback│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Indian Earth Observation (EO) Integration

TerreX separates visual semantic search from multispectral temporal science:
- **RGB Visual Composite**: Band 4 (Red), Band 3 (Green), Band 2 (Blue) $\rightarrow$ **RemoteCLIP ViT-B/32** semantic embedding.
- **Multispectral Temporal Bands**: Band 8 (NIR), Band 11 (SWIR1), Band 12 (SWIR2), SCL $\rightarrow$ **Spectral Change Engine**:
  $$\text{NDVI} = \frac{\text{B08} - \text{B04}}{\text{B08} + \text{B04}} \quad \text{(Vegetation)}$$
  $$\text{NDBI} = \frac{\text{B11} - \text{B08}}{\text{B11} + \text{B08}} \quad \text{(Built-Up / Concrete)}$$
  $$\text{NDWI} = \frac{\text{B03} - \text{B08}}{\text{B03} + \text{B08}} \quad \text{(Water Bodies)}$$

### Supported Sources
1. **Sentinel-2 L2A**: Primary 10m high-frequency dataset.
2. **ISRO / NRSC Bhuvan**: Indian Resourcesat LISS-III (23.5m) and AWiFS (56m).
3. **ISRO MOSDAC**: Official API for INSAT-3D/3DR, Oceansat-3 OCM, and EOS-04 SAR.

---

## 5. Premier Indian Demonstration Corridors

Fast-selector buttons in the Workspace header allow 1-click inspection of major Indian growth areas:

| Corridor | Coordinates | Target Scenario & Intent Query |
| :--- | :--- | :--- |
| **⭐ Kolkata (New Town)** | `22.5867° N, 88.4754° E` | **Premier Demo**: Rapid construction across Action Area I, II, & III bordering East Kolkata wetlands.<br>*Query: "New buildings near water in New Town, Kolkata"* |
| **Delhi NCR (Yamuna)** | `28.5684° N, 77.2912° E` | Infrastructure development and riverbed encroachment along the Yamuna corridor.<br>*Query: "Highways & construction along Yamuna corridor"* |
| **Bengaluru (Outskirts)** | `12.8452° N, 77.6602° E` | Peri-urban tech corridor expansion and vegetation plot clearance.<br>*Query: "Urban expansion & roads in Bengaluru outskirts"* |
| **Ahmedabad (Sabarmati)**| `23.0225° N, 72.5714° E` | Dryland industrial corridors and riverfront urban development.<br>*Query: "Industrial development in Ahmedabad"* |
| **Mumbai (Coastal)** | `19.0760° N, 72.8777° E` | Coastal infrastructure, reclamation, and high-density marine development.<br>*Query: "Dense coastal construction in Mumbai"* |

---

## 6. Operational Staging & Execution Guide

### Step 1: Download Real RemoteCLIP Weights
```bash
python scripts/download_remoteclip_weights.py
```
*Downloads `RemoteCLIP-ViT-B-32.pt` directly into `models/remoteclip/` from Hugging Face.*

### Step 2: Acquire Sentinel-2 Imagery over Kolkata
```bash
python scripts/download_planetary_scenes.py --preset kolkata --count 4
```
*Extracts multi-band GeoTIFFs (B02, B03, B04, B08, B11, SCL) directly into `data/incoming/`.*

### Step 3: Run TerreX Ingestion
Navigate to `http://localhost:3000/ingest` and click **`PROCESS data/incoming/ DIRECTORY`** or select an ISRO pass and click **`STAGE TO TERREX →`**.

### Step 4: Launch the Workspace
Open `http://localhost:3000/workspace` to perform semantic searches, inspect bi-temporal changes, and record analyst decisions.

---

## 7. API Endpoint Directory

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/search/text` | Natural language search via RemoteCLIP text encoder + Qdrant kNN. |
| `POST` | `/api/search/image` | Reference optical chip search via RemoteCLIP image encoder. |
| `POST` | `/api/change/detect` | Bi-temporal change detection (JSON payload with `aoi` or coordinates). |
| `GET` | `/api/change/detect` | Bi-temporal change detection (Query parameters: `lon`, `lat`, `date_from`, `date_to`). |
| `GET` | `/api/ingest/sources` | Lists registered EO providers (Sentinel-2, ISRO Bhuvan, ISRO MOSDAC). |
| `POST` | `/api/ingest/search-provider` | Queries provider catalog by AOI and date range. |
| `POST` | `/api/ingest/stage-provider` | Stages a selected scene into `data/incoming/` as normalized GeoTIFF. |
| `POST` | `/api/ingest/upload` | Uploads and ingests a single GeoTIFF file. |
| `POST` | `/api/ingest/process-incoming` | Scans `data/incoming/` and ingests all pending scenes. |
| `GET` | `/api/ingest/scenes` | Lists all ingested scenes with metadata and tile counts. |
| `POST` | `/api/feedback` | Records analyst `confirm` / `reject` decisions and notes. |
| `POST` | `/api/chat` | AI Evidence Assistant query endpoint. |
| `GET` | `/api/system/status` | System health, offline status, model staging flags, and vector counts. |
