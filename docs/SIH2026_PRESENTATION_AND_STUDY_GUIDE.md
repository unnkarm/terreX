# TerreX SIH 2026 Presentation and Study Guide

## Ground rules for this deck

- The provided SIH template permits **six slides in total, including the title slide**. Delete its final instruction slide before export.
- Keep the narrative focused on SIH PS #26227: **Semantic Retrieval and Multi-Temporal Change Analysis of Satellite Imagery**.
- Use only results measured on the team's own held-out data. Do not present estimated latency, accuracy, hardware footprint, or model performance as a achieved result.
- Say **"air-gapped design"** only after the full demo works with network access disabled. Confirm the active model state before presenting. The code deliberately labels fallback embeddings and feature extraction as placeholders when local RemoteCLIP or Prithvi weights are not staged.

## Six-slide story

### Slide 1 — Title page

**Title**

`TerreX`

**Subtitle**

`Offline Satellite Imagery Search and Change Intelligence`

**Fill the template fields**

| Field | Text |
| --- | --- |
| Problem Statement ID | 26227 |
| Problem Statement Title | Semantic Retrieval and Multi-Temporal Change Analysis of Satellite Imagery |
| Theme | Space Technology |
| PS Category | Software |
| Team ID | `<enter SIH portal ID>` |
| Team Name | `<enter registered team name>` |

**Visual**: one clean satellite image with a subtle before/after divider. Keep the slide minimal.

### Slide 2 — Idea title and proposed solution

**Idea title**

`TerreX: Explainable Offline Geospatial Intelligence`

**Proposed solution**

TerreX converts a locally stored satellite archive into an analyst workspace. An analyst can search imagery with natural language or a reference image, narrow the results by area, date, sensor, and image quality, then verify meaningful change through before-and-after evidence.

**What the analyst receives**

- Ranked candidate locations from semantic or image-to-image search.
- Detected construction, road development, land clearance, and water-extent variation.
- A confidence explanation that includes image quality, registration, spectral change, temporal evidence, and source provenance.
- A review action to confirm or reject a result and retain the decision in the audit trail.

**Why it is distinct**

- It treats an image difference as a hypothesis, not an alert. The pipeline checks cloud or haze contamination, alignment quality, radiometric shift, spatial coherence, and temporal persistence.
- It joins discovery and verification. RemoteCLIP retrieves candidate imagery; the change-analysis path tests whether a physical change is supported.
- It preserves an offline deployment path with local imagery, local models, Qdrant, and PostgreSQL/PostGIS or the local SQLite fallback.

**Visual**: use four large flat stages: `Search` → `Verify change` → `Review evidence` → `Export provenance`. Do not add an overloaded architecture diagram here.

### Slide 3 — Technical approach

**Main diagram copy**

```text
Public EO scenes in GeoTIFF / COG
                ↓
Validate metadata and provenance → tile into 256 × 256 chips
                ↓
Quality mask + spectral indices + local embeddings
                ↓
Qdrant vectors  +  PostGIS / SQLite metadata  +  local files
                ↓
Text / image retrieval                    Change analysis
RemoteCLIP + filters                      register → normalize → compare
                ↓                          ↓
             candidate locations → evidence fusion → analyst review and export
```

**Technology line**

`Next.js + React + MapLibre  |  FastAPI + Python  |  Rasterio/GDAL + OpenCV  |  Qdrant  |  PostgreSQL/PostGIS  |  RemoteCLIP  |  Prithvi-EO`

**Technical method to describe verbally**

1. Ingest each GeoTIFF or COG with its acquisition metadata and source provenance.
2. Generate thumbnail, quality data, spectral indices, and a tile embedding locally.
3. Search vectors with metadata filters to identify a candidate area.
4. Align the before and after images. Normalize image brightness only over valid pixels.
5. Combine deep feature difference, NDVI/NDWI/NDBI deltas, connected regions, quality checks, and temporal persistence.
6. Show the analyst a classification, confidence, before/after imagery, source dates, and reasons for any confidence penalty.

**Important scope label**

`Current MVP: optical change analysis, local ingestion, retrieval, review, and provenance. Future enhancement: production-grade SAR processing and optical–SAR fusion.`

### Slide 4 — Feasibility and viability

| Area | MVP approach | Risk | Mitigation / next validation |
| --- | --- | --- | --- |
| Input data | Public Sentinel-2, Sentinel-1, Landsat, and approved Bhuvan data | Uneven coverage and licensing | Store source, licence, acquisition date, CRS, and checksum for every scene. Use only approved public sources. |
| Offline model use | Stage model weights before the event | Missing or incompatible weights can trigger a transparent placeholder mode | Stage and test RemoteCLIP and Prithvi locally. Keep model versions and hashes in a manifest. |
| Optical imagery | Quality mask, registration, normalization, and persistence checks | Cloud, haze, seasons, shadows, misregistration | Benchmark hard negatives and tune thresholds for precision before the demo. |
| Multiple sensors | Store sensor and band metadata with every tile | Optical and SAR signals cannot be compared as if they were the same input | Keep modality-specific pipelines. Add late fusion only after each modality is validated. |
| Scale | Tiled ingestion, deterministic IDs, incremental vector upserts | Long ingestion runs or duplicate scenes | Process new scenes in batches, retain source hashes, and monitor index/storage growth. |

