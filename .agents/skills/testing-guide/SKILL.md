---
name: testing-guide
description: Test suite structure, how to run tests, and conventions for writing new tests in TerreX. Use this skill when adding tests, debugging test failures, or understanding what is covered by the existing test suite.
---

# Testing Guide

## When to Use
- Adding a new test or debugging a failing one
- Checking what is already covered before implementing a feature
- Running the test suite locally

## Running Tests
```bash
pytest tests/ -v                          # all tests
pytest tests/test_algorithms.py -v       # single file
pytest tests/test_tier1.py::test_text_search -v   # single test
pytest tests/ --cov=backend              # with coverage
```
Requires: `backend/requirements.txt`. Uses SQLite + synthetic data — no Docker needed.

## Test Files

| File | Coverage |
|------|---------|
| `test_tier1.py` | End-to-end: ingest ? text search ? image search ? change ? ranking |
| `test_algorithms.py` | Unit: spectral indices, co-registration, change classifier, normalization |
| `test_ingestion_and_change.py` | Integration: synthetic GeoTIFF ? detect change |
| `test_quality_and_ingestion.py` | Quality scoring + ingestion pipeline |
| `test_search_image.py` | Image-to-image search endpoint |
| `test_time_series_change.py` | Multi-temporal persistence filter |
| `test_vector_store.py` | Qdrant upsert/query/delete |
| `test_capabilities.py` | System status endpoint |

## Writing Tests — Rules
1. **Offline only** — no live satellite API calls
2. Use `tmp_path` fixture for file I/O
3. Each test gets a fresh SQLite DB — never share state
4. Always assert `is_placeholder` flags are correctly set when models are not staged

## Minimal Template
```python
def test_spectral_indices(tmp_path):
    import numpy as np
    from services.algorithms.spectral import compute_spectral_indices

    raster = np.random.rand(4, 256, 256).astype(np.float32)
    indices = compute_spectral_indices(raster)

    assert indices.ndvi.shape == (256, 256)
    assert -1.0 <= float(indices.ndvi.mean()) <= 1.0
```

## Synthetic Demo Data
```bash
python scripts/generate_sample_data.py
# Writes data/incoming/*.tif + *.provenance.json
# River (NDWI high) + growing settlement across 5 dates + 1 cloudy scene
```
