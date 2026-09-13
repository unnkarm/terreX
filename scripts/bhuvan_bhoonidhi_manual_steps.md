# Bhuvan / Bhoonidhi Manual Acquisition Steps

Since Bhuvan and Bhoonidhi portals require interactive logins and captcha-protected manual selection, automated API downloads are not supported without breaking terms of service or encountering IP blocks.

Follow these steps to manually acquire ISRO data for TerreX and automatically attach valid provenance metadata.

## Bhuvan (Primary PS-Named Source)
*Provides AWiFS (56m) and LISS-III (23.5m) open data.*

1. **Register/Login:** Go to [Bhuvan Open Data Portal](https://bhuvan-app3.nrsc.gov.in/data/download/index.php).
2. **Select Category:** Choose `Satellites / Sensors` > `Resourcesat-2` > `AWiFS` or `LISS-III`.
3. **Select Area of Interest:** 
   - Choose `Bounding Box` mode.
   - Enter `88.40` to `88.48` for Longitude and `22.56` to `22.60` for Latitude (Salt Lake / New Town).
4. **Select Date Range:** Pick any date spanning 2024–2026.
5. **Download:** Click search, review the cloud cover in the metadata popup, and click Download.
6. **Extract:** Unzip the downloaded `.tar.gz` or `.zip` and locate the core multispectral `.tif` file.
7. **Finalize:** Run the finalizing script:
   `python scripts/finalize_manual_download.py <path-to-the.tif>`
8. **Move:** Move both the `.tif` and its `.provenance.json` to `data/incoming/bhuvan/`.

## Bhoonidhi (Supplementary Source)
*Provides LISS-IV (5.8m) and Cartosat-2 (1m) data in limited open tiers.*

1. **Register/Login:** Go to [Bhoonidhi NRSC](https://bhoonidhi.nrsc.gov.in/bhoonidhi/home.html).
2. **Select AOI:** Use the map tools to draw a box around Kolkata / Salt Lake.
3. **Filter:** Select `Open Data` tier and choose `LISS-IV` or `Cartosat`.
4. **Download:** Add scenes to your cart and checkout. Download the archive.
5. **Finalize:** Run the finalizing script:
   `python scripts/finalize_manual_download.py <path-to-the.tif>`
   *Note: Select 'Bhoonidhi' when prompted by the script to correctly flag it as a supplementary source.*
6. **Move:** Move both the `.tif` and its `.provenance.json` to `data/incoming/bhoonidhi/`.
