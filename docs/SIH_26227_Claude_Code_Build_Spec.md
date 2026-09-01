# PROJECT BUILD SPECIFICATION — Semantic Retrieval & Multi-Temporal Change Analysis of Satellite Imagery

**Use this as the master context for the entire project. Read it fully before writing any code. Refer back to it whenever priorities are unclear.**

---

## 0. Project Identity

- **Competition:** Smart India Hackathon (SIH), Problem Statement #26227
- **Organisation:** Ministry of Defence (MoD) / Indian Army (DGIS)
- **Category:** Software | **Theme:** Space Technology
- **Team composition:** 3 members strong in ML/RAG/LangChain/LangGraph (including project lead), remaining members strong in web development. No dedicated hardcore CV/remote-sensing specialist — this must be compensated for by leveraging existing open-source models/repos rather than building from scratch.

---

## 1. Full Original Problem Statement (verbatim — treat every sentence as a requirement, not flavour text)

> **2.1 Background.** Earth-observation archives are expanding rapidly and increasingly contain multi-temporal, multi-spectral and multi-sensor imagery. Conventional catalogues are effective for searching by metadata such as coordinates, acquisition date, platform and product type, but analysts may still need to know where and when to look before they can examine the imagery itself. Recent advances in multimodal and remote-sensing foundation models have improved semantic representation of Earth-observation data, creating the possibility of searching imagery by meaning as well as metadata. Translating those advances into a reliable operational system remains challenging, particularly when the system must work on-premises, ingest new acquisitions incrementally, preserve geospatial provenance, and suppress false change caused by season, atmosphere, viewing geometry, registration error or sensor differences.
>
> **2.2 Detailed Description.** Teams are required to build a system that makes a satellite-imagery archive queryable by semantic content and by change over time, while retaining conventional spatial, temporal and sensor filters. The solution should support analyst discovery rather than require the analyst to identify every location of interest in advance. Six core capabilities are required.
>
> **2.2.1 Semantic and Multimodal Retrieval.** Support free-text search over imagery tiles using natural-language queries, together with image-to-image search for visually and semantically similar locations. Results should be rank ordered and may be refined using area-of-interest, date-range, sensor or other metadata filters. Example queries include "newly built structures near a river" and "large vehicle concentrations on open ground".
>
> **2.2.2 Multi-Temporal Change Analysis.** For a specified area and time window, identify meaningful changes such as appearance, disappearance, expansion or contraction of features; classify supported change types such as construction, clearance, water-extent variation or road development; and estimate the earliest available observation at which the change is supported by usable imagery.
>
> **2.2.3 False-Alarm Suppression and Quality Handling.** Seasonal variation, illumination and view-angle differences, cloud, haze, snow, shadows, radiometric inconsistency and imperfect co-registration must be treated as confounding factors rather than automatically reported as change. The system should use quality masks, normalization, confidence estimates or equivalent mechanisms and should favour analytically useful precision over indiscriminate change recall.
>
> **2.2.4 Discovery and Clustering.** Support unsupervised or embedding-based grouping of similar sites across a wider area so that an analyst who identifies one location of interest can discover other locations with comparable visual or semantic characteristics without manually constructing a new query for each site.
>
> **2.2.5 Analyst Workflow and Provenance.** Provide a ranked review queue with before-and-after evidence, location, acquisition time, sensor or source information, confidence and relevant processing history. Analysts should be able to confirm or reject candidates, preserve those decisions in the audit trail, and use feedback for subsequent reranking or refinement where the chosen approach supports it. Exported results must retain source-scene and processing provenance.
>
> **2.2.6 Scale, Incremental Ingestion and Sovereignty.** Support efficient vector or equivalent indexing, incremental addition of newly acquired imagery without a complete index rebuild, and complete on-premises operation without cloud services or external APIs during evaluation. Georeferencing and acquisition metadata must be preserved, and the solution should ingest organiser-defined common geospatial formats such as GeoTIFF or Cloud Optimized GeoTIFF (COG).
>
> **2.2.7 Constraints.** The complete demonstration must run with network access disabled after all approved models, libraries and datasets have been staged locally. Pretrained public models may be used provided that their origin and licence are declared and the required weights are packaged for offline use. The evaluation will use publicly available or organiser-generated imagery only; no classified, operational or service-generated imagery will be included.
>
> **2.3 Expected Solution.** A working system will be demonstrated over an organiser-defined area of interest and time span using public imagery. Retrieval will be evaluated against held-out semantic queries and relevance judgements, while change analysis will be evaluated against a held-out set of labelled change and no-change cases that participating teams have not seen. Teams must submit source code, an architecture note, the index-build and incremental-ingestion procedure, model and dataset provenance, and a reproducible evaluation report stating the indexed area, number of scenes or tiles, build time, storage footprint, query latency and hardware used.

