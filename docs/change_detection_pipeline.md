# Multi-Evidence Change Detection Pipeline

**Module:** `backend/services/algorithms/` + `backend/services/change_detection.py`
**Pipeline version:** `multi-evidence-1.0`
**Status:** replaces the single embedding-difference change score.

---

## 1. Why this replaced the old detector

The previous detector reduced "did anything change here?" to one number: the L2 distance
between Prithvi-EO patch embeddings, min–max normalised across the tile. That has three
structural problems, none of which can be tuned away.

| Problem | Consequence |
|---|---|
| **One signal, no cross-checks.** A deep feature distance rises for genuine ground change, for illumination drift, for sensor gain differences, and for sub-pixel misalignment — and cannot distinguish them. | Every false alarm looked exactly like a real detection. |
| **Min–max normalisation has no zero.** Rescaling a difference map to `[0, 1]` guarantees a `1.0` pixel exists, even on two identical images. | An unchanged AOI still produced a confident-looking change map. |
| **No per-pixel quality gate.** Cloud, shadow and nodata pixels entered the difference on equal terms with clear ground. | Cloud edges produced ring-shaped "change". |

The replacement computes **three independently derived pieces of evidence** for every pixel and
requires them to corroborate each other. A lone embedding spike is no longer sufficient to raise
a detection; deep + spectral + spatial agreement is decisive.

---

## 2. Pipeline stages

```
Before image + After image
  → Registration                    (registration.py)
  → Cloud / quality masking         (masking.py)
  → Radiometric normalization       (normalization.py)
  → Prithvi EO features             (services/prithvi.py, injected)
  → Deep feature difference    ─┐
  → Spectral differences        ├─ (evidence.py)
  → Spatial/context consistency ┘
  → Evidence fusion                 (fusion.py)
  → False-alarm suppression         (suppression.py)
  → Change mask
  → Change type                     (change_classifier.py)
  → Confidence                      (services/false_alarm.py)
```

Orchestrated by `pipeline.analyze_change_pair()`, which returns a `ChangeAnalysis` carrying the
change map, mask, regions, every evidence layer, and an ordered `PipelineStage` audit trail.

> **Masking runs before normalization**, not after. The radiometric fit must not be computed over
> cloud pixels, or a cloudy date drags the whole tile's gain with it.

### Design boundary

`services/algorithms/` is array-in / array-out with **no database, rasterio or model-loading
dependency**. The EO feature extractor is *injected* by the caller:

```python
analyze_change_pair(before, after, feature_extractor=callable)
# callable: (raster_hwc, band_map) -> (feature_grid, model_name, is_placeholder)
```

This keeps the science unit-testable against plain NumPy fixtures, and lets the deep layer degrade
to a spectral + spatial detection when no extractor is available. `change_detection.py` owns the
database, file and API concerns only.

---

## 3. Stage detail

### 3.1 Registration — `registration.py`

ORB features + RANSAC partial-affine, falling back to sub-pixel FFT phase correlation for
low-texture scenes, heavy cloud, or dissimilar seasons.

Additions over the previous version:

- **`residual_dx` / `residual_dy`** — misalignment measured *after* warping, via phase correlation
  on the warped output. The translation a warp **applied** says nothing about how well the result
  lines up; that is what was corrected. Downstream suppression keys off the residual.
- **`footprint`** — boolean mask of destination pixels backed by real source data. `BORDER_REFLECT_101`
  invents plausible-looking edge pixels; comparing against them manufactures change.
- **`method`** — `"orb-affine"` | `"fft-phase-correlation"` | `"none"`, so the UI can say how
  alignment was achieved.
- **Contrast stretch before 8-bit conversion.** ORB and phase correlation need `uint8`; a naive cast
  collapses dark, low-contrast tiles (forest, water) to a handful of grey levels.
- **Correlation measured on float luminance**, never on the quantised view.

### 3.2 Cloud / quality masking — `masking.py`

Produces a per-pixel `QualityMask` with a named breakdown of *why* each pixel was rejected.

