# TerreX

### Offline Geospatial Intelligence & Satellite Change Detection

> **Search the Earth. Detect what changed. Understand why.**

TerreX is an **offline, on-premise geospatial intelligence platform** for discovering and detecting meaningful changes in satellite imagery.

Its core is a **multi-evidence change-detection engine** that combines deep Earth-observation features, spectral information, spatial consistency, image registration, and quality analysis to distinguish genuine physical changes from false alarms caused by clouds, seasonal variation, illumination, or misregistration.

---

## 🎯 Core Problem

Satellite archives are growing rapidly across multiple sensors, locations, and acquisition dates. Traditional metadata-based systems require analysts to already know **where and when** to look.

TerreX addresses two connected problems:

1. **Discover relevant locations** using semantic and visual retrieval.
2. **Reliably determine what changed** between satellite observations while suppressing false alarms.

The primary analytical focus is robust change detection.

---

## ✨ Features

* 🛰️ Multi-temporal satellite change detection
* 🏗️ Construction detection
* 🛣️ Road development detection
* 🌳 Land/vegetation clearance detection
* 💧 Water-extent variation detection
* 🧠 Deep Earth-observation feature comparison
* 🌿 NDVI / NDWI / NDBI analysis
* 📐 Image registration and alignment
* ☁️ Cloud and quality masking
* 🔆 Radiometric normalization
* 🚨 False-alarm suppression
* 🗺️ Semantic satellite-image retrieval
* 🖼️ Image-to-image search
* 🔎 Similar-location discovery
* 📊 Confidence and evidence reporting
* 👨‍💻 Analyst confirm/reject workflow
* 📜 Source and processing provenance
* ➕ Incremental archive ingestion
* 📴 Fully offline/on-premise execution

---

# 🧠 Core Change Detection

TerreX does **not** assume that every image difference represents physical change.

The central pipeline is:

```text
             BEFORE + AFTER
                    │
                    ▼
            Image Registration
                    │
                    ▼
          Radiometric Normalization
                    │
                    ▼
          Cloud / Quality Masking
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
    Prithvi-EO            Spectral Analysis
   Feature Difference     NDVI / NDWI / NDBI
          │                   │
          └─────────┬─────────┘
                    ▼
            Spatial Consistency
                    │
                    ▼
             Evidence Fusion
                    │
                    ▼
          False-Alarm Suppression
                    │
                    ▼
            Change Probability
                    │
                    ▼
               Change Mask
                    │
                    ▼
          Change Classification
                    │
                    ▼
        Confidence + Evidence
```

### Change Score

A conceptual change score is:

$$
C(x,y)=w_fD_f(x,y)+w_sD_s(x,y)+w_pD_p(x,y)
$$

Where:

* \(D_f\) = deep feature difference
* \(D_s\) = spectral difference
* \(D_p\) = spatial/contextual consistency
* \(w_f,w_s,w_p\) = configurable weights

The result is further adjusted using image quality, registration quality, and temporal evidence.

---

# 🔬 Detection Pipeline

## 1. Registration

Before comparing observations, TerreX aligns them spatially.

Techniques include:

* ORB feature detection
* Feature matching
* RANSAC
* Affine transformation
* Phase-correlation fallback

A **registration-quality score** is generated so poorly aligned observations can be rejected or down-weighted.

---

## 2. Radiometric Normalization

Observations may differ because of:

* Illumination
* Atmospheric conditions
* Sensor characteristics
* Acquisition geometry
* Overall brightness

TerreX applies normalization before change analysis to reduce these effects.

---

## 3. Quality & Cloud Handling

The system evaluates:

* Cloud contamination
* Haze
* Valid pixels
* Missing data
* Image sharpness
* Registration quality

Poor-quality regions are masked or assigned lower confidence.

---

## 4. Deep Feature Difference

TerreX uses **Prithvi-EO** for Earth-observation feature extraction.

For before and after observations:

$$
F_b=Model(I_b)
$$

$$
F_a=Model(I_a)
$$

The feature difference is:

$$
D_f=|F_a-F_b|
$$

This provides higher-level representations beyond simple pixel differences.

---

## 5. Spectral Evidence

TerreX calculates interpretable spectral indices.

### NDVI

$$
NDVI=\frac{NIR-Red}{NIR+Red}
$$

Useful for vegetation-related changes.

### NDWI

$$
NDWI=\frac{Green-NIR}{Green+NIR}
$$

Useful for water-related changes.

### NDBI

