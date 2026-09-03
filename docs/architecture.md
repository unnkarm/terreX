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

### C. Multi-Temporal Change Detection (`services/change_detection.py`)
A highly specialized pipeline to analyze what changed in a specific Area of Interest (AOI) over a given time window.
1. **Co-Registration**: Mathematically aligns the "Before" and "After" multispectral images to ensure pixel-perfect overlap.
2. **Radiometric Normalization**: Adjusts histograms to account for differing sun angles, seasons, or atmospheric conditions.
3. **AI Feature Diffing**: Passes both images through the **Prithvi-EO** foundation model and calculates the difference between their deep features (Siamese network approach).
4. **Spectral Classification**: Uses standard remote sensing indices (NDVI, NDWI, NDBI) on the changed pixels to classify the event as Construction, Clearance, Flooding, etc.
5. **False-Alarm Suppression**: Evaluates temporal consistency to ignore fleeting anomalies like passing clouds or shadows.

---

## 3. The Foundation Models (AI Layer)

terreX relies on two specialized Earth Observation models, engineered to run locally without internet access.

- **RemoteCLIP**: A vision-language model explicitly trained on remote sensing data. It links natural language concepts (e.g., "airport runway") with the visual patterns found in satellite imagery. Used for all search and retrieval tasks.
- **Prithvi-EO (NASA/IBM)**: A massive Vision Transformer (ViT) pre-trained on harmonized Landsat and Sentinel-2 data. Because it natively understands multispectral physics and temporal changes, it is used exclusively as the engine for the Change Detection pipeline.

### "Placeholder Mode" (Hardware Graceful Degradation)
To support development and deployment on hardware lacking dedicated GPUs (e.g., standard laptops), the system implements a `Placeholder` design pattern. If the massive AI weights cannot be loaded into VRAM, the backend automatically falls back to utilizing classical computer vision algorithms (like perceptual hashing and standard difference maps). This allows the entire pipeline, databases, and UI to function seamlessly on CPU-only hardware for testing.

---

## 4. Frontend Architecture (UI/UX)

The frontend is a single-page application built on Next.js, prioritizing a "tactical, space-tech" aesthetic suitable for military or high-end intelligence analysts.

- **Workspace Map (`MapView.tsx`)**: The core interface is a full-bleed interactive map powered by Mapbox GL JS. Satellite chips are rendered as interactive geo-json polygons directly on the grid.
- **Floating UI Elements**: The application abandons traditional sidebars in favor of high-z-index, floating pill-shaped components with glassmorphism (e.g., the Gemini-style Search Bar).
- **Target Inspection (`ResultDetail.tsx`)**: A dedicated panel for auditing results. It surfaces all backend provenance, quality scores, and change-detection controls, ensuring the analyst has full transparency into why the AI made a decision.
- **Dedicated Ingestion Dashboard (`/ingest`)**: An independent route managing the flow of new data into the system, featuring drag-and-drop uploads, real-time terminal logs, and empty-state database protection.