| Path | Used when | Logic |
|---|---|---|
| **SCL** (preferred) | A Sentinel-2 L2A scene-classification plane is available | cloud = `{8, 9, 10}`, shadow = `{2, 3}`, nodata = `{0}`, saturated = `{1}`, snow = `{11}` |
| **Heuristic** | Otherwise | Cloud: brightness > 0.72 AND saturation < 0.18 (AND NDVI < 0.25 when NIR present). Shadow: scene-relative darkness. |

Cloud and shadow are **dilated** (default 2 px) — both bleed into their neighbourhood
(semi-transparent cloud edge, penumbra), and those halo pixels are the classic source of
ring-shaped false change.

The SCL plane is read from the tile `.npz` **before** any `[0, 1]` rescaling, since it carries class
codes, not reflectance. When the after image is warped, its SCL and ingest masks are warped with it
(nearest-neighbour) so they keep masking the right pixels.

`joint_valid_mask()` intersects both dates and the registration footprint. Only those pixels are
comparable at all.

### 3.3 Radiometric normalization — `normalization.py`

`normalize_relative_radiometry()` fits a **per-band gain/offset on pseudo-invariant features (PIF)**:
the quietest 70 % of clear pixels, by absolute difference.

```
gain   = clip(MAD_ref / MAD_src, 0.5, 2.0)
offset = median_ref − gain · median_src
out    = clip(gain · src + offset, 0, 1)
```

Fitting over *all* pixels lets genuine change pull the transfer and partially normalise itself away.
Restricting the fit to the invariant population corrects illumination, atmosphere and sensor gain
while leaving real ground change intact. Degenerate-spread bands fall back to an offset-only
correction; mismatched grids fall back to identity. Cumulative histogram matching
(`normalize_histogram_match`) is retained for cases that differ in more than gain and offset.

> A large real change can make the *scene-mean* difference wider after normalization, not narrower.
> That is correct behaviour, so the evidence panel reports the fitted gain/offset rather than the
> scene-mean shift.

### 3.4 Evidence layers — `evidence.py`

Each layer returns an `EvidenceLayer`: a calibrated probability map, a **prior weight**, a
**reliability** for *this specific pair*, an analyst-readable justification, and its statistics.

| Layer | Measures | Prior weight | Reliability |
|---|---|---|---|
| `deep_feature` | Cosine distance (0.75) + relative activation-magnitude change (0.25) between Prithvi patch tokens | 0.45 | 1.0, or **0.5** on placeholder features |
| `spectral` | Change Vector Analysis over shared bands (0.45) + max NDVI/NDWI/NDBI shift (0.55) | 0.35 | 1.0, or **0.55** on RGB-only proxies |
| `spatial_context` | SSIM-style local structural dissimilarity (0.65) + local texture-energy change (0.35) | 0.20 | 0.9 |

**Why these three.** Cosine distance is gain-invariant and captures *semantics*. CVA and index
deltas are physical and say *what kind* of change. The structural term is invariant to brightness
and contrast by construction — it cannot be tripped by a global gain or offset — which makes it the
natural adjudicator when the other two disagree.

#### Calibration — `robust_probability()`

Two independent judgements are combined:

```
p = p_absolute · (0.5 + 0.5 · p_relative)

p_absolute = clip((d − floor) / span, 0, 1)
p_relative = sigmoid((z − 2.0) / 0.8),   z = (d − median) / (1.4826 · MAD)
span       = clip(P98(d) − median, scale_min, scale_max)
```

- The absolute `floor` is what keeps an unchanged pair at **zero** — the property min–max
  normalisation cannot deliver.
- Absolute magnitude sets the ceiling, so a *uniformly* changed tile (a whole-AOI flood) still
  scores, which a purely scene-relative z-score would miss entirely.
- The `span` adapts to the spread observed in the scene, clamped to `[scale_min, scale_max]`. The
  same cosine distance means different things in a 768-dimension Prithvi embedding and in a
  7-dimension statistical stand-in; one hard-coded span would be right for one and wrong for the
  other. The clamp stops it collapsing onto sensor noise or widening past a real signal.
- MAD is used rather than standard deviation because a genuine change region is, by construction, an
  outlier population that would inflate a plain σ and hide itself.

### 3.5 Evidence fusion — `fusion.py`