**Datasets (7.1 Primary Imagery Sources):** Copernicus Sentinel-2 (optical), Copernicus Sentinel-1 (SAR), USGS Landsat Collection 2, and NRSC/ISRO Bhuvan open Earth-observation data products. All data must be publicly accessible under applicable licences; no classified/operational/service-generated imagery.

---

## 2. Deployment Environment — Non-Negotiable Constraints

These constraints shape every architecture decision below and must never be silently violated by any dependency, library default, or code path.

- **Hardware (worst-case assumption, design for this floor):** 4–8 GB RAM, no GPU, basic/low-end CPU, Windows 10 (or older) as OS, ~1 TB HDD (storage is not a constraint; RAM and compute are).
- **Docker is currently allowed and will be used** for this build phase. (Note: architecture should still avoid unnecessary heavy services like Milvus that assume generous RAM — favor lightweight components regardless of Docker availability, since a non-Docker fallback may become necessary later.)
- **Network:** Full internet access is available during a staging/setup phase. At evaluation time, network access is disabled entirely — no cloud APIs, no hosted model endpoints, no external DB connections, no CDN-loaded frontend assets, no telemetry calls. The system must run 100% self-contained after staging.
- **Single machine, worst case.** Assume the entire stack — backend, vector index, models, frontend — must run on one low-spec machine. Do not assume a client-server split across multiple machines is guaranteed to be available.
- **Staging is not time-constrained** — we can pre-download and pre-build everything thoroughly ahead of the demo. The hard constraint is runtime-only network isolation, not setup-time restrictions.

---

## 3. Build Philosophy — Read This Before Writing Code

1. **All six numbered capabilities (2.2.1–2.2.6) must be functionally working end-to-end, individually, before any USP/enhancement work begins.** Do not let "impressive" features (agentic LLM layers, fancy UI polish) get built on top of a retrieval or change-detection pipeline that isn't yet solid. If in doubt about priority, check: "does this improve one of the six numbered capabilities, or is it decoration?" Decoration waits.
2. **Offline-safety is architectural, not a checklist applied at the end.** Every component chosen must have a genuine, verifiable offline mode. Any library call that could reach the internet (model hub downloads, telemetry, CDN assets, PROJ/GDAL grid-shift fetches) must be neutralized via explicit offline environment variables and pre-staged local caches from day one of implementation — not retrofitted later.
3. **Design for the RAM/CPU floor from the first line of code, not as a later optimization pass.** Always include CPU fallback paths (never hardcode `.cuda()` — always check `torch.cuda.is_available()`), prefer small/quantized models, and avoid components (like Milvus) whose baseline resource footprint is risky on a 4GB machine. Build a runtime resource check that can gracefully degrade optional heavy components (e.g., skip loading an LLM layer if available RAM is too low, falling back to rule-based logic).
4. **Do not train foundation models from scratch.** Leverage existing open-source pretrained remote-sensing models and adapt/fine-tune lightly (LoRA or similar) where needed. Reuse existing GitHub repositories and published implementations wherever a well-established one exists, rather than reimplementing from a paper.
5. **Favour precision over recall for change/false-alarm outputs**, per the PS's explicit instruction — conservative thresholds and confidence-gated outputs are preferred over aggressive, noisy flagging.
6. **Everything must be provenance-traceable.** Every retrieval result, change detection, and exported artifact must carry back-references to source scene ID, acquisition date/sensor, and processing steps applied. This is graded explicitly (2.2.5) and required for the submission report.

---

## 4. System Architecture to Build

