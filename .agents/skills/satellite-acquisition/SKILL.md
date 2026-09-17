---
name: satellite-acquisition
description: Step-by-step runbook for acquiring, downloading, and ingesting satellite imagery into TerreX. Covers Sentinel-1/2 (Copernicus), Landsat (USGS), ISRO/Bhoonidhi, Bhuvan, and Microsoft Planetary Computer. Use this skill for any task involving data download scripts, provenance sidecars, or adding new scenes to the system.
---

# Satellite Acquisition

## When to Use
- Running or modifying acquisition scripts in `scripts/`
- Debugging provenance sidecar errors during ingestion
- Adding support for a new satellite data source

## Acquisition Scripts

| Script | Source | Auth needed |
|--------|--------|-------------|
| `acquire_sentinel2.py` | Copernicus CDSE | `CDSE_USER` + `CDSE_PASSWORD` |
| `acquire_sentinel1.py` | Copernicus CDSE (SAR GRD) | same |
| `acquire_landsat.py` | USGS EarthExplorer | `USGS_USER` + `USGS_PASSWORD` |
| `acquire_isro.py` | Bhoonidhi/ISRO | `BHOONIDHI_API_KEY` (semi-manual) |
| `download_planetary_scenes.py` | MS Planetary Computer | none |
| `acquire_all.py` | All above | `--source` flag |

Low-level clients: `copernicus_client.py`, `usgs_client.py`, `bhoonidhi_client.py`

## Standard Workflow
```bash
cp .env.example .env  # fill in credentials
python scripts/acquire_sentinel2.py --aoi 88.2,22.4,88.5,22.7 --date-from 2024-01-01 --date-to 2024-06-30
python scripts/ingest.py            # OR: POST /api/ingest/process-incoming
python scripts/validate_provenance.py data/incoming/
```

## Provenance Sidecar (Required)
Every `.tif` must have a `.provenance.json` sidecar. Use `acquisition_common.py:write_provenance_sidecar()`.
Required fields: `source_portal`, `underlying_dataset`, `satellite`, `sensor`, `acquisition_date`, `resolution_m`, `bounding_box`, `license`, `download_date`, `ps_named_source`
Valid `source_portal` values: `Bhoonidhi` · `Bhuvan` · `Copernicus Data Space Ecosystem` · `Google Earth Engine` · `USGS EarthExplorer`

## Band Layout

| Sensor | Bands (0-indexed) |
|--------|-------------------|
| Sentinel-2 MSI | B02,B03,B04,B08,B11,B12 ? indices 0-5 |
| Sentinel-1 GRD | VV,VH ? 0,1 |
| Landsat-8 OLI | Blue,Green,Red,NIR,SWIR1,SWIR2 ? 0-5 |

## Adding a New Source
1. Write `scripts/acquire_<source>.py` following `acquire_sentinel2.py` pattern
2. Use `acquisition_common.py:write_provenance_sidecar()` for provenance
3. Add `source_portal` string to allowed set in `backend/services/ingestion.py:_load_provenance()`