```
w_i        = prior_weight_i · reliability_i
weighted   = Σ(w_i · p_i) / Σw_i
agreement  = Σ(w_i · [p_i > threshold]) / Σw_i
p_fused    = weighted · (0.60 + 0.40 · agreement)
```

`CORROBORATION_FLOOR = 0.60`: a pixel supported by every layer keeps its full score; one supported
by a single layer is damped to 60 %. Worked examples at the 0.5 threshold:

| Scenario | deep | spectral | spatial | Fused | Outcome |
|---|---|---|---|---|---|
| All agree | 0.90 | 0.85 | 0.80 | **0.71** | detected |
| Two of three | 0.90 | 0.90 | 0.20 | **0.71** | detected |
| Deep alone | 0.95 | 0.10 | 0.10 | **0.38** | rejected |

That last row is the entire point of the redesign.

Per-layer contributions are retained so the UI can attribute any detection to the evidence that
actually drove it.

### 3.6 Per-pixel false-alarm suppression — `suppression.py`

`services/false_alarm.py` scores the *scene*. This module works one level down, on the map itself,
in four ordered stages — each recording how much area it removed:

1. **Quality masking** — cloud/shadow/saturated/nodata probability zeroed outright.
2. **Registration residual** — misalignment produces change along strong edges and nowhere else.
   High-gradient pixels are discounted by up to 80 %, scaled by the residual (saturating at 2 px);
   a pair that failed to register takes a 0.5 severity floor.
3. **Context corroboration** — scores scaled by neighbourhood support over the context window;
   an unsupported pixel retains 55 %.
4. **Morphological cleanup** — opening plus a minimum-region-size filter drops the remaining
   isolated detections.

> **Critical:** severity comes from the *measured post-warp residual*, never from the before/after
> correlation. Genuine ground change lowers that correlation just as misalignment does, so keying
> the penalty off it suppresses exactly the detections the pipeline exists to find. (See §5.)

Removed pixels are pushed just below threshold rather than to zero, so the rendered overlay still
shows the faint signal that was rejected.

### 3.7 Change typing and confidence

Connected components are classified by the existing 4-class typer (construction, clearance,
water extent, road development). Region confidence is then tempered by how much independent
evidence supports *that region*:

```
confidence = classifier_confidence · (0.7 + 0.3 · region_agreement)
```

Scene-level scoring in `false_alarm.evaluate()` gained four optional inputs — omit them and it
behaves exactly as the original single-signal scorer:

| Input | Effect |
|---|---|
| `evidence_agreement` | ≥ 0.6 boosts; < 0.30 raises a `single_evidence_source` confound |
| `clear_fraction` | < 0.5 raises a `masked_coverage` confound |
| `radiometry_normalized` | Softens the radiometric-shift penalty (0.6 → 0.85), severity medium → low |
| `registration_residual_px` + `registration_aligned` | Judges geometry on the residual instead of correlation |

Confidence becomes `0.45·score + 0.35·quality + 0.20·agreement` when agreement is supplied
(otherwise the original `0.6·score + 0.4·quality`). Corroboration boosts now consume **headroom**
(`score + boost·(1 − score)`) rather than adding flat amounts, which previously pinned every good
detection at exactly 1.0.

### 3.8 Scene-level figures

`raw_change_score` and `evidence_agreement` are measured **inside the detected change**, not
averaged over the tile. A tile-wide average of a correctly localised 2 % detection is ~0.05 and
reads as "nothing happened"; what an analyst needs is how strong the evidence is *where* change was
found, alongside `change_area_m2` for how much ground it covers.

### 3.9 Temporal corroboration

Each additional date in the window is scored by the **same multi-evidence pipeline** against the
baseline (capped at `MAX_CORROBORATION_PASSES = 12`). Persistence therefore means "several
independent evidence types agreed again", not "the embedding moved again". The per-pass
`evidence_agreement` is surfaced on each observation in the timeline.

---

## 4. Module inventory