```
┌─────────────────────────────────────────────────────────────────┐
│                     INGESTION PIPELINE (offline-safe)             │
│  GeoTIFF/COG reader (rasterio/GDAL) → tiling → quality mask       │
│  (cloud/shadow/snow detection) → radiometric normalization →      │
│  embedding generation (CLIP-family RS model) → metadata extraction│
│  (AOI, acquisition date, sensor, provenance chain) →               │
│  incremental upsert into vector index + metadata store            │
└───────────────────────────┬─────────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  VECTOR INDEX (FAISS, IVF-PQ for memory efficiency) +              │
│  METADATA STORE (SQLite, with AOI/date/sensor/provenance columns)  │
└───────┬─────────────────────────────┬─────────────────────────────┘
        ▼                             ▼
┌──────────────────────┐   ┌────────────────────────────────────┐
│ SEMANTIC RETRIEVAL     │   │ MULTI-TEMPORAL CHANGE ANALYSIS       │
│ (Capability 2.2.1)     │   │ (Capabilities 2.2.2 + 2.2.3)         │
│ - text→image search    │   │ - co-registration (feature matching  │
│ - image→image search   │   │   + homography correction)           │
│ - AOI/date/sensor       │   │ - radiometric normalization          │
│   metadata filters      │   │ - quality masking (cloud/shadow/     │
│ - rank ordering         │   │   snow) applied BEFORE diffing       │
│                         │   │ - lightweight Siamese CD model       │
│ DISCOVERY & CLUSTERING  │   │   (MobileNet/ResNet-18 backbone,     │
│ (Capability 2.2.4)      │   │   CPU-only)                          │
│ - k-NN / HDBSCAN over   │   │ - change type classification          │
│   the same embeddings   │   │   (construction/clearance/water-     │
│   from retrieval, seeded│   │   extent/road development)           │
│   from a confirmed site │   │ - confidence estimate, precision-    │
│                         │   │   favoring conservative thresholding  │
│                         │   │ - earliest-observation estimation     │
│                         │   │   (evaluate across full available    │
│                         │   │   time series for the AOI, not just  │
│                         │   │   one before/after pair)              │
└───────────┬────────────┘   └─────────────────┬────────────────────┘
            └────────────────────┬──────────────┘
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  ANALYST REVIEW QUEUE (Capability 2.2.5)                          │
│  Ranked candidates, before/after imagery evidence, location,      │
│  acquisition time, sensor/source, confidence, processing history. │
│  Confirm/reject actions logged to audit trail. Feedback loop for  │
│  subsequent reranking/refinement. Provenance-preserving export.   │
└─────────────────────────────────────────────────────────────────┘
```

**Optional enhancement layer (build only after all six capabilities above are solid):** a LangChain/LangGraph-based agentic layer for (a) parsing free-text queries into structured filters + semantic embedding query, (b) generating natural-language change-explanation captions from structured change-detection output, (c) feedback-driven reranking logic. This layer must be lazy-loaded and gracefully skippable — the core system must remain fully functional with a simple rule-based query parser if this layer is disabled or the machine's RAM is too constrained to load an LLM.

---

## 5. Component-by-Component Build Instructions

### 5.1 Ingestion & Geospatial I/O
- Use `rasterio` + GDAL for reading GeoTIFF and Cloud-Optimized GeoTIFF (COG) inputs, taking advantage of COG's partial/range-read capability rather than loading full scenes into memory.
- Use `rio-cogeo` to validate/convert inputs to COG where needed.
- Tile large scenes into manageable patches (e.g., 256×256 or 512×512) for embedding and change-detection processing — do not process full scenes at native resolution on this hardware budget.
- Preserve full georeferencing and acquisition metadata (CRS, timestamp, sensor/platform, source scene ID) alongside every tile — this metadata is required for provenance (2.2.5) and for filters (2.2.1).
- Pre-fetch and bundle `PROJ_DATA` grid-shift files during staging; set `PROJ_NETWORK=OFF` at runtime so no coordinate-transform operation ever attempts a network fetch.

