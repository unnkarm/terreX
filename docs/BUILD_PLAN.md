# TerreX — Build Plan & Architecture Decision Record

SIH PS #26227 — Semantic Retrieval & Multi-Temporal Change Analysis of Satellite Imagery
Ministry of Defence (MoD) / Indian Army (DGIS) · Space Technology

Status: **foundation-repair block implemented and verified (17/17 tests passing)**
Date: 2026-09-01

---

## 1. What the scaffold already gives us

The existing codebase (7 commits, ~1,940 lines Python, ~2,400 lines TypeScript) is a
better starting point than it first appears. Three things about it are worth
protecting as we change everything else:

**The honesty contract.** `embeddings.py` and `prithvi.py` both implement a real
model path and an explicitly-labelled placeholder path, and every result carries
`is_placeholder=True` up through the API into the UI. This is the right instinct and
it is exactly what a judge will probe. Keep it, and extend the same discipline to
every new model we introduce.

**The provenance spine.** `scenes` → `tiles` → `change_results` → `feedback`, with
`processing_version` stamped on scenes and tiles, footprint geometry on both, and a
`quarantined` status that records failed ingests rather than dropping them. Capability
2.2.5 is graded on precisely this and the tables are already shaped for it.

**Suppression with stated reasons.** `false_alarm.py` returns a `reasons` list
explaining every discount it applied. Rule-based and inspectable beats a black box for
an analyst-facing system, and it means the false-alarm story can be *narrated* in the
demo rather than asserted.

## 2. Capability audit against the problem statement

| PS capability | State | What is actually missing |
|---|---|---|
| 2.2.1 Semantic + multimodal retrieval | **Mostly built** | Compound-query geometry ("near a river"); AOI filter is a centroid bbox, not polygon intersection; no real weights staged |
| 2.2.2 Multi-temporal change analysis | **Partial** | Change *type* classification entirely absent (0 references to construction/clearance/water/road in the backend); "earliest supported observation" returns the earliest tile that exists, not the earliest at which change is supported; no co-registration *correction*, only measurement; no radiometric normalization before differencing; change is a scalar tile mean, with no per-region areas |
| 2.2.3 False-alarm suppression | **Partial** | Quality masks are scored but never applied *before* differencing, so a cloud edge still contributes to the raw signal; no SCL / s2cloudless; confidence is a fixed linear blend, uncalibrated |
| 2.2.4 Discovery & clustering | **Absent** | No clustering service, no endpoint, no UI. Zero references to cluster/kmeans/hdbscan |
| 2.2.5 Analyst workflow & provenance | **Stub** | Feedback rows are written but never read back into ranking; no ranked review queue endpoint; no export; no before/after evidence assembly |
| 2.2.6 Scale, incremental ingestion, sovereignty | **Partial** | Incremental upsert works. But: Google Fonts pulled from a CDN at runtime; no `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` / `PROJ_NETWORK`; no offline verification test; no provenance manifest; no evaluation harness |

### Two correctness defects that block everything downstream

**Ingestion loads whole scenes into RAM.** `ingest_file()` calls
`_read_rgb_float(dataset)` with no window, and then `valid_pixel_fraction(dataset.read())`
which reads *every band at full resolution*. On the synthetic demo scenes this is
invisible. On a real Sentinel-2 L2A granule (10980 × 10980) the first call needs
~1.4 GB and the second ~6 GB. The scaffold therefore cannot ingest the very data the
problem statement names, on the hardware we are targeting. This is the single most
important fix, and it also happens to be where COG's range-read capability earns its
place in the architecture note.

**Change detection ignores its own date range.** `find_candidate_tiles(lon, lat,
date_from, date_to)` accepts both dates and filters on neither — the `select()` only
constrains `lon`/`lat`. Every windowed change query therefore compares the oldest and
newest tiles at that location in the entire archive, regardless of the window the
analyst asked for. It also matches by coordinate tolerance without confirming the two
tiles cover the same footprint. Any change-analysis evaluation run against the current
code would be measuring the wrong thing.

## 3. Decisions taken

### D1 — Keep Qdrant + Postgres/PostGIS *(chosen; overrides the spec's FAISS+SQLite)*

Accepted, with a rider. The upside is real: Qdrant gives native incremental upsert and
payload filtering, which is precisely what 2.2.6 grades, and PostGIS gives true polygon
intersection for AOI filters instead of hand-rolled shapely predicates.

The rider is that we now have to *prove* the 4 GB floor rather than argue about it:

- Qdrant collection configured with `on_disk: true` vectors, `on_disk_payload: true`,
  and **int8 scalar quantization**. This is the spec's IVF-PQ intent — memory-efficient
  approximate search — satisfied inside Qdrant, and it is defensible in the
  architecture note as such.
- Postgres tuned down (`shared_buffers=128MB`, `work_mem=4MB`).
- Explicit `mem_limit` on every compose service, so the budget is enforced by the
  runtime and measurable with `docker stats` for the evaluation report.

Worth naming the real memory hog while we are here: it is not Qdrant or Postgres, it is
**torch**. RemoteCLIP ViT-B/32 in fp32 plus the torch runtime lands the backend around
1.2–1.8 GB resident. Postgres and Qdrant together are ~400 MB. Which means the spec's
"convert to ONNX with INT8 quantization" (§5.2) is not optional polish — it is the item
that makes a 4 GB machine viable, dropping the embedding stack to roughly 90 MB of
weights plus ~200 MB of onnxruntime. It also lets us export the text and image towers
separately and lazy-load only the text tower on the query path.

### D2 — Pretrained Siamese change-detection checkpoint *(chosen)*

Accepted, with a rider, and Prithvi-EO comes off the critical path. Two honest notes:

**The current Prithvi integration cannot work as written.**
`PrithviViT.from_pretrained_local(weights_path, config_path)` is not a terratorch API —
it is an aspirational placeholder. Dropping it costs us nothing real and removes a heavy,
Windows-hostile dependency chain.

**A Siamese checkpoint gives binary change, not change *types*.** Capability 2.2.2
explicitly requires classifying construction, clearance, water-extent variation and road
development, and no public pretrained model emits those four classes. So the engine is
two layers, not one:

- *Layer 1 — where changed.* Siamese CD network producing a pixel-level change mask.
- *Layer 2 — what changed.* Spectral-index reasoning over the same tile pair
  (ΔNDVI, ΔNDWI, ΔNDBI) plus region shape, mapping each connected change region to one
  of the four required classes with a stated rationale. Vegetation down + built-up up
  reads as construction; vegetation down alone as clearance; NDWI shift as water extent;
  an elongated region with high eccentricity as road development.

Layer 2 is why **task #2 (multispectral ingestion) is a hard prerequisite** for change
typing — you cannot compute NDVI from the first three bands of a GeoTIFF. It degrades to
RGB-only heuristics when NIR/SWIR are unavailable, and says so in the output.

**Model selection, and a domain-gap warning.** The obvious checkpoints (BIT-CD, SNUNet-CD)
are trained on **LEVIR-CD: 0.5 m aerial building change**. Our named data sources are
Sentinel-2 at 10 m and Landsat at 30 m. That is a 20–60× resolution gap, and a
LEVIR-pretrained model applied to Sentinel-2 tiles will perform poorly in a way that is
easy for a judge to expose. Proposed handling:

1. Primary: an **OSCD-domain** siamese model (Onera Satellite Change Detection *is*
   Sentinel-2 at 10 m — the correct domain; FC-Siam-diff / FC-Siam-conc are the
   canonical small architectures, a few hundred thousand parameters, trivially CPU-fast).
2. Secondary: **BIT-CD** with LEVIR weights, offered for any high-resolution source, with
   the resolution assumption declared in the provenance manifest.
3. Retained baseline: the **classical change-vector analysis** path stays in the codebase
   permanently — not as a fallback but as the comparator. If the learned model cannot beat
   CVA on the held-out set, the evaluation report should say so, and we should ship CVA.
   Reporting both is a stronger result than reporting one.

### D3 — Foundation repair first *(chosen)*

Agreed, and it is the right call: closing capability gaps on top of an ingestion path
that OOMs on real data and a change query that ignores its date range would mean
building twice.

### D4 — Nothing staged locally *(stated)*

So all work in this block is written and verified against `scripts/generate_sample_data.py`.
Weight staging becomes its own task with its own acceptance test, and the placeholder
paths stay honest and load-bearing until then.

## 4. A design constraint worth making explicit

My own sandbox has `numpy`, `PIL` and `OpenCV` available, but package installation is
blocked at the proxy — I cannot run `fastapi`, `rasterio`, `sqlalchemy` or `qdrant_client`
here at all. Rather than treat that as a limitation to apologise for, it should shape the
architecture in a way we want anyway:

**All algorithmic logic goes in modules that take numpy arrays and return numpy arrays,
with no rasterio, SQLAlchemy or Qdrant imports.** Quality metrics, registration,
radiometric normalization, the change map, false-alarm suppression, change typing. Thin
adapters handle I/O and persistence.

