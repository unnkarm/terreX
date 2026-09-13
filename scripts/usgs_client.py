"""
USGS EarthExplorer Machine-to-Machine (M2M) API client for TerreX acquisition.

Handles:
  - Token-based authentication via /login-token (as of Feb 2025, the
    legacy /login password endpoint was retired; API tokens are now required).
  - Scene search for landsat_ot_c2_l2 using spatialFilter + acquisitionFilter.
  - Download via /download-options → /download-request → /download-retrieve.
  - Exponential backoff on HTTP 429 and M2M errorCode "RATE_LIMIT".

API base confirmed against live M2M docs (2025):
  https://m2m.cr.usgs.gov/api/api/json/stable/

Credentials are read ONLY from env vars — never hardcoded.
This module lives under scripts/ and is NEVER imported by the FastAPI runtime.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    requests = None


import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Constants (overridable via env)
# ---------------------------------------------------------------------------
_M2M_BASE = os.getenv(
    "USGS_M2M_BASE",
    "https://m2m.cr.usgs.gov/api/api/json/stable",
)


class USGSError(RuntimeError):
    """Raised for M2M authentication, search, or download failures."""


def _backoff(attempt: int) -> None:
    delay = min(120.0, 2.0 ** attempt)
    print(f"  [usgs] rate-limited -- waiting {delay:.0f}s before retry {attempt + 1}...")
    time.sleep(delay)


def _m2m_post(session: Any, endpoint: str, payload: Dict[str, Any], api_key: Optional[str] = None) -> Any:
    """POST a JSON payload to an M2M endpoint, return parsed response data."""
    url = f"{_M2M_BASE}/{endpoint}"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Auth-Token"] = api_key
    resp = session.post(url, json=payload, headers=headers, timeout=120)
    if not resp.ok:
        if resp.status_code == 403:
            raise USGSError(
                f"M2M {endpoint} returned HTTP 403 Forbidden. "
                "Your USGS ERS account has search access, but Machine-to-Machine download access has not been approved yet. "
                "Request 'Machine-to-Machine' access in your profile at https://ers.cr.usgs.gov/profile/access and accept the Landsat Collection 2 EULA on EarthExplorer."
            )
        raise USGSError(f"M2M {endpoint} HTTP {resp.status_code}: {resp.text[:400]}")
    body = resp.json()
    if body.get("errorCode"):
        raise USGSError(f"M2M {endpoint} error [{body['errorCode']}]: {body.get('errorMessage', '')}")
    return body.get("data")


class USGSClient:
    """
    Authenticated USGS EarthExplorer M2M API client.

    Required env vars:
      USGS_USERNAME      — USGS ERS account username
      USGS_M2M_API_KEY   — 64-character Application Token from ERS profile
                           (not the account password; generate via
                           https://ers.cr.usgs.gov/profile/access)
    """

    def __init__(self, session: Optional[Any] = None) -> None:
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        except ImportError:
            pass

        self._username = os.getenv("USGS_USERNAME")
        self._api_key = os.getenv("USGS_M2M_API_KEY")

        if not self._username or not self._api_key:
            raise USGSError(
                "USGS_USERNAME and USGS_M2M_API_KEY must be set before running acquisition. "
                "Generate the API key at https://ers.cr.usgs.gov/profile/access "
                "(select 'Application Token' under Machine-to-Machine access)."
            )

        if requests is None:
            raise USGSError("The 'requests' package is required for acquisition.")

        self.session = session or requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "TerreX-USGS-M2M/1.0",
        })
        self._auth_token: Optional[str] = None  # M2M session token (different from API key)
        self._token_obtained_at: float = 0.0

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> str:
        """
        POST to /login-token with username + API application token.
        Returns the short-lived M2M session token used in X-Auth-Token headers.
        """
        payload = {
            "username": self._username,
            "token": self._api_key,
        }
        for attempt in range(5):
            resp = self.session.post(
                f"{_M2M_BASE}/login-token",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            if resp.status_code == 429:
                _backoff(attempt)
                continue
            if not resp.ok:
                raise USGSError(
                    f"USGS M2M authentication failed ({resp.status_code}): {resp.text[:400]}"
                )
            body = resp.json()
            if body.get("errorCode"):
                raise USGSError(
                    f"USGS M2M login error [{body['errorCode']}]: {body.get('errorMessage', '')}"
                )
            token = body.get("data")
            if not token:
                raise USGSError(
                    f"USGS M2M login returned no session token. Body: {resp.text[:300]}"
                )
            self._auth_token = str(token)
            self._token_obtained_at = time.time()
            print(f"  [usgs] authenticated (session token obtained)")
            return self._auth_token

        raise USGSError("USGS M2M authentication failed after 5 attempts.")

    def _ensure_token(self) -> str:
        # M2M session tokens expire after 2 hours; re-auth proactively
        if not self._auth_token or (time.time() - self._token_obtained_at > 6900):
            self.authenticate()
        return self._auth_token  # type: ignore[return-value]

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Any:
        token = self._ensure_token()
        for attempt in range(5):
            try:
                data = _m2m_post(self.session, endpoint, payload, api_key=token)
                return data
            except USGSError as exc:
                msg = str(exc)
                if "RATE_LIMIT" in msg or "429" in msg:
                    _backoff(attempt)
                    continue
                if "AUTH" in msg.upper() and attempt == 0:
                    self.authenticate()
                    token = self._auth_token
                    continue
                raise
        raise USGSError(f"M2M {endpoint} failed after repeated rate-limit retries.")

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        bbox: List[float],
        start_date: str,
        end_date: str,
        dataset: str = "landsat_ot_c2_l2",
        cloud_cover_max: Optional[float] = 20.0,
        max_results: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Scene search.  bbox = [minLon, minLat, maxLon, maxLat].
        Returns list of normalised scene dicts.
        """
        minlon, minlat, maxlon, maxlat = bbox
        scene_filter: Dict[str, Any] = {
            "spatialFilter": {
                "filterType": "geojson",
                "geoJson": {
                    "type": "Polygon",
                    "coordinates": [[
                        [minlon, minlat],
                        [maxlon, minlat],
                        [maxlon, maxlat],
                        [minlon, maxlat],
                        [minlon, minlat],
                    ]],
                },
            },
            "acquisitionFilter": {
                "start": start_date,
                "end": end_date,
            },
        }
        if cloud_cover_max is not None:
            scene_filter["cloudCoverFilter"] = {"max": int(cloud_cover_max), "includeUnknown": False}

        payload = {
            "datasetName": dataset,
            "maxResults": max_results,
            "startingNumber": 1,
            "sortDirection": "DESC",
            "sortField": "acquisitionDate",
            "sceneFilter": scene_filter,
        }
        raw_results = self._post("scene-search", payload)
        results_list = (raw_results or {}).get("results", [])
        return [self._normalise(r, bbox, dataset) for r in results_list]

    def _normalise(self, item: Dict[str, Any], bbox: List[float], dataset: str) -> Dict[str, Any]:
        """Map M2M scene result to a standardised scene dict."""
        entity_id = item.get("entityId", "")
        display_id = item.get("displayId", entity_id)
        acq_date = str(item.get("acquisitionDate", ""))[:10]
        cloud_cover = item.get("cloudCover")

        # Spatial bounds
        sp = item.get("spatialBounds") or {}
        if sp.get("type") == "Polygon":
            coords = sp.get("coordinates", [[]])[0]
            if coords:
                lons = [c[0] for c in coords]
                lats = [c[1] for c in coords]
                footprint_bbox = [min(lons), min(lats), max(lons), max(lats)]
            else:
                footprint_bbox = bbox
        else:
            footprint_bbox = bbox

        # Determine sensor from dataset name / display ID
        if "landsat" in dataset.lower():
            if display_id.startswith("LC09") or display_id.startswith("LO09"):
                satellite = "Landsat-9"
                sensor = "OLI-2/TIRS-2"
            else:
                satellite = "Landsat-8"
                sensor = "OLI/TIRS"
            resolution_m = 30.0

        return {
            "entity_id": entity_id,
            "display_id": display_id,
            "acquisition_date": acq_date,
            "cloud_cover": float(cloud_cover) if cloud_cover is not None else None,
            "footprint_bbox": footprint_bbox,
            "bbox": footprint_bbox,
            "satellite": satellite,
            "sensor": sensor,
            "resolution_m": resolution_m,
            "dataset": dataset,
            "raw": item,
        }

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _get_download_options(self, entity_id: str, dataset: str) -> List[Dict[str, Any]]:
        payload = {"datasetName": dataset, "entityIds": [entity_id]}
        options = self._post("download-options", payload) or []
        # Return products that are available
        return [o for o in options if o.get("available")]

    def download(self, entity_id: str, dest_path: Path, dataset: str = "landsat_ot_c2_l2") -> Path:
        """
        Download a Landsat scene to dest_path via the M2M download pipeline:
          download-options → download-request → download-retrieve → HTTP GET.
        """
        # 1. Discover download options
        options = self._get_download_options(entity_id, dataset)
        if not options:
            raise USGSError(
                f"No available download options for scene {entity_id}. "
                "The scene may be offline or not yet available."
            )

        # Prefer "STANDARD" bundle (full scene), fall back to first available option
        product = next((o for o in options if o.get("productName", "").upper() == "STANDARD"), None)
        if product is None:
            product = options[0]
        product_id = product.get("id")

        # 2. Request download
        request_payload = {
            "downloads": [{"entityId": entity_id, "productId": product_id}],
            "label": f"terrex-{entity_id[:12]}",
        }
        request_result = self._post("download-request", request_payload) or {}
        available_dls = request_result.get("availableDownloads", [])
        preparing_dls = request_result.get("preparingDownloads", [])

        if available_dls:
            download_url = available_dls[0].get("url")
        elif preparing_dls:
            # Scene is being staged — poll retrieve endpoint
            label = request_payload["label"]
            download_url = None
            for wait_attempt in range(8):
                time.sleep(30)  # poll every 30s
                retrieve_result = self._post("download-retrieve", {"label": label}) or {}
                available = retrieve_result.get("available", [])
                if available:
                    download_url = available[0].get("url")
                    break
            if not download_url:
                raise USGSError(
                    f"USGS scene {entity_id} is still being prepared after 4 minutes. "
                    "Re-run the script later to complete the download."
                )
        else:
            raise USGSError(f"USGS download-request returned no URLs for {entity_id}.")

        # 3. Stream the file
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest_path.with_suffix(dest_path.suffix + ".download")

        for attempt in range(5):
            resp = self.session.get(download_url, stream=True, timeout=600)
            if resp.status_code in (429, 503):
                _backoff(attempt)
                continue
            if not resp.ok:
                raise USGSError(
                    f"USGS HTTP download failed for {entity_id} "
                    f"({resp.status_code}): {resp.text[:300]}"
                )
            written = 0
            with tmp.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        written += len(chunk)
            print(f"  [usgs] downloaded {written // (1024*1024)} MB -> {dest_path.name}")
            break
        else:
            raise USGSError(f"HTTP download for {entity_id} failed after retries.")

        # Unpack TAR.GZ if needed
        import tarfile
        if tarfile.is_tarfile(tmp):
            with tarfile.open(tmp) as tf:
                tif_members = [m for m in tf.getmembers() if m.name.lower().endswith((".tif", ".tiff"))]
                if not tif_members:
                    raise USGSError(f"USGS archive for {entity_id} has no GeoTIFF inside")
                # Prefer the surface reflectance multi-band file
                sr_member = next(
                    (m for m in tif_members if "_SR_" in m.name or "SR" in m.name.upper()),
                    tif_members[0],
                )
                with tf.extractfile(sr_member) as src, dest_path.open("wb") as dst:
                    dst.write(src.read())
            tmp.unlink(missing_ok=True)
        else:
            import zipfile
            if zipfile.is_zipfile(tmp):
                with zipfile.ZipFile(tmp) as zf:
                    tif_members = [m for m in zf.namelist() if m.lower().endswith((".tif", ".tiff"))]
                    if not tif_members:
                        raise USGSError(f"USGS ZIP for {entity_id} has no GeoTIFF inside")
                    chosen = next((m for m in tif_members if "_SR_" in m or "SR" in m.upper()), tif_members[0])
                    with zf.open(chosen) as src, dest_path.open("wb") as dst:
                        dst.write(src.read())
                tmp.unlink(missing_ok=True)
            else:
                tmp.replace(dest_path)

        return dest_path

    def logout(self) -> None:
        """Cleanly invalidate the M2M session token."""
        if self._auth_token:
            try:
                self._post("logout", {})
            except Exception:
                pass
            self._auth_token = None


def download_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()