### 5.2 Embedding Model (semantic retrieval backbone)
- Use an existing open-source remote-sensing CLIP-family model — **RemoteCLIP** or **GeoRSCLIP** (search GitHub/HuggingFace for the official released checkpoints) as the base. Do not train from scratch.
- Prefer the smaller variant (ViT-B/32-scale, not ViT-L/14) for CPU feasibility.
- Convert to ONNX with INT8 quantization for faster CPU inference where feasible; verify accuracy impact is acceptable.
- If time and data allow, lightly fine-tune (LoRA or full fine-tune of a small head) on an available RS image-text dataset (e.g., a public captioned corpus such as those from the RSICD/RSITMD/VRSBench family, or a co-registered Sentinel-1/Sentinel-2 captioned dataset if available) to improve domain relevance — this is optional polish, not blocking for MVP.
- Download and bake the model weights into the local environment during staging; set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` so no runtime hub calls are attempted.

### 5.3 Vector Index & Metadata Store
- Use **FAISS** (not Milvus — too heavy for the RAM budget and adds unnecessary service/Docker complexity). Use an IVF-PQ index type for memory-efficient storage rather than a flat index, sized appropriately for the demo-scale archive.
- Support incremental upsert (add new embeddings without full index rebuild) — verify this works correctly, since it's an explicit graded requirement (2.2.6).
- Use **SQLite** for metadata (tile ID, source scene ID, AOI/geometry, acquisition date, sensor, processing history, provenance chain, confirm/reject audit log). This keeps the whole metadata layer to a single file with no service overhead.

### 5.4 Semantic & Image-to-Image Retrieval (2.2.1)
- Text query → embed via the same CLIP-family text encoder → FAISS similarity search → rank-ordered results.
- Image query (image-to-image) → embed via the same visual encoder → FAISS similarity search.
- Support post-retrieval filtering/refinement by AOI (bounding box/polygon intersection against stored geometry), date range, and sensor type — implement as metadata filters applied either as a pre-filter (restrict FAISS search space) or a post-filter (filter ranked results), whichever is more efficient at demo scale.
- **Handle compound queries properly**, e.g. "newly built structures near a river" — this contains both a semantic component (visual concept) and a geometric/spatial-relation component (proximity to a hydrological feature). Do not rely purely on embedding similarity for the spatial-relation part; consider incorporating an auxiliary spatial reference layer (e.g., a cached river/road vector layer, sourced once during staging from OSM or Bhuvan) to compute actual geometric proximity as an additional filter/rerank signal.

### 5.5 Discovery & Clustering (2.2.4)
- Reuse the same embedding space from 5.4. Given a seed site (a confirmed location of interest), retrieve nearby-in-embedding-space tiles across the wider indexed AOI using k-NN or a density-based method (e.g., HDBSCAN) — this should require no new model, only a different query pattern over the existing FAISS index.

### 5.6 Multi-Temporal Change Analysis (2.2.2)
- **Registration:** align bi-temporal (or multi-temporal) image pairs using feature matching (e.g., OpenCV ORB/SIFT + homography or affine transform) before any diffing — do not assume input pairs are already perfectly co-registered.
- **Radiometric normalization:** apply histogram matching or relative radiometric normalization between dates before comparison, to reduce illumination/atmospheric-driven pseudo-change.
- **Change detection model:** use a lightweight Siamese architecture (small CNN backbone such as MobileNet or ResNet-18, not a heavy Transformer) suitable for CPU inference. Prefer adapting an existing open-source change-detection repository/checkpoint over training fully from scratch; fine-tune lightly on available public change-detection datasets if time allows.
- **Change type classification:** classify detected change regions into supported categories — construction, clearance, water-extent variation, road development (or an equivalent/extendable label set).
- **Earliest-observation estimation:** for a flagged change, do not rely solely on a single before/after pair — evaluate across the full available time series of usable observations for that location/AOI (where the local archive has multiple timestamps) to estimate the earliest observation date at which the change is actually supported by usable (quality-passing) imagery. A simple viable approach: track an embedding/feature-difference signal over time per location and identify where it crosses a change threshold; a more advanced approach (optional, time-permitting) is a proper change-point detection method (e.g., CUSUM).

### 5.7 False-Alarm Suppression & Quality Handling (2.2.3)
This must be built into the change-detection pipeline (5.6), not bolted on afterward.
- **Quality masking:** detect and mask out cloud, haze, snow, and shadow-affected regions before comparison (e.g., using Sentinel-2's SCL band where available, or a lightweight cloud/shadow classifier such as s2cloudless). Masked regions should not be flagged as change regardless of raw pixel difference.
- **Confidence estimation:** every change output must carry a calibrated confidence score, not a binary flag — use this to implement the PS's explicit precision-over-recall preference (conservative thresholding, favoring fewer false positives over catching every possible true positive).
- **Registration-error tolerance:** the registration step in 5.6 is part of this requirement — imperfect co-registration must not be reported as false change.
- **(Enhancement, build after MVP works):** cross-sensor corroboration — when both optical and SAR imagery are available for a similar timeframe, check whether a flagged optical change is corroborated by SAR (which is largely independent of lighting/season/cloud); use agreement between modalities to raise confidence, and disagreement to lower it. This directly strengthens the false-alarm suppression requirement and produces a measurable improvement worth reporting.

### 5.8 Optical–SAR Consideration
The dataset list includes both Sentinel-1 (SAR) and Sentinel-2 (optical). While the PS's six capabilities do not mandate a separate "cross-modal fusion" feature the way the ISRO SatQuery PS does, SAR imagery should be usable within retrieval (embed and index SAR tiles alongside optical, e.g., via a dual-encoder approach if using a SAR-aware embedding model such as CLOSP-style architectures) and as a corroboration signal in change analysis (5.7). Do not build a separate heavy fusion subsystem — integrate SAR support into the existing retrieval and change pipelines.

### 5.9 Analyst Workflow, Provenance & Review Queue (2.2.5)
- Backend: expose a ranked candidate list (from either retrieval or change-analysis results) with all required fields — before/after image evidence, location (AOI/coordinates), acquisition time(s), sensor/source, confidence, and processing history (registration applied, normalization applied, quality-mask state, model/version used).
- Support confirm/reject actions per candidate, persisted to an audit trail (append-only log in SQLite: who/what action, timestamp, candidate ID, resulting state).
- Support using confirmed/rejected feedback to influence subsequent reranking or refinement — at minimum, deprioritize or reweight results similar (in embedding space or terrain/context type) to repeatedly-rejected candidates; a more advanced version calibrates confidence thresholds per context/terrain type based on accumulated feedback.
- Export functionality must retain full source-scene and processing provenance in the exported artifact (e.g., a structured report/CSV/JSON bundling all the above fields per exported result).

### 5.10 Offline Enforcement (2.2.6 / 2.2.7)
- Use Docker Compose to containerize the full stack (backend, vector index, any local LLM service, frontend) for this build phase.
- All model weights, embedding models, quantized LLM files, PROJ/GDAL grid data, and frontend assets (fonts, map tiles, JS/CSS bundles) must be staged/baked into the build — no runtime fetch of any of these.
- Set explicit offline environment variables everywhere applicable: `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `PROJ_NETWORK=OFF`, disable any LangChain/LangSmith tracing (`LANGCHAIN_TRACING_V2=false`, no API key set).
- No CDN references anywhere in the frontend (fonts, icon libraries, map tile servers) — self-host all static assets; pre-download basemap tiles for the demo AOI rather than pointing Leaflet/map library at an online tile server.
- Verification: test the full pipeline with networking physically/logically disabled (Docker `--network internal`, or OS-level firewall blocking, or literal disconnection) before considering any milestone complete — not just once at the end, but repeatedly as new dependencies are added.
- Maintain a running model/dataset provenance manifest (name, source repo/URL, licence, version, date obtained) from the start of implementation — required for submission (2.3) and for the licence-declaration requirement (2.2.7).