$$
NDBI=\frac{SWIR-NIR}{SWIR+NIR}
$$

Useful as evidence for built-up areas.

Temporal differences are calculated as:

```text
ΔNDVI = NDVI_after - NDVI_before
ΔNDWI = NDWI_after - NDWI_before
ΔNDBI = NDBI_after - NDBI_before
```

---

## 6. Spatial Consistency

Real changes usually form meaningful regions rather than isolated pixels.

TerreX uses:

* Neighbourhood agreement
* Connected components
* Minimum region size
* Morphological filtering
* Spatial continuity

This helps eliminate isolated noisy detections.

---

# 🚨 False-Alarm Suppression

False-alarm suppression is a major component of TerreX.

| Confounder             | Mitigation                        |
| ---------------------- | --------------------------------- |
| Clouds                 | Cloud / quality masking           |
| Haze                   | Quality analysis + normalization  |
| Shadows                | Spatial and spectral consistency  |
| Seasonal vegetation    | Spectral + temporal evidence      |
| Illumination           | Radiometric normalization         |
| View-angle differences | Registration + confidence         |
| Misregistration        | Registration-quality score        |
| Missing pixels         | Valid-pixel masking               |
| Isolated noise         | Spatial filtering                 |
| Sensor differences     | Normalization + quality weighting |

The system therefore distinguishes:

```text
Image Difference
       ≠
Physical Change
```

---

# 🏷️ Change Classification

TerreX currently focuses on four major change categories:

### 🏗️ Construction

Evidence may include:

* Increased NDBI
* Deep feature change
* Spatially coherent structural regions
* Consistent observations

### 🛣️ Road Development

Evidence may include:

* Linear spatial structures
* Persistent feature differences
* Expansion around transportation networks

### 🌳 Clearance

Evidence may include:

* NDVI decrease
* Deep feature change
* Spatially coherent cleared regions

### 💧 Water Variation

Evidence may include:

* NDWI variation
* Water-boundary movement
* Spatial consistency
* Temporal confirmation

If evidence is insufficient, TerreX can return:

```text
Unknown / Other Change
```

rather than forcing a classification.

---

# 📅 Temporal Analysis

The primary detection task uses temporally adjacent observations:

```text
T1 ───────────────► T2
        CHANGE?
```

Additional observations may be used for persistence:

```text
T1 ─────► T2 ─────► T3
               │
        Persistence Check
```

The larger archive can also be searched to estimate the **earliest available observation supporting a detected change**.

The goal is to keep the main detection algorithm efficient rather than performing unnecessary full-history comparisons.

---

# 🔎 Semantic Retrieval

TerreX provides semantic discovery over the satellite archive.

Example:

```text
"newly built structures near a river"
```

or:

```text
"large vehicle concentrations on open ground"
```

The retrieval pipeline is:

```text
Natural Language Query
          │
          ▼
    Query Understanding
          │
          ▼
   RemoteCLIP Embedding
          │
          ▼
      Qdrant Search
          │
          ▼
Spatial / Temporal / Sensor Filters
          │
          ▼
   Candidate Locations
          │
          ▼
    Change Detection
```

Semantic retrieval is primarily a **candidate-generation layer** for the change engine.

---

# 🖼️ Image-to-Image Search

Users can provide an image or tile and search for visually similar locations.

```text
Input Image
     ↓
RemoteCLIP Image Embedding
     ↓
Qdrant Similarity Search
     ↓
Similar Locations
     ↓
Optional Change Analysis
```

---

# 🧩 Discovery & Clustering

Embedding representations can be used to group similar locations.

A user can:

1. Find an interesting site.
2. Use it as a seed.
3. Retrieve similar sites.
4. Apply geographic/temporal filters.
5. Run change analysis.

This supports discovery without manually searching for every location.

---

# 🏗️ System Architecture

```text
                         TERREX
                            │
              ┌─────────────┴─────────────┐
              │                           │
       Semantic Search              Image Search
       RemoteCLIP/Qdrant            RemoteCLIP/Qdrant
              │                           │
              └─────────────┬─────────────┘
                            ▼
                    Candidate Locations
                            │
                            ▼
                  ┌──────────────────┐
                  │  CHANGE ENGINE   │
                  └────────┬─────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   Registration      Prithvi-EO          Spectral
   + Quality         Features            Indices
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ▼
                  Evidence Fusion
                           │
                           ▼
                False-Alarm Suppression
                           │
                           ▼
                  Change Classification
                           │
                           ▼
                Confidence + Evidence
                           │
                           ▼
                    Analyst Review
                           │
                           ▼
                 Provenance + Feedback
```

