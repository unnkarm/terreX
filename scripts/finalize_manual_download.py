import sys
import json
from pathlib import Path
from datetime import datetime

def finalize():
    if len(sys.argv) < 2:
        print("Usage: python finalize_manual_download.py <path_to_downloaded_tif>")
        sys.exit(1)
        
    tif_path = Path(sys.argv[1])
    if not tif_path.exists():
        print(f"File not found: {tif_path}")
        sys.exit(1)
        
    print(f"Creating provenance sidecar for: {tif_path.name}")
    print("Please answer the following questions:\n")
    
    portal = input("Source Portal (1: Bhuvan, 2: Bhoonidhi): ").strip()
    source_portal = "Bhuvan" if portal == "1" else "Bhoonidhi"
    
    dataset = input("Underlying Dataset (e.g. AWiFS, LISS-III, LISS-IV, Cartosat-2S): ").strip()
    satellite = input("Satellite (e.g. Resourcesat-2, Cartosat-2): ").strip()
    sensor = input("Sensor (e.g. AWiFS, LISS-III): ").strip()
    acq_date = input("Acquisition Date (YYYY-MM-DD): ").strip()
    res = input("Resolution in meters (e.g. 56, 23.5, 5.8): ").strip()
    
    cloud_cov = input("Cloud Cover Percentage (0-100 or press Enter if unknown): ").strip()
    
    print("\nBounding Box:")
    minlon = float(input("Min Longitude: ").strip())
    minlat = float(input("Min Latitude: ").strip())
    maxlon = float(input("Max Longitude: ").strip())
    maxlat = float(input("Max Latitude: ").strip())
    
    sidecar = {
        "source_portal": source_portal,
        "underlying_dataset": dataset,
        "satellite": satellite,
        "sensor": sensor,
        "acquisition_date": acq_date,
        "resolution_m": float(res),
        "bounding_box": [minlon, minlat, maxlon, maxlat],
        "license": "Bhuvan Open Data License" if portal == "1" else "ISRO Bhoonidhi Open Data Terms",
        "download_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "cloud_cover_pct": float(cloud_cov) if cloud_cov else None,
        "ps_named_source": portal == "1", # Bhoonidhi is supplementary
        "notes": "" if portal == "1" else "Supplementary source, not explicitly named in PS §7.1"
    }
    
    sidecar_path = tif_path.with_name(f"{tif_path.stem}.provenance.json")
    with open(sidecar_path, "w") as f:
        json.dump(sidecar, f, indent=2)
        
    print(f"\nSuccess! Created {sidecar_path.name}")
    print("You can now safely move the TIF and this JSON sidecar into data/incoming/")

if __name__ == "__main__":
    finalize()
