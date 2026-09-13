# TerreX Data Acquisition Setup

> **Pre-demo step only** — these scripts run offline acquisition before the demonstration.
> No network calls exist in `backend/` at runtime; this document covers the acquisition phase only.

---

## AOI — New Town / Salt Lake, Kolkata

All acquisition scripts use the same bounding box:

```
[88.40, 22.56, 88.48, 22.62]   # [minLon, minLat, maxLon, maxLat]
```

Defined once in `scripts/acquisition_common.py → DEFAULT_BBOX`. Change it there to update all scripts at once.

---

## Source 1 — Copernicus Data Space Ecosystem (Primary)

**Provides**: Sentinel-2 L2A (multispectral backbone) + Sentinel-1 GRD (SAR)

### Account Registration
1. Go to [https://dataspace.copernicus.eu](https://dataspace.copernicus.eu) → **Register**
2. Activate your account via the confirmation email

### Auth Method
The acquisition scripts use the **Resource Owner Password Credentials** OAuth2 flow (`grant_type=password`).  
Token endpoint (confirmed 2025):
```
https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token
```

No extra OAuth client registration is required for the ROPC flow (`client_id=cdse-public` is a public client).

**Alternative (preferred for production)**: Register an OAuth client in the Copernicus Sentinel Hub Dashboard, set `Supported Flow` to `Client Credentials`, and use `COPERNICUS_CLIENT_ID` + `COPERNICUS_CLIENT_SECRET` instead.

### Set Credentials in `.env`

```dotenv
# Copernicus Data Space Ecosystem
COPERNICUS_USERNAME=your_cdse_email@example.com
COPERNICUS_PASSWORD=your_cdse_password

# OR (client-credentials flow — preferred):
# COPERNICUS_CLIENT_ID=your_client_id
# COPERNICUS_CLIENT_SECRET=your_client_secret
```

> `.env` is in `.gitignore` — credentials are never committed.

---

## Source 2 — USGS EarthExplorer M2M API (Landsat Gap-Fill)

**Provides**: Landsat 8/9 Collection 2 Level-2 for date windows where Sentinel-2 has no coverage

### Account Registration
1. Register at [https://ers.cr.usgs.gov/register](https://ers.cr.usgs.gov/register)
2. Request Machine-to-Machine access:  
   Go to **ERS Profile → Access** → request **"MACHINE"** access (may take 1–2 business days)

### Generate an Application Token
> **Important**: Since February 26, 2025, the `/login` password endpoint is retired.  
> All programmatic access requires an **Application Token**, not the account password.

1. Log in at [https://ers.cr.usgs.gov](https://ers.cr.usgs.gov)
2. Navigate to **Profile → Access → Application Tokens**
3. Click **Generate Token**
4. Copy the 64-character token immediately (it won't be shown again)

### Set Credentials in `.env`

```dotenv
# USGS EarthExplorer M2M
USGS_USERNAME=your_usgs_username
USGS_M2M_API_KEY=your_64_character_application_token
```

---

## Running Acquisition

### Prerequisites

```powershell
pip install requests python-dotenv
```

### Full acquisition (all sources)

```powershell
# From the project root
python scripts/acquire_all.py
```

This runs:
1. **Sentinel-2** → `data/incoming/sentinel2/` (6 quarterly windows, 2024–2026)
2. **Sentinel-1** → `data/incoming/sentinel1/` (monsoon windows for SAR demo)
3. **Landsat** → `data/incoming/landsat/` (gap-fill only for dates S2 missed)
4. **Provenance validation** (all sidecars checked before reporting success)

The script exits non-zero if fewer than 3 Sentinel-2 dates are acquired.

### Per-source

```powershell
python scripts/acquire_sentinel2.py
python scripts/acquire_sentinel1.py
python scripts/acquire_landsat.py
```

### Validate provenance only

```powershell
python scripts/validate_provenance.py data/incoming/
```

### Ingest into TerreX

Once files are downloaded and validated:
```powershell
curl -X POST http://localhost:8000/api/ingest/process-incoming
```

Verify ingestion:
```powershell
curl http://localhost:8000/api/ingest/scenes
```

---

## Directory Layout After Acquisition

```
data/
  incoming/
    sentinel2/          ← Sentinel-2 L2A scenes (.tif) + sidecars (.provenance.json)
    sentinel1/          ← Sentinel-1 GRD scenes + sidecars
    landsat/            ← Landsat C2L2 gap-fill scenes + sidecars
```

---

## Provenance Sidecar Schema

Every downloaded file `X.tif` gets a `X.provenance.json` with this schema
(validated by `scripts/validate_provenance.py` and enforced by ingestion):

```json
{
  "source_portal": "Copernicus Data Space Ecosystem",
  "underlying_dataset": "Sentinel-2 L2A",
  "satellite": "Sentinel-2A",
  "sensor": "MSI",
  "acquisition_date": "2024-03-15",
  "resolution_m": 10.0,
  "bounding_box": [88.40, 22.56, 88.48, 22.62],
  "license": "Copernicus open data licence (CC BY 4.0)",
  "download_date": "2026-09-10",
  "cloud_cover_pct": 4.2,
  "ps_named_source": true,
  "notes": "Product ID: abc123; Name: S2A_MSIL2A_..."
}
```

---

## Runtime Network Call Audit

Per TerreX offline constraints, no network calls should exist in `backend/` at runtime.
Verify with:

```powershell
Select-String -Path "backend\services\*.py","backend\api\*.py" -Pattern "requests\.|urllib\.|fetch\(" -CaseSensitive
```

Expected output: **zero results** (acquisition scripts in `scripts/` are excluded).

---

## Optional — ISRO Bhoonidhi (Later)

> Bhoonidhi server has been experiencing outages. Do not use as a blocker.

When Bhoonidhi is stable, `scripts/acquire_isro.py` can supplement with LISS-IV
fine-detail tiles. Set `BHOONIDHI_USER` + `BHOONIDHI_PASS` in `.env`.

---

## Optional — Bhuvan Manual Download

Bhuvan's public API only provides geocoding/LULC statistics, not imagery downloads.
For AWiFS/LISS-III tiles: go to [https://bhuvan.nrsc.gov.in](https://bhuvan.nrsc.gov.in) →
**Data Download** → manually download for the AOI → run `scripts/finalize_manual_download.py`
to attach a provenance sidecar before ingestion.