| File | Lines | Role |
|---|---|---|
| `algorithms/imageops.py` | 245 | Integral-image box filters, morphology, connected labelling, robust statistics — pure NumPy with OpenCV/SciPy as optional accelerators |
| `algorithms/masking.py` | 219 | Cloud/shadow/nodata masking, SCL and heuristic paths |
| `algorithms/evidence.py` | 417 | The three evidence layers + shared calibration |
| `algorithms/fusion.py` | 119 | Reliability-weighted fusion with corroboration |
| `algorithms/suppression.py` | 192 | Per-pixel false-alarm suppression |
| `algorithms/pipeline.py` | 470 | Stage orchestration, `ChangeAnalysis`, audit trail |
| `algorithms/registration.py` | 380 | Co-registration (rewritten) |
| `algorithms/normalization.py` | 247 | PIF-linear + histogram matching |
| `tests/test_change_pipeline.py` | 747 | 47 tests covering every stage |

Every operator in `imageops.py` has a NumPy reference implementation, so the pipeline behaves
identically whether or not OpenCV and SciPy are installed.

---

## 5. Bugs found and fixed during implementation

These were pre-existing defects that the new evidence chain exposed.

### 5.1 Sign error in the FFT phase-correlation fallback

`cv2.phaseCorrelate(a, b)` reports how far `b` sits from `a`. Bringing `b` back onto `a` requires
translating by the **negative** of that offset. The code applied it as-is, *doubling* the
misalignment instead of removing it.

It went unnoticed because the same code path returned fabricated correlations
(`correlation_after = max(corr_before, 0.94)`) rather than measuring the warped result. On a
5 px-shifted test pair the residual came back as exactly 10 px — twice the true offset.

**Fixed:** negate the offset; measure every correlation on the actual imagery. The same pair now
goes 0.729 → **1.000** correlation with 0.0 px residual.

### 5.2 Edge suppression keyed off inter-date correlation

Correlation between two dates falls with genuine ground change as well as with misalignment. A
well-registered pair (0.11 px residual) containing a real 32 % change reported 0.35 correlation,
which both the per-pixel suppressor and the scene scorer read as "misalignment artefact" — the
detection suppressed itself. Scene change score went **0.58 → 1.0** once fixed.

**Fixed:** both now use the measured post-warp residual and the `is_aligned` flag.

### 5.3 `uint8` quantisation destroyed low-contrast correlation

Casting float reflectance to 8 bits collapsed dark tiles to ~3 grey levels, reporting two
near-identical images as uncorrelated (0.096).

**Fixed:** percentile stretch for the OpenCV input; correlation measured on float luminance.

### 5.4 Absolute shadow threshold rejected entire dark scenes

The RGB shadow heuristic used `brightness < 0.10`. On any dark tile — open water, dense canopy,
low winter light — that masked **100 %** of the pixels, leaving the detector nothing to compare.

**Fixed:** the cut-off is now scene-relative (`0.45 × median brightness`, capped by the absolute
ceiling), with a rail that discards the shadow mask entirely if it would reject more than 90 % of a
tile — at that point the heuristic is diagnosing itself, not the imagery.

Cloud remains an absolute test: a cloud really is bright, and a fully clouded tile *should* come
back fully masked.

---

## 6. Configuration

All environment-driven, in `backend/config.py`:

| Variable | Default | Meaning |
|---|---|---|
| `CHANGE_PROB_THRESHOLD` | `0.5` | Fused probability above which a pixel counts as changed |
| `W_EVIDENCE_DEEP` | `0.45` | Prior weight of the deep EO feature layer |
| `W_EVIDENCE_SPECTRAL` | `0.35` | Prior weight of the spectral layer |
| `W_EVIDENCE_SPATIAL` | `0.20` | Prior weight of the spatial/context layer |
| `CHANGE_CONTEXT_RADIUS` | `3` | Window radius (px) for spatial consistency and corroboration |
| `CHANGE_MIN_REGION_PIXELS` | `8` | Smallest connected component kept as a real region |
| `CLOUD_MASK_DILATION` | `2` | Radius (px) by which cloud/shadow masks are grown |

Weights need not sum to 1 — fusion normalises by total effective weight.

---

## 7. API and storage changes

All response changes are **additive**; every pre-existing field keeps its name and meaning.

### New top-level fields on `/api/change/detect`