**Closing line**

`The solution is feasible as a local MVP. Its viability depends on reproducible data staging, real-model verification, and measured evaluation rather than unverified performance claims.`

### Slide 5 — Impact and benefits

**Target users**

Geospatial and Earth-observation analysts who must inspect wide areas and repeated satellite passes with limited or no network connectivity.

**Operational benefit**

- An analyst can start with a meaning-based query instead of knowing exact coordinates in advance.
- The review queue prioritizes evidence-supported candidates and exposes uncertainty instead of hiding it.
- Provenance links each result to imagery, acquisition time, sensor, processing steps, and analyst decision.
- The same architecture can support infrastructure monitoring, flood and water-boundary assessment, land-cover clearance assessment, and disaster-response triage when data use is authorized.

**What the team must measure**

| Outcome | Evaluation measure |
| --- | --- |
| Retrieval relevance | Recall@K, mAP, or judged relevance for held-out text and image queries |
| Change detection quality | Precision, recall, F1, IoU, false-positive rate, split by change class |
| False-alarm resistance | Error rate for clouds, haze, shadows, seasonal vegetation, illumination shifts, and registration errors |
| Analyst usability | Time from query to reviewed result, review acceptance rate, and explanation completeness |
| System viability | Indexed scenes/tiles, index-build and incremental-ingestion time, query/change latency, RAM, storage, and hardware |

**Visual**: an analyst workflow picture or a map, a before/after strip, and a small evidence checklist. Do not use made-up impact numbers.

### Slide 6 — Research and references

Keep this slide readable. Use short labels that hyperlink to the full page or add a small QR code pointing to the project repository and its provenance manifest.