---

# 📥 Data Ingestion

TerreX supports satellite imagery stored locally as GeoTIFF/COG.

The ingestion pipeline is:

```text
GeoTIFF / COG
      ↓
Metadata Validation
      ↓
Quality Assessment
      ↓
256 × 256 Tiling
      ↓
Spectral Indices
      ↓
Thumbnail Generation
      ↓
RemoteCLIP Embeddings
      ↓
Qdrant + PostgreSQL
```

Each tile retains its source-scene and acquisition information.

---

# 🛰️ Target Data Sources

TerreX is designed to work with publicly available Earth-observation data, including:

* Sentinel-2
* Sentinel-1
* Landsat-8
* ISRO Bhuvan resources
* ISRO MOSDAC products

Evaluation datasets should follow the applicable competition/problem-statement requirements.

---

# 🗃️ Storage Architecture

## PostgreSQL + PostGIS

Used for:

* Scene metadata
* Tile metadata
* Spatial information
* Acquisition dates
* Sensor information
* Change results
* Provenance
* Analyst feedback

## Qdrant

Used for:

* Semantic vector search
* Image similarity
* Similar-location discovery

The architecture supports incremental ingestion without rebuilding the complete archive.

---

# 🧠 Models

| Model / Technology  | Role                                 |
| ------------------- | ------------------------------------ |
| **Prithvi-EO**      | Deep Earth-observation features      |
| **RemoteCLIP**      | Semantic + visual retrieval          |
| **GLiNER**          | Natural-language query understanding |
| **Qwen 2.5**        | Optional evidence-based explanation  |
| **Qdrant**          | Vector similarity search             |
| **OpenCV**          | Registration / computer vision       |
| **Rasterio / GDAL** | Raster processing                    |
| **PostGIS**         | Geospatial storage                   |

> Qwen is an explanation layer, not the change detector.

---

# 👨‍💻 Analyst Workflow

Each detected change can be presented as:

```text
CHANGE DETECTED
────────────────────────────

Type: Construction
Confidence: 91%
Changed Area: 0.42 ha

BEFORE
Sentinel-2
12 Jan 2025

AFTER
Sentinel-2
28 Mar 2025

Evidence
✓ Deep feature difference
✓ NDBI increase
✓ Spatial consistency
✓ Good registration
✓ Low cloud contamination

[ CONFIRM ]    [ REJECT ]
```

Analyst actions can be stored as feedback for ranking/refinement.

---

# 📜 Provenance

TerreX preserves the analytical chain:

```text
Source Scene
     ↓
Acquisition Metadata
     ↓
Tile
     ↓
Preprocessing
     ↓
Registration
     ↓
Normalization
     ↓
Feature Extraction
     ↓
Change Detection
     ↓
Classification
     ↓
Confidence
     ↓
Analyst Decision
```

This allows detected changes to be traced back to their source imagery and processing steps.

---

# 📴 Offline Architecture

TerreX is designed to run without external network access after required models, datasets, and dependencies have been staged locally.

```text
Satellite Data
      ↓
Local Storage
      ↓
Local Processing
      ↓
Local Models
      ↓
Local PostgreSQL
      ↓
Local Qdrant
      ↓
Local API
      ↓
Local Frontend
```

Relevant offline configuration:

```bash
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
PROJ_NETWORK=OFF
```

No cloud inference or external API is required for the core pipeline.

---

# 🛠️ Technology Stack

### Backend

* Python
* FastAPI
* Uvicorn

### Machine Learning

* PyTorch
* Prithvi-EO
* RemoteCLIP
* GLiNER
* ONNX Runtime

### Geospatial

* GDAL
* Rasterio
* Shapely
* GeoAlchemy
* PostGIS

### Search

* Qdrant

### Computer Vision

* OpenCV

### Frontend

* Next.js
* React

### Optional LLM

* Ollama
* Qwen 2.5

---

# 📁 Project Structure

```text
TerreX/
│
├── backend/
│   ├── api/
│   ├── models/
│   ├── services/
│   ├── change_detection/
│   ├── retrieval/
│   ├── ingestion/
│   └── geospatial/
│
├── frontend/
│   ├── app/
│   ├── components/
│   └── services/
│
├── models/
│   ├── prithvi/
│   ├── remoteclip/
│   ├── gliner/
│   └── qwen/
│
├── data/
│   ├── scenes/
│   ├── tiles/
│   └── benchmark/
│
├── scripts/
│   ├── ingest/
│   ├── indexing/
│   ├── evaluation/
│   └── demo/
│
├── requirements.txt
└── README.md
```