| Field | Contents |
|---|---|
| `evidence_layers[]` | Per-layer weight, reliability, mean/p95 probability, changed fraction, justification, stats |
| `fusion` | Normalised weights, per-layer contributions, mean agreement, corroboration floor |
| `masking` | Per-date mask summaries (method, cloud/shadow/nodata fractions, notes) + joint clear fraction |
| `normalization` | Method, fitted gains and offsets, PIF fraction, scene shift before/after |
| `suppression` | Per-stage pixel counts and explanations |
| `pipeline` | Version, threshold, and the ordered stage audit (`ok` / `degraded` / `skipped` + detail + metrics) |

Also extended: `evidence` (agreement, clear fraction, layer availability flags, five new checklist
rows), `change_regions[].evidence` (per-layer response inside each region), `registration.residual_shift_px`,
`observations[].evidence_agreement`.

`method` now reads `multi-evidence-1.0/prithvi-onnx`, `/placeholder-features` or `/spectral-spatial`.

TypeScript types in `frontend/lib/api.ts` were updated to match (`tsc --noEmit` clean). No frontend
component required changes.

### Database

`ChangeResult` gained two nullable JSON columns — `evidence_layers` and `pipeline_stages` — added
to the existing `_ensure_ingestion_schema()` migration path in `db/database.py`, so databases
created by an older checkout upgrade in place.

---

## 8. Verification

**Test suite:** 93 passing, up from 44. `tests/test_change_pipeline.py` adds 47 covering calibration,
each evidence layer, masking, PIF normalization, fusion arithmetic, each suppression stage,
scene-level scoring, and end-to-end behaviour.

**Accuracy** — against an independent spectral-index-threshold reference (a detector built on
different logic) on the real bi-temporal demo scene pair:

| Metric | Result |
|---|---|
| Recall | **0.975** |
| Precision | **0.973** |
| IoU | **0.95** |

**Behavioural guarantees under test:**

- Identical pair → `changed_fraction < 0.01`, `no_significant_change`
- Pure illumination/gain shift → not detected
- Real change *plus* illumination shift → still detected
- Cloud over the changed area → suppressed, not detected
- One loud layer, two quiet → fused below threshold
- Uniformly dark scene → not mass-masked as shadow
- Missing feature extractor, or one that raises → degrades to spectral + spatial, stage marked `skipped`

**End-to-end through `run_change_detection()`** (throwaway SQLite DB, demo scenes, placeholder
feature extractor):

| Path | Result |
|---|---|
| Multispectral `.npz` | construction / appearance, 213.15 ha, score 0.879, confidence 0.903 |
| RGB-thumbnail fallback | construction, 183.93 ha, score 0.738, confidence 0.794, spectral reliability 0.55 |

The RGB path correctly reports lower confidence and smaller area — the intended graceful
degradation rather than a silent quality drop.

**Pre-existing failures resolved:** `test_pair_features_fallback_together_for_ambiguous_side` and
`test_difference_to_change_map_rejects_mixed_feature_shapes` encoded contracts the old code had
dropped (fall back to a single feature space for both dates; refuse to difference mismatched
feature spaces) and now pass.

**Unrelated failures still open** (untouched by this work): ingestion band count, geocoder river
distance, sensor-alias casing.

---

## 9. Known limitations

- **Calibration constants are literature-informed, not trained.** `evidence.py` floors and spans
  were chosen to be physically sensible and validated against the demo scenes; a labelled change
  dataset would let them be fitted properly.
- **Shadow detection is heuristic without SCL.** No solar-geometry projection is attempted; a dark
  patch that is neither cloud shadow nor water may be masked.
- **Temporal corroboration is pairwise against the baseline**, not a full time-series model. It
  cannot distinguish a gradual trend from a step change.
- **Region typing is unchanged**, a rule-based spectral/morphological classifier. The new pipeline
  improves *where* it is applied and how its confidence is tempered, not its class logic.
- **Ingestion could not be re-run locally** to regenerate tile packs — the demo scenes lack the
  provenance sidecars `ingest.py` requires — so service-level verification used a throwaway
  database built from the same GeoTIFFs.