1. [ESA Sentinel-2 mission](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-2) — optical multispectral imagery, 13 bands, 10 m bands, and five-day revisit stated by ESA.
2. [ESA Sentinel-1 mission](https://www.esa.int/Applications/Observing_the_Earth/Copernicus/Sentinel-1/Introducing_the_Sentinel-1_mission) — C-band SAR with all-weather, day-and-night acquisition.
3. [USGS Landsat Collection 2](https://www.usgs.gov/landsat-missions/landsat-collection-2) — public archive and product documentation.
4. [NASA-IMPACT Prithvi-EO](https://github.com/NASA-IMPACT/Prithvi-EO-2.0) — geospatial foundation-model code and release details.
5. [RemoteCLIP](https://github.com/ChenDelong1999/RemoteCLIP) — remote-sensing vision-language retrieval model and evaluation resources.
6. [Qdrant filtering documentation](https://qdrant.tech/documentation/search/filtering/) — vector retrieval with payload filtering.
7. [ISRO/NRSC Bhuvan](https://bhuvan.nrsc.gov.in/bhuvan_links.php) — Indian geospatial portal and data-resource entry point.

**Repository references to study**

- `README.md` — complete product and pipeline overview.
- `docs/TerreX_Project_Overview.md` — SIH fit, feature mapping, architecture, and provenance requirements.
- `docs/SATELLITE_DATA_REFERENCE.md` — sensor, data-format, and remote-sensing primer.
- `docs/BUILD_PLAN.md` — delivery priorities and capability audit.
- `docs/TERREX_GRAND_FINALE_MASTER_DEFENSE_GUIDE.md` — extended technical Q&A. Treat numerical claims in this guide as targets to verify, not as presentation facts unless the team reproduces them.

## End-to-end study plan

### 1. Problem framing

Know the difference between a metadata catalogue and semantic discovery. The problem needs an analyst to find places of interest without already knowing every coordinate or acquisition date. It also requires incremental ingestion, quality handling, provenance, and offline operation.

### 2. Earth-observation data and geometry

Study GeoTIFF, Cloud Optimized GeoTIFF, coordinate reference systems, pixel resolution, scene footprints, tile boundaries, and resampling. Understand why the same geographic area can look different across dates because of solar angle, atmosphere, season, cloud, and sensor geometry.

Sentinel-2 provides multispectral optical imagery. Sentinel-1 is C-band radar and can support all-weather observations. Treat the two sources as different physical modalities. An RGB-to-RGB comparison cannot replace a validated SAR pipeline.

### 3. Spectral evidence

Learn these indices and their limitations:

```text
NDVI = (NIR − Red) / (NIR + Red)       vegetation evidence
NDWI = (Green − NIR) / (Green + NIR)   water/moisture evidence
NDBI = (SWIR − NIR) / (SWIR + NIR)     built-up/bare-surface evidence
```

The deltas are evidence, not ground truth. A fall in NDVI can mean construction, clearing, crop harvest, drought, cloud shadow, or registration error. This is why TerreX combines spectral, spatial, quality, and temporal tests.

### 4. Semantic and visual retrieval

RemoteCLIP places text and overhead imagery in a shared representation space. TerreX stores image embeddings in Qdrant and filters them by area, date, sensor, and image quality. Learn cosine similarity, top-K retrieval, metadata filters, and the difference between a candidate ranking and a confirmed change.

### 5. Change-analysis pipeline

Be able to explain the order and the reason for each stage:

1. Select usable before/after observations for the same AOI.
2. Register the images to reduce spatial shift.
3. Mask or discount low-quality pixels.
4. Perform relative radiometric normalization over valid ground pixels.
5. Calculate deep-feature and spectral differences.
6. Remove isolated noise and classify spatially coherent regions.
7. Check a short temporal stack. A signal that does not persist through the next usable observation remains unconfirmed.
8. Present confidence, confounds, evidence, and the earliest supported observation to the analyst.

### 6. Evaluation design

Create a held-out benchmark before demonstrating any score. Include positive cases for each required class, true no-change cases, and hard negatives for seasonal vegetation, cloud, haze, shadow, lighting differences, and deliberate misregistration. Split scenes by geography and time to reduce leakage. Record all thresholds and model versions.

### 7. Offline deployment and provenance

Prepare the entire demo before disconnecting the network: containers, package wheels, frontend assets, model weights, basemaps, sample scenes, database snapshot, and model/data licence records. Each scene and exported result should retain a checksum, source, date, sensor, CRS, preprocessing version, model version, and analyst decision.

### 8. Demo rehearsal

Use a known public demonstration AOI. Rehearse this sequence: type a query, select a candidate, open the before/after view, run or reveal change analysis, read the evidence and confounds, confirm/reject the result, and export provenance. Prepare a short fallback video or screenshots only if SIH rules permit it.

## Future changes to label explicitly as roadmap

These are strong improvements, but they must be marked **Future enhancement** in any presentation or spoken answer until implemented and tested.

| Priority | Future enhancement | Why it improves the system |
| --- | --- | --- |
| Must complete before a credible final demo | Stage real RemoteCLIP and Prithvi weights, declare licences and hashes, and block placeholder results from being mistaken for AI results | Converts a wiring-complete MVP into a model-verified system |
| Must complete before publishing metrics | Benchmark retrieval and change detection on held-out public scenes with hard negatives | Enables defensible precision, recall, F1, IoU, and false-alarm claims |
| High | Modality-specific Sentinel-1 SAR pipeline with speckle handling, radiometric calibration, and temporal backscatter features | Supports all-weather monitoring without pretending radar is optical data |
| High | Late fusion of independently calibrated optical and SAR evidence with modality-specific confidence | Better resilience during cloud cover while retaining traceability |
| High | Production provenance manifest and signed export package | Strengthens reproducibility and audit readiness |
| Medium | Asynchronous ingest queue, job checkpoints, and dashboarded operational metrics | Separates long raster jobs from the interactive analyst experience |
| Medium | Spatial partitioning and hierarchical retrieval for larger areas | Makes national-scale growth more manageable |
| Medium | Active-learning review loop with approval-controlled retraining | Lets analyst feedback improve ranking after an auditable evaluation process |
| Medium | STAC-compatible catalogue and OGC-friendly exports | Improves interoperability with GIS and EO tools |
| Later | Uncertainty calibration and per-region confidence maps | Gives analysts a more reliable understanding of model confidence |

## Questions judges may ask

| Question | Concise, evidence-based answer |
| --- | --- |
| Why do you use two AI models? | RemoteCLIP retrieves semantically related locations from text or an example image. Prithvi-style multispectral features support localized comparison. Retrieval finds candidates; change analysis verifies them. |
| How do you stop a cloud shadow becoming an alert? | We do not trust pixel difference alone. We use quality masks, alignment checks, radiometric normalization, spatial filtering, and persistence across usable observations. The evidence panel shows any remaining confounds. |
| How do you know when a change began? | We report the earliest usable observation that exceeds the threshold and then require confirmation in later usable imagery. The result also contains the interval since the last clear baseline observation. |
| Is SAR already fused with optical imagery? | SAR processing and fusion are planned enhancements unless the team has implemented and validated their modality-specific pipeline. Optical and SAR are not interchangeable. |
| Can the system work without internet? | The architecture is designed for local operation. We will demonstrate the claim only after models, data, assets, and services are staged and the full workflow passes with the network disabled. |
| What proves a result is trustworthy? | Every result links to its source scenes, dates, sensor, preprocessing and model versions, evidence scores, confidence penalties, and analyst decision. |

## 60-second narration

"Satellite archives are large, but analysts often need to know where and when to look before they can use them. TerreX changes that. It lets an analyst search a locally stored archive with a phrase or a reference image, then filters the results by area, time, sensor, and quality. For a selected location, TerreX compares usable satellite observations, aligns and normalizes them, checks spectral and feature evidence, suppresses cloud and registration artefacts, and confirms persistent changes over time. The analyst sees the before/after evidence, confidence, source provenance, and can confirm or reject the result. The key principle is simple: an image difference is not automatically a ground change. TerreX is designed to make every alert explainable, reviewable, and usable offline."