---

# 🚀 Installation

## Requirements

* Python 3.10+
* Node.js 18+
* PostgreSQL + PostGIS
* Qdrant
* GDAL
* Git

GPU inference is recommended for deep-model processing.

### Backend

```bash
cd backend

python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

### Database

```sql
CREATE DATABASE terrex;

\c terrex

CREATE EXTENSION postgis;
```

Configure the local PostgreSQL connection using the project environment configuration.

### Backend

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

# 🧪 Evaluation

TerreX should be evaluated using a held-out benchmark containing:

### Positive Cases

* Construction
* Road development
* Clearance
* Water variation

### Negative Cases

* No physical change

### Hard Negatives

* Seasonal vegetation
* Clouds
* Shadows
* Haze
* Illumination changes
* Registration errors
* Radiometric differences

The hard-negative set is particularly important for evaluating false-alarm suppression.

---

## Metrics

Primary change-detection metrics:

* Precision
* Recall
* F1 Score
* IoU
* False Positive Rate

$$
Precision=\frac{TP}{TP+FP}
$$

$$
Recall=\frac{TP}{TP+FN}
$$

$$
F1=2\frac{Precision\cdot Recall}{Precision+Recall}
$$

$$
IoU=\frac{TP}{TP+FP+FN}
$$

In addition to overall metrics, false positives should be broken down by confounder type.

---

# 📊 Reproducibility

Evaluation reports should document:

### Dataset

* Indexed area
* Number of scenes
* Number of tiles
* Sensors
* Acquisition period
* Positive cases
* Negative cases
* Hard negatives

### Models

* Model name
* Version
* Source
* Licence
* Weights
* Preprocessing

### System

* CPU/GPU
* RAM
* Storage
* Index-build time
* Incremental ingestion time
* Query latency
* Change-detection latency

---

# ⚠️ Current Limitations

* Performance depends on the quality of available pretrained model weights.
* Registration can be difficult in visually homogeneous areas.
* Cross-sensor comparison requires careful normalization.
* Optical and SAR imagery have fundamentally different characteristics.
* Change classification is currently limited to supported categories.
* Synthetic imagery is useful for pipeline testing but should not replace real evaluation data.
* Feedback-aware reranking is not equivalent to continual model training.
* Approximate georeferencing should be replaced with rigorous affine/reprojection handling where required.

---

# 🗺️ Roadmap

### Core Algorithm

* [ ] Robust registration
* [ ] Registration-quality estimation
* [ ] Radiometric normalization
* [ ] Cloud/quality masking
* [ ] Prithvi feature extraction
* [ ] Deep feature differencing
* [ ] Spectral differencing
* [ ] Spatial consistency
* [ ] Evidence fusion
* [ ] False-alarm suppression
* [ ] Change probability maps

### Change Understanding

* [ ] Construction detection
* [ ] Road development detection
* [ ] Clearance detection
* [ ] Water variation detection
* [ ] Confidence calibration
* [ ] Changed-area estimation
* [ ] Temporal persistence

### Retrieval

* [ ] Semantic search
* [ ] Image-to-image search
* [ ] Spatial filtering
* [ ] Temporal filtering
* [ ] Sensor filtering
* [ ] Similar-location discovery

### Deployment

* [ ] Fully offline packaging
* [ ] Incremental ingestion
* [ ] Benchmark automation
* [ ] Ablation studies
* [ ] Latency profiling

---

# 🔐 Model & Dataset Provenance

Every external model or dataset should document:

```text
Name
Version
Source
Provider / Repository
Licence
Weights Version
Preprocessing
Modifications
Intended Use
```

All evaluation data should comply with the applicable problem-statement and licensing requirements.

---

# 🎯 Research Focus

The central technical question behind TerreX is:

> **How can meaningful physical changes be reliably detected between satellite observations while minimizing false alarms caused by environmental and imaging artifacts?**

TerreX approaches this as an **evidence-fusion problem**:

```text
Deep EO Features
       +
Spectral Evidence
       +
Spatial Evidence
       +
Registration Quality
       +
Image Quality
       +
Temporal Evidence
       ↓
Robust Change Detection
```

---

# 📄 License

Add the project's primary license here.

Third-party models, datasets, and pretrained weights may have separate licensing and attribution requirements.

---

## 👥 TerreX

**TerreX — Search the Earth. Detect what changed. Understand why.**