The payoff is not theoretical. It means the science is unit-testable in isolation, it
means I can genuinely execute and verify that layer before handing it over rather than
asserting it works, and it means the change-detection head stays swappable exactly as the
existing `_difference_to_change_map` docstring intends. OpenCV also covers ORB/SIFT,
homography estimation, Otsu thresholding and morphology — everything §5.6 asks for —
under one light dependency we would want regardless.

The service-stack layer still needs verification on your machine. Section 6 is the runbook
for that.

## 5. Foundation-repair work breakdown

Ordered. Each item states what "done" means as a command whose output we compare, not as
a claim.

**#2 Windowed multispectral ingestion**
Replace full-scene reads with per-tile `rasterio.windows.Window` reads. Add a band-map
config (`{blue, green, red, nir, swir1, swir2, scl}` per sensor profile) so NIR/SWIR are
ingested and NDVI/NDWI/NDBI become computable. Derive per-tile geo bounds from
`dataset.transform` instead of interpolating the WGS84 bbox. Stream tile-by-tile so peak
RSS is a function of tile size, not scene size.
*Done when:* ingesting a synthetic 8000×8000 6-band scene keeps peak backend RSS under
600 MB, measured, and tile centroid coordinates agree with `rasterio`'s own `xy()` to
within a pixel.

**#3 Change-detection candidate selection**
Filter candidates by `date_from`/`date_to`. Confirm footprint overlap rather than trusting
a coordinate tolerance. Gate on usable-observation quality before a pair is selected at all.
*Done when:* a change query over a window that contains exactly two of five available
observations selects those two, proven by a test asserting the returned tile IDs.

**#4 Offline violations**
Self-host the two webfonts and drop the `fonts.googleapis.com` import from `globals.css`.
Set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `PROJ_NETWORK=OFF` and a bundled
`PROJ_DATA` in the backend image and compose env. Add a startup assertion that refuses to
boot if `OFFLINE_MODE=true` while any guard is unset — offline-safety should fail loudly,
not silently.
*Done when:* `grep -r "https\?://" frontend --exclude-dir=node_modules` returns only
localhost and SVG-namespace URLs, and the stack serves a full search+change round trip
with the compose network set to `internal`.

**#5 RAM budget made real**
Qdrant on-disk + int8 quantization, Postgres tuned, `mem_limit` on all four services.
*Done when:* `docker stats` during an ingest-then-query cycle shows total resident under
2.5 GB with placeholder models, and the numbers are recorded in the evaluation report
template rather than estimated.

**#6 Algorithm core + tests**
Extract the pure-array modules described in §4, add `pytest` over synthetic fixtures
covering: cloud-masked regions never counted as change, a deliberately misregistered
no-change pair scoring below threshold, a histogram-shifted no-change pair scoring below
threshold, and a genuine construction pair scoring above it.
*Done when:* the suite runs green in my sandbox and I can paste the output.

**#7 Verification pass**
The runbook in §6, executed, with real output compared against the criteria above.

## 6. Verification loop

Because I cannot run the service stack, the honest arrangement is: I write and test the
array-level code here, then give you a short numbered command list and you paste the
output back. No milestone is marked done on my assertion alone. Commands will cover
`docker compose build`, `generate_sample_data`, an incremental ingest, the four API round
trips, `docker stats`, and an air-gapped rerun.

## 7. Roadmap after this block

In the spec's own priority order, and not before the foundation is verified:

1. **Capability 2.2.4 — discovery & clustering.** Cheapest large gap to close: k-NN plus
   HDBSCAN over embeddings that already exist, seeded from a confirmed site. No new model.
2. **Capability 2.2.2 — change typing** and honest earliest-supported-observation
   (change-point detection across the full temporal stack, not the earliest tile that exists).
3. **Capability 2.2.3 — masks applied before differencing**, registration *correction* via
   homography, radiometric normalization via histogram matching.
4. **Capability 2.2.5 — review queue, export with provenance, feedback-driven reranking.**
   Feedback rows are already being written; nothing reads them yet.
5. **Model staging** — RemoteCLIP ONNX INT8, OSCD siamese checkpoint, provenance manifest.
6. **Deliverables** (§7 of the spec) — architecture note, ingestion procedure, evaluation
   report. Assembled continuously.
7. **USPs** (§6 of the spec) — hybrid semantic+geometric retrieval, cross-sensor
   corroboration, watchlist, adversarial false-alarm harness.

The adversarial false-alarm harness deserves an early slot despite its low nominal
priority: it is the difference between claiming false-alarm suppression and quantifying it,
and 2.2.3 is graded on precision.