### 5.11 Optional Agentic/LLM Enhancement Layer (build ONLY after 5.1–5.10 are solid and tested offline)
- Use LangChain/LangGraph to build: (a) a query-parsing node that converts free-text queries into structured filters + semantic embedding query (with a non-LLM rule-based fallback if the LLM layer is disabled/unavailable), (b) a change-caption generation node that converts structured change-detection output (type, location, confidence, dates) into a readable analyst note, (c) optionally, a feedback-driven query refinement loop.
- Serve the LLM locally via **Ollama** or **llama.cpp**, using a small quantized model (1–1.5B parameter class, Q4 GGUF) appropriate for the RAM budget — do not default to a 7B+ model given the 4–8GB RAM ceiling.
- This layer must be lazy-loaded (only load the LLM into memory when actually invoked) and must be skippable via a runtime RAM check — if available memory is below a safe threshold, the system should automatically fall back to rule-based query parsing and template-based change captions rather than attempting to load the LLM and risking a crash or unusable slowdown.
- Use constrained/structured output generation (e.g., a JSON-schema-constrained decoding approach) for the query-parsing node to avoid malformed output from a small quantized model.

---

## 6. USP / Differentiator Features (build only after Section 5's core capabilities are fully working and offline-verified)

In priority order:

1. **Hybrid semantic + geometric retrieval** — handle compound queries like the PS's own example ("newly built structures near a river") by combining embedding-based semantic search with an actual geometric proximity computation against a cached vector layer (rivers/roads), not embedding similarity alone.
2. **Change-point detection over the full temporal stack** — for the "earliest available observation" requirement, use a proper time-series change-point method across all available observations for an AOI rather than a single before/after pair comparison.
3. **Cross-sensor corroboration** — use optical+SAR agreement/disagreement to raise/lower change confidence, directly strengthening the measurable false-alarm suppression performance.
4. **Standing watchlist / proactive monitoring** — allow an analyst to save a semantic query as a persistent watchlist; automatically re-evaluate it against newly ingested imagery and surface new matches into the review queue, without the analyst re-querying manually.
5. **Adversarial false-alarm stress-test harness** — build a small synthetic evaluation set that deliberately injects confounders (simulated cloud, illumination shift, seasonal color grading, small misregistration) onto known no-change pairs, and report the false-positive rate under each stressor as part of the evaluation report — this converts a vague "we suppress false alarms" claim into a quantified, defensible result.
6. **(Stretch) Feedback-driven online calibration** — let repeated analyst confirm/reject patterns adjust confidence thresholds per terrain/context type over time, not just rerank a single query's results.

