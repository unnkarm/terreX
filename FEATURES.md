# TerreX — Platform Features & Capabilities Specification

> **TerreX** is an air-gapped, offline AI platform for natural language semantic satellite imagery search and bi-temporal change detection, built around Indian Earth Observation (ISRO) architectures and Sentinel-2 multispectral imagery.

---

## 1. Core Architecture & Design Principles

* **Strict Offline Air-Gap (Zero Cloud Egress)**:
  * Hard environment isolation guards: `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and `PROJ_NETWORK=OFF`.
  * Fully self-contained local stack without external CDN or cloud API dependencies.
* **Hybrid Geospatial & Vector Storage Stack**:
  * **Qdrant Vector Database**: Indexes high-dimensional visual & textual embeddings (512-D vectors) with HNSW indexing for sub-second semantic retrieval.
  * **PostgreSQL 16 + PostGIS**: Enforces spatial boundary filters (EPSG:4326 geometry), multi-temporal timestamp indexing, analyst feedback logs, and metadata cataloging.
* **Local Microservices Architecture**:
  * **Frontend**: Next.js 14 App Router, Tailwind CSS, MapLibre GL, and Tactical HUD (Port `3001`).
  * **Backend**: FastAPI, Python 3.11, GDAL 3.6, Rasterio, NumPy, SciPy, Pillow, SQLAlchemy (Port `8000`).
  * **Databases**: PostGIS (Port `5432`), Qdrant (Port `6333`).

---

## 2. The 5 Core SIH MVP Capabilities

### 🔎 Feature 1: Semantic Natural-Language Satellite Search
* **Text-to-Image Search**:
  * Translates natural language queries (e.g., *"new buildings near a river"*, *"cleared forest parcel"*, *"sandbar expansion"*, *"industrial construction"*) into high-dimensional vector representations using **RemoteCLIP** (ViT-B/32 trained on overhead satellite imagery).
  * Measures cosine similarity against indexed satellite tile embeddings.
* **Reverse Image-to-Image Search**:
  * Drag and drop any reference satellite chip, aerial photo, or multi-band GeoTIFF patch to find spectrally and structurally similar tiles across the archive.
* **Multi-Parameter PostGIS Filtering**:
  * Real-time spatial bounding box filter (`min_lon`, `min_lat`, `max_lon`, `max_lat`).
  * Acquisition date range window (`date_from`, `date_to`).
  * Sensor filter (Sentinel-2, Resourcesat-2, Landsat-8, EOS-04 SAR).
  * Cloud cover tolerance limit.
* **Transparent Composite Ranking**:
  * Every search result card provides an explainable composite rank:
    $$\text{Final Score} = 0.50 \cdot \text{Semantic Match} + 0.20 \cdot \text{Data Quality} + 0.15 \cdot \text{Geographic Proximity} + 0.15 \cdot \text{Metadata Match}$$

---

### 🛰️ Feature 2: Multi-Source Indian Earth Observation Ingestion Pipeline
* **Indian Satellite Adapters**:
  * **ISRO/NRSC Bhuvan**:
    * **Resourcesat-2 LISS-III** (23.5m spatial resolution, 4 bands: Green, Red, NIR, SWIR).
    * **Resourcesat-2 AWiFS** (56m spatial resolution, wide swath monitoring).
  * **ISRO MOSDAC**:
    * **EOS-04 (RISAT-1A)** C-Band Synthetic Aperture Radar (SAR) with cloud-penetrating capability and Fine Resolution Stripmap mode.
    * **Oceansat-3 Ocean Colour Monitor (OCM-3)** for coastal and estuary sediment monitoring.
  * **ESA Sentinel-2 Level-2A**:
    * Primary high-frequency multispectral ML baseline (10m resolution, 12 spectral bands, bottom-of-atmosphere reflectance).
* **Format Normalization & Tiling Engine**:
  * Converts diverse sensor data formats into standardized Cloud-Optimized GeoTIFFs (COGs).
  * Slices large raster granules into deterministic $256 \times 256$ pixel chips.
  * Preserves native CRS transforms, geographic bounds, and GDAL tags.
* **Quality & Cloud Masking**:
  * Scene Classification Layer (SCL) pixel evaluation to automatically filter and discard cloudy, shadowed, or invalid tiles ($< 20\%$ usable pixels) before vectorization.

---

### 🔄 Feature 3: Bi-Temporal Change Detection & 4-Class Semantic Typing
* **Sub-Pixel Spatial Co-Registration**:
  * Uses pure-array ORB keypoint detection and RANSAC affine/homography warp estimation to align $T_0$ (baseline) and $T_1$ (recent) observation pairs before diffing.
  * Eliminates false alarms caused by sensor tilt, satellite viewing angle variations, or parallax shifts.
* **Relative Radiometric Normalization**:
  * Histogram matching between acquisition dates to equalize seasonal sun-angle variations and atmospheric conditions.
* **Layer-1 Feature Differencing**:
  * Deep Siamese spatial feature differencing (powered by **Prithvi-EO**) producing a per-pixel change probability map ($0.0$ to $1.0$).
* **Layer-2 Morphological & Spectral Change Typing**:
  * Classifies detected change regions into the 4 official problem statement categories:
    1. **Construction**: $\downarrow\text{NDVI} + \uparrow\text{NDBI}$ (high SWIR & built-up masonry response).
    2. **Clearance**: $\downarrow\text{NDVI}$ without urban built-up materials or water signatures.
    3. **Water Extent Variation**: $\uparrow\text{NDWI}$ with negative NDBI water absorption response.
    4. **Road Development**: High linear aspect ratio / elongation ($> 3.0$) matching infrastructure reflectance profiles.

---

### 🛡️ Feature 4: Explainable Confidence & Automated False-Alarm Suppression
* **Automated Suppression Engine**:
  * Cross-references detected changes against physical confounders:
    * Persistent cloud, haze, or cloud-shadow presence.
    * Agricultural phenology (cyclical crop sowing and harvesting cycles).
    * Co-registration inlier thresholds.
* **Confidence & Rationale Checklist**:
  * Displays an itemized checklist of suppression reasons and validation criteria in the evidence panel.
* **Ground Surface Area Measurement**:
  * Calculates exact affected surface area in both **square meters ($m^2$)** and **hectares**.
* **Earliest Supported Observation**:
  * Pinpoints the specific historical observation date where the physical change first manifested in the satellite record.

---

### 📋 Feature 5: Analyst Review & Active Learning Feedback Loop
* **Operational Review Queue (`/review`)**:
  * High-throughput verification interface for intelligence analysts to audit automated detections.
* **Audited Decision Logging**:
  * Analysts can issue formal **CONFIRM** or **REJECT** verdicts with mandatory or optional domain rationale notes.
  * Verdicts are persisted in the `feedback` table linked to tile IDs and change result IDs.
* **Active Learning Ready**:
  * Logged analyst feedback forms a curated dataset for offline fine-tuning and confidence calibration.
* **Standardized GIS Export**:
  * One-click GeoJSON export containing bounding polygons, centroids, confidence scores, and spectral metrics for direct import into QGIS or ArcGIS.

---

## 3. Indian Strategic Corridors (One-Click Presets)

TerreX includes pre-calibrated spatial bounding boxes and monitoring corridors across India:

1. **📍 Kolkata New Town / Rajarhat Corridor (Default)**
   * *Coordinates*: `[88.25, 22.45, 88.48, 22.65]`
   * *Monitoring Focus*: Rapid urban expansion, wetland boundary encroachment, and infrastructure development east of the Hooghly River.
2. **📍 Delhi NCR / Yamuna Floodplain Basin**
   * *Coordinates*: `[77.10, 28.50, 77.35, 28.75]`
   * *Monitoring Focus*: Floodplain encroachment, sand extraction, seasonal vegetation dynamics, and transport corridor extensions.
3. **📍 Bengaluru Outer Ring Road & Tech Corridors**
   * *Coordinates*: `[77.50, 12.80, 77.80, 13.10]`
   * *Monitoring Focus*: Tech park development, lake-bed preservation, vegetation clearance, and peripheral road building.
4. **📍 Ahmedabad Sabarmati Riverfront Development**
   * *Coordinates*: `[72.50, 22.95, 72.65, 23.10]`
   * *Monitoring Focus*: Riverbank reclamation, urban riverfront expansion, and industrial periphery zoning.
5. **📍 Mumbai Trans-Harbour Link (MTHL) & Navi Mumbai**
   * *Coordinates*: `[72.90, 18.90, 73.05, 19.05]`
   * *Monitoring Focus*: Coastal infrastructure, tidal flat modifications, airport construction, and bridge landings.

---

## 4. Tactical User Interface & Visual HUD

* **Authentic Top-Down Satellite Visuals**:
  * The before/after slider and preview queues strictly render orthorectified nadir satellite captures from orbit, avoiding hand-held or horizon landscape stock photos.
* **Multi-Spectral & Radiometric Layer Toggles**:
  * **True Color (RGB)**: Natural color composite.
  * **Change Mask**: Per-pixel probability change overlay.
  * **$\Delta$NDVI**: Normalized Difference Vegetation Index change (vegetation loss/gain).
  * **$\Delta$NDWI**: Normalized Difference Water Index change (water boundary shifts).
  * **$\Delta$NDBI**: Normalized Difference Built-up Index change (concrete and masonry emergence).
  * **Confidence Overlay**: Color-coded probability heatmaps.
* **Interactive Before / After Split Slider**:
  * Smooth curtain slider with **SPLIT**, **BEFORE**, **AFTER**, **MASK**, and **BLEND** viewing modes.
* **AI Evidence Assistant Panel**:
  * Scoped chat assistant powered by a local LangGraph workflow and local Ollama daemon.
  * Directly interrogates tile metadata, spectral delta values, and change provenance without data leaving the machine.

---

## 5. Complete API Catalog

### Ingestion & Data Sources (`/api/ingest`)
* `GET /api/ingest/eo-providers`: Lists available data providers (Sentinel-2, ISRO Bhuvan, ISRO MOSDAC).
* `POST /api/ingest/search-provider`: Queries provider archives for satellite passes matching an AOI and date range.
* `POST /api/ingest/stage-provider`: Normalizes an Indian EO pass into a Cloud-Optimized GeoTIFF in `data/incoming/`.
* `POST /api/ingest/upload`: Directly uploads and ingests a custom GeoTIFF file.
* `POST /api/ingest/process-incoming`: Scans `data/incoming/` for new scenes, tiles them, and updates Qdrant and PostGIS.
* `GET /api/ingest/scenes`: Lists all registered scenes, quality scores, and chip counts.

### Search Engine (`/api/search`)
* `GET /api/search/text`: Natural language semantic search with optional spatial bounding box and date filters.
* `POST /api/search/image`: Reverse image search using uploaded satellite chips or crops.

### Change Detection (`/api/change`)
* `GET /api/change/detect`: Runs bi-temporal change detection between two dates for a coordinate point.
* `POST /api/change/detect`: JSON payload change detection supporting custom bounding boxes and scene IDs.
* `GET /api/change/results`: Lists historical persisted change results and classified regions.

### Analyst Feedback (`/api/feedback`)
* `POST /api/feedback/submit`: Logs an analyst's CONFIRM or REJECT verdict with notes.
* `GET /api/feedback/stats`: Returns verification statistics and confirmed vs. rejected ratios.

### System Diagnostics & Chat (`/api/system`, `/api/chat`)
* `GET /api/system/status`: Returns air-gap verification, active model checkpoints, and database health.
* `POST /api/chat`: Interacts with the local LangGraph evidence assistant.
* `GET /api/chat/status`: Reports Ollama reachability, model availability, and RAM budget.
