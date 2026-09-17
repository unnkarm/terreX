# terreX System Architecture

terreX is a specialized **Retrieval-Augmented Generation (RAG)** platform designed specifically for Earth Observation (EO) and geospatial satellite imagery. It allows analysts to interact with massive satellite archives using natural language, visual similarity, and automated AI change detection, operating entirely in an offline, air-gapped environment.


## 1. High-Level System Components

The platform is split into a decoupled **Frontend (Next.js/React)** and **Backend (FastAPI/Python)** architecture, communicating via RESTful APIs.

### The Stack
- **Frontend**: Next.js, React, Tailwind CSS, Mapbox GL JS
- **Backend API**: FastAPI, Uvicorn
- **Databases**: 
  - **Qdrant**: Vector Database for high-speed semantic search.
  - **PostgreSQL / SQLite**: Relational database for metadata, provenance, and audit logging (via SQLAlchemy).
- **Core Processing**: PyTorch, Rasterio, OpenCV, NumPy
- **Foundation Models**: RemoteCLIP, Prithvi-EO (NASA/IBM)

---

## 2. Backend Architecture & Data Pipelines

The backend is strictly modularized into distinct services to handle the complexities of geospatial data processing.

### A. The Ingestion Pipeline (`services/ingestion.py`)
Handling raw satellite imagery (GeoTIFFs) requires careful memory management, as files can exceed tens of gigabytes.
1. **Windowed Streaming**: `rasterio` reads the imagery in small chunks (e.g., 256x256 pixels) to prevent RAM overflows.
2. **Quality Assessment**: Each tile is evaluated for cloud cover fraction and image sharpness. Low-quality tiles are discarded.
3. **Data Extraction**: 
   - Generates an RGB thumbnail (using joint-percentile normalization) for the UI.
   - Saves the raw multispectral data (including Near-Infrared, SWIR, etc.) into a compressed `.npz` file for future analytical workflows.
4. **Embedding Generation**: The tile is passed through the vision-language model to create a semantic vector.
5. **Storage**: The vector is pushed to Qdrant, and the geospatial metadata (Lat/Lon bounding boxes, acquisition date) is pushed to the relational database.

### B. The Search & Retrieval Engine (`services/search.py`)
This engine implements the core RAG retrieval capabilities.
- **Text-to-Image**: A natural language query is converted to a vector and matched against the Qdrant database using Cosine Similarity.
- **Image-to-Image (Seed Discovery)**: A reference image (or an existing map tile) is vectorized and matched against the database.
- **Hybrid Filtering**: Semantic searches are pre-filtered using Qdrant's payload indexes (e.g., applying strict Date Range, Sensor Type, and Bounding Box filters before vector matching).

### C. Multi-Temporal Change Detection (`services/algorithms/`, `services/change_detection.py`)
A specialized pipeline to analyze what changed in a specific Area of Interest (AOI) over a given time window. Rather than relying on a single embedding difference, it derives **three independent lines of evidence** per pixel and requires them to corroborate each other before raising a detection.

1. **Co-Registration**: Aligns the "Before" and "After" images (ORB + RANSAC affine, FFT phase-correlation fallback) and measures the misalignment *remaining after* the warp.
2. **Cloud / Quality Masking**: Builds a per-pixel usable mask from the Sentinel-2 scene-classification plane where available, otherwise a brightness/whiteness/NIR heuristic. Cloud and shadow are dilated to catch their haloes. Masked pixels are excluded from every subsequent stage.
3. **Radiometric Normalization**: Fits a per-band gain/offset on *pseudo-invariant* clear pixels, correcting sun angle, atmosphere and sensor gain without normalising genuine change away.
4. **Evidence Layers**: (a) **deep feature divergence** from the **Prithvi-EO** foundation model, (b) **spectral divergence** via Change Vector Analysis plus NDVI/NDWI/NDBI shift, (c) **spatial/context consistency** from local structural dissimilarity and texture energy — invariant to illumination by construction.
5. **Evidence Fusion**: Combines the layers weighted by how trustworthy each is for *this* image pair, damping any detection that rests on a single line of evidence.
6. **False-Alarm Suppression**: Removes change under cloud/shadow, discounts edges in proportion to measured registration residual, requires neighbourhood corroboration, and clears morphological speckle.
7. **Change Typing & Confidence**: Classifies connected regions as Construction, Clearance, Water Extent or Road Development, tempers each region's confidence by the evidence supporting it, and corroborates across the rest of the observation stack.

Every stage emits an auditable record (status, explanation, metrics) that the analyst UI surfaces. See **[`change_detection_pipeline.md`](change_detection_pipeline.md)** for the full design, calibration and verification results.

---

## 3. The Foundation Models (AI Layer)

terreX relies on two specialized Earth Observation models, engineered to run locally without internet access.

- **RemoteCLIP**: A vision-language model explicitly trained on remote sensing data. It links natural language concepts (e.g., "airport runway") with the visual patterns found in satellite imagery. Used for all search and retrieval tasks.
- **Prithvi-EO (NASA/IBM)**: A massive Vision Transformer (ViT) pre-trained on harmonized Landsat and Sentinel-2 data. Because it natively understands multispectral physics and temporal changes, it is used exclusively as the engine for the Change Detection pipeline.

### "Placeholder Mode" (Hardware Graceful Degradation)
To support development and deployment on hardware lacking dedicated GPUs (e.g., standard laptops), the system implements a `Placeholder` design pattern. If the massive AI weights cannot be loaded into VRAM, the backend automatically falls back to classical computer vision algorithms (perceptual hashing, statistical patch features). This allows the entire pipeline, databases, and UI to function seamlessly on CPU-only hardware for testing.

In change detection this degradation is **graded rather than silent**: each evidence layer carries a reliability weight, so placeholder features drop the deep layer's influence to 0.5 and RGB-only tiles drop the spectral layer's to 0.55. The detector keeps working, reports lower confidence, and names the reason in its stage audit.

---

## 4. Frontend Architecture (UI/UX)

The frontend is a single-page application built on Next.js, prioritizing a "tactical, space-tech" aesthetic suitable for military or high-end intelligence analysts.

- **Workspace Map (`MapView.tsx`)**: The core interface is a full-bleed interactive map powered by Mapbox GL JS. Satellite chips are rendered as interactive geo-json polygons directly on the grid.
- **Floating UI Elements**: The application abandons traditional sidebars in favor of high-z-index, floating pill-shaped components with glassmorphism (e.g., the Gemini-style Search Bar).
- **Target Inspection (`ResultDetail.tsx`)**: A dedicated panel for auditing results. It surfaces all backend provenance, quality scores, and change-detection controls, ensuring the analyst has full transparency into why the AI made a decision.
- **Dedicated Ingestion Dashboard (`/ingest`)**: An independent route managing the flow of new data into the system, featuring drag-and-drop uploads, real-time terminal logs, and empty-state database protection.
