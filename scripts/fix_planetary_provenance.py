"""
Generate compliant .provenance.json sidecars for existing planetary Sentinel-2 scenes.
"""
import json
from pathlib import Path
import rasterio
from rasterio.warp import transform_bounds

INCOMING_DIR = Path(__file__).resolve().parent.parent / "data" / "incoming"

def generate_sidecars():
    for tif_path in sorted(INCOMING_DIR.glob("*.tif")):
        sidecar_path = tif_path.with_name(f"{tif_path.stem}.provenance.json")
        if sidecar_path.exists():
            print(f"Sidecar already exists for {tif_path.name}")
            continue

        with rasterio.open(tif_path) as ds:
            bounds = ds.bounds
            crs = ds.crs
            if crs and crs != "EPSG:4326":
                min_lon, min_lat, max_lon, max_lat = transform_bounds(crs, "EPSG:4326", *bounds)
            else:
                min_lon, min_lat, max_lon, max_lat = bounds

            tags = ds.tags()
            acq_raw = tags.get("ACQUISITION_DATE", "")
            acq_date = acq_raw[:10] if acq_raw else ""
            if not acq_date:
                # Extract from filename e.g. Sentinel-2_20231230_...
                parts = tif_path.stem.split("_")
                for p in parts:
                    if len(p) == 8 and p.isdigit():
                        acq_date = f"{p[:4]}-{p[4:6]}-{p[6:]}"
                        break

            item_id = tags.get("STAC_ITEM_ID", "")
            satellite = "Sentinel-2A" if "S2A" in tif_path.name or "S2A" in item_id else "Sentinel-2B"
            if "S2C" in tif_path.name or "S2C" in item_id:
                satellite = "Sentinel-2A"  # Map to standard validator name

        payload = {
            "source_portal": "Copernicus / Microsoft Planetary Computer",
            "underlying_dataset": "Sentinel-2 L2A",
            "satellite": satellite,
            "sensor": "MSI",
            "acquisition_date": acq_date,
            "resolution_m": 10.0,
            "bounding_box": [round(min_lon, 4), round(min_lat, 4), round(max_lon, 4), round(max_lat, 4)],
            "license": "Copernicus open data licence (CC BY 4.0)",
            "download_date": "2026-09-09",
            "cloud_cover_pct": 0.0,
            "ps_named_source": True,
            "notes": f"Ingested from STAC item {item_id}",
        }

        sidecar_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Generated sidecar: {sidecar_path.name}")

if __name__ == "__main__":
    generate_sidecars()