---

## 7. Required Deliverables (per PS section 2.3 — plan for these from the start, not as an afterthought)

- Full source code.
- An architecture note (can be derived from Section 4 of this document, expanded with actual implementation details as built).
- The index-build and incremental-ingestion procedure, documented and reproducible.
- Model and dataset provenance declarations (maintain the manifest described in 5.10 throughout).
- A reproducible evaluation report stating: indexed area, number of scenes/tiles indexed, index build time, storage footprint, query latency (retrieval and change analysis separately), and hardware used for testing (explicitly state the low-end 4–8GB RAM/no-GPU target this was validated against).

---

## 8. Explicit Non-Goals (do not spend time on these)

- Do not train any foundation/embedding model from scratch — adapt existing open-source checkpoints.
- Do not build a distributed/multi-node vector database cluster — a well-implemented single-node FAISS index is sufficient and appropriate for the target hardware and hackathon scope.
- Do not build heavy agentic orchestration before the six core capabilities work — the LLM/LangGraph layer is an enhancement, not the foundation.
- Do not assume GPU availability anywhere in the codebase — always provide and default-test the CPU path.
- Do not rely on any hosted API (OpenAI, Anthropic, any cloud vector DB, any cloud storage) anywhere in the runtime path, even as a fallback.

---

## 9. Suggested Build Order

1. Environment & offline-safety scaffolding (Docker Compose skeleton, offline env vars, provenance manifest template) — get this right before building features on top of it.
2. Ingestion pipeline (5.1) + embedding model integration (5.2) + FAISS/SQLite index (5.3), tested for incremental upsert.
3. Semantic + image-to-image retrieval with filters (5.4), including the compound-query geometric handling.
4. Discovery/clustering (5.5) — should be fast to add given 2–3 are done.
5. Change detection pipeline including registration, normalization, quality masking, and confidence-based thresholding (5.6 + 5.7) — build false-alarm suppression in from the start, not after a naive diff "works."
6. Analyst review queue, audit trail, feedback loop, provenance-preserving export (5.9).
7. Full offline verification pass (5.10) — test with networking disabled, on constrained RAM (simulate via container memory limits), on Windows if possible.
8. Only then: optional LLM/LangGraph enhancement layer (5.11), built with lazy-loading and graceful degradation from the start.
9. Only then: USP features from Section 6, in the stated priority order, as time allows.
10. Assemble deliverables (Section 7) continuously alongside development, not at the end.

---

**When implementing, always check proposed dependencies/models against the RAM/no-GPU/offline constraints in Section 2 before adopting them. When in doubt about scope or priority, default to: make the six numbered PS capabilities (Section 1, 2.2.1–2.2.6) work correctly and verifiably offline before adding anything not explicitly required.**
