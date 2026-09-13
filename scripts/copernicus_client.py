"""
Copernicus Data Space Ecosystem (CDSE) client for TerreX acquisition.

Handles:
  - OAuth2 Resource Owner Password Credentials flow (grant_type=password,
    client_id=cdse-public).  Supports optional client-credentials flow when
    COPERNICUS_CLIENT_ID / COPERNICUS_CLIENT_SECRET are set instead.
  - OData v1 catalog search for SENTINEL-2 and SENTINEL-1.
  - Streaming download with exponential backoff on 429/503.

Auth endpoint confirmed against live docs (2025):
  https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token

OData search base:
  https://catalogue.dataspace.copernicus.eu/odata/v1/Products

Download:
  https://catalogue.dataspace.copernicus.eu/odata/v1/Products(<UUID>)/$value

Credentials are read ONLY from env vars — never hardcoded.
This module lives under scripts/ and is NEVER imported by the FastAPI runtime.
"""
from __future__ import annotations

import json
import os
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

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
# Constants (can be overridden via env)
# ---------------------------------------------------------------------------
_TOKEN_URL = os.getenv(
    "COPERNICUS_TOKEN_URL",
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token",
)
_ODATA_BASE = os.getenv(
    "COPERNICUS_ODATA_BASE",
    "https://catalogue.dataspace.copernicus.eu/odata/v1",
)
_DOWNLOAD_BASE = os.getenv(
    "COPERNICUS_DOWNLOAD_BASE",
    "https://download.dataspace.copernicus.eu/odata/v1",
)


class CopernicusError(RuntimeError):
    """Raised for authentication, catalog, or download failures."""


@dataclass
class _Token:
    access_token: str
    refresh_token: Optional[str]
    expires_at: float  # unix timestamp


def _backoff(attempt: int) -> None:
    delay = min(60.0, 2.0 ** attempt)
    print(f"  [backoff] waiting {delay:.0f}s before retry {attempt + 1}...")
    time.sleep(delay)


class CopernicusClient:
    """
    Authenticated Copernicus Data Space Ecosystem catalog + download client.

    Credential priority:
      1. Client Credentials flow — set COPERNICUS_CLIENT_ID + COPERNICUS_CLIENT_SECRET
      2. Resource Owner Password flow — set COPERNICUS_USERNAME + COPERNICUS_PASSWORD
    """

    def __init__(self, session: Optional[Any] = None) -> None:
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        except ImportError:
            pass

        # Client credentials flow (preferred when client ID/secret are available)
        self._client_id = os.getenv("COPERNICUS_CLIENT_ID")
        self._client_secret = os.getenv("COPERNICUS_CLIENT_SECRET")

        # Resource Owner Password flow (fallback; works with plain account)
        self._username = os.getenv("COPERNICUS_USERNAME")
        self._password = os.getenv("COPERNICUS_PASSWORD")

        if not ((self._client_id and self._client_secret) or
                (self._username and self._password)):
            raise CopernicusError(
                "Set COPERNICUS_USERNAME + COPERNICUS_PASSWORD (resource-owner flow) "
                "or COPERNICUS_CLIENT_ID + COPERNICUS_CLIENT_SECRET (client-credentials flow) "
                "before running acquisition scripts."
            )

        if requests is None:
            raise CopernicusError("The 'requests' package is required for acquisition.")

        self.session = session or requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "TerreX-Copernicus/1.0",
        })
        self._token: Optional[_Token] = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> str:
        """Obtain an access token, retrying 429 with backoff."""
        if self._client_id and self._client_secret:
            payload = {
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }
        else:
            payload = {
                "grant_type": "password",
                "client_id": "cdse-public",
                "username": self._username,
                "password": self._password,
            }

        for attempt in range(5):
            resp = self.session.post(
                _TOKEN_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            if resp.status_code == 429:
                _backoff(attempt)
                continue
            if not resp.ok:
                raise CopernicusError(
                    f"Copernicus authentication failed ({resp.status_code}): "
                    f"{resp.text[:400]}"
                )
            body = resp.json()
            access_token = body.get("access_token")
            if not access_token:
                raise CopernicusError(
                    "Copernicus token response missing 'access_token'. "
                    f"Response: {resp.text[:400]}"
                )
            expires_in = float(body.get("expires_in", 600))
            refresh_token = body.get("refresh_token")
            self._token = _Token(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=time.time() + max(60.0, expires_in - 60.0),
            )
            self.session.headers.update({"Authorization": f"Bearer {access_token}"})
            print(f"  [copernicus] authenticated (token expires in {int(expires_in)}s)")
            return access_token

        raise CopernicusError("Copernicus authentication failed after 5 attempts.")

    def _refresh(self) -> None:
        """Use refresh token if available; otherwise re-authenticate."""
        if self._token and self._token.refresh_token:
            payload = {
                "grant_type": "refresh_token",
                "client_id": self._client_id or "cdse-public",
                "refresh_token": self._token.refresh_token,
            }
            resp = self.session.post(
                _TOKEN_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            if resp.ok:
                body = resp.json()
                access_token = body.get("access_token")
                if access_token:
                    self._token.access_token = access_token
                    self._token.expires_at = time.time() + float(body.get("expires_in", 600)) - 60
                    self.session.headers.update({"Authorization": f"Bearer {access_token}"})
                    return
        self.authenticate()

    def _ensure_token(self) -> None:
        if self._token is None or time.time() >= self._token.expires_at:
            if self._token and self._token.refresh_token:
                self._refresh()
            else:
                self.authenticate()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _bbox_to_wkt(self, bbox: List[float]) -> str:
        """Convert [minLon, minLat, maxLon, maxLat] to a WKT POLYGON."""
        minlon, minlat, maxlon, maxlat = bbox
        return (
            f"POLYGON(("
            f"{minlon} {minlat},{maxlon} {minlat},"
            f"{maxlon} {maxlat},{minlon} {maxlat},"
            f"{minlon} {minlat}"
            f"))"
        )

    def search(
        self,
        bbox: List[float],
        start_date: str,
        end_date: str,
        collection: str = "SENTINEL-2",
        cloud_cover_max: Optional[float] = 20.0,
        product_type: Optional[str] = None,
        max_results: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Query the OData v1 catalog.

        collection: "SENTINEL-2" or "SENTINEL-1"
        product_type: e.g. "S2MSI2A" for L2A, "GRD" for Sentinel-1 GRD
        Returns list of normalised scene dicts.
        """
        self._ensure_token()
        wkt = self._bbox_to_wkt(bbox)

        filters = [
            f"Collection/Name eq '{collection}'",
            f"ContentDate/Start gt {start_date}T00:00:00.000Z",
            f"ContentDate/Start lt {end_date}T23:59:59.999Z",
            f"OData.CSC.Intersects(area=geography'SRID=4326;{wkt}')",
        ]
        if cloud_cover_max is not None and collection == "SENTINEL-2":
            filters.append(f"Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value le {cloud_cover_max:.1f})")
        if product_type:
            filters.append(f"contains(Name,'{product_type}')")

        filter_str = " and ".join(filters)
        params = {
            "$filter": filter_str,
            "$top": str(max_results),
            "$orderby": "ContentDate/Start desc",
        }

        url = f"{_ODATA_BASE}/Products"
        for attempt in range(5):
            try:
                resp = self.session.get(url, params=params, timeout=60)
            except requests.exceptions.ConnectionError as exc:
                if attempt < 4:
                    _backoff(attempt)
                    continue
                raise CopernicusError(f"Copernicus search connection error: {exc}") from exc
            if resp.status_code == 401 and attempt == 0:
                self._refresh()
                continue
            if resp.status_code in (429, 503):
                _backoff(attempt)
                continue
            if not resp.ok:
                raise CopernicusError(
                    f"Copernicus search failed ({resp.status_code}): {resp.text[:400]}"
                )
            break
        else:
            raise CopernicusError("Copernicus search failed after retries.")

        items = resp.json().get("value", [])
        results = []
        for item in items:
            results.append(self._normalise(item, bbox, collection))
        return results

    def _normalise(self, item: Dict[str, Any], bbox: List[float], collection: str) -> Dict[str, Any]:
        """Map OData item to a standardised scene dict."""
        # OData returns dates like "2024-03-15T10:22:11.000Z"
        raw_date = item.get("ContentDate", {}).get("Start", "") or ""
        acq_date = raw_date[:10]  # YYYY-MM-DD

        # Cloud cover is buried in Attributes list
        cloud_cover = None
        for attr in item.get("Attributes", []) or []:
            if isinstance(attr, dict) and attr.get("Name") == "cloudCover":
                try:
                    cloud_cover = float(attr.get("Value", 0))
                except (TypeError, ValueError):
                    pass
                break

        # Footprint from GeoFootprint
        footprint_geo = item.get("GeoFootprint") or {}
        if footprint_geo.get("type") == "Polygon":
            coords = footprint_geo.get("coordinates", [[]])[0]
            if coords:
                lons = [c[0] for c in coords]
                lats = [c[1] for c in coords]
                footprint_bbox = [min(lons), min(lats), max(lons), max(lats)]
            else:
                footprint_bbox = bbox
        else:
            footprint_bbox = bbox

        # Determine sensor/satellite from Name and collection
        name = item.get("Name", "")
        if collection == "SENTINEL-2":
            satellite = "Sentinel-2A" if "_MSIL" in name and name[2] == "A" else "Sentinel-2B"
            sensor = "MSI"
            resolution_m = 10.0
        elif collection == "SENTINEL-1":
            satellite = "Sentinel-1A" if name.startswith("S1A") else "Sentinel-1B"
            sensor = "SAR-C"
            resolution_m = 5.0  # IW GRD, 10m; ground range 5–40m
        else:
            satellite = collection
            sensor = "unknown"
            resolution_m = 10.0

        return {
            "product_id": item.get("Id", ""),
            "name": name,
            "acquisition_date": acq_date,
            "cloud_cover": cloud_cover,
            "footprint_bbox": footprint_bbox,
            "bbox": footprint_bbox,
            "satellite": satellite,
            "sensor": sensor,
            "resolution_m": resolution_m,
            "collection": collection,
            "online": item.get("Online", True),
            "raw": item,
        }

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download(self, product_id: str, dest_path: Path) -> Path:
        """
        Download a product by UUID to dest_path.
        Streams in 1 MB chunks; backs off on 429/503.
        Unpacks ZIP if the server returns one and converts JP2 to GeoTIFF.
        """
        self._ensure_token()
        url = f"{_DOWNLOAD_BASE}/Products({product_id})/$value"
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest_path.with_suffix(dest_path.suffix + ".download")

        for attempt in range(5):
            current_url = url
            resp = None
            # Follow redirects manually up to 5 hops to preserve Authorization header across domains
            for _ in range(5):
                if current_url.startswith("http://"):
                    current_url = "https://" + current_url[7:]
                headers = {"Authorization": f"Bearer {self._token.access_token}"}
                resp = self.session.get(
                    current_url,
                    headers=headers,
                    stream=True,
                    allow_redirects=False,
                    timeout=600,
                )
                if resp.status_code in (301, 302, 303, 307, 308) and "Location" in resp.headers:
                    current_url = resp.headers["Location"]
                    continue
                break

            if resp is None:
                raise CopernicusError(f"No response received from server for {product_id}")

            if resp.status_code == 401 and attempt == 0:
                self._refresh()
                continue
            if resp.status_code in (429, 503):
                _backoff(attempt)
                continue
            if not resp.ok:
                raise CopernicusError(
                    f"Copernicus download failed for {product_id} "
                    f"({resp.status_code}): {resp.text[:300]}"
                )
            content_type = resp.headers.get("Content-Type", "")
            if "json" in content_type:
                raise CopernicusError(
                    f"Copernicus returned JSON instead of a product file for {product_id}: "
                    f"{resp.text[:300]}"
                )
            total = int(resp.headers.get("Content-Length", 0))
            written = 0
            with tmp.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        written += len(chunk)
            print(f"  [copernicus] downloaded {written // (1024*1024)} MB -> {dest_path.name}")
            break
        else:
            raise CopernicusError(f"Download for {product_id} failed after retries.")

        # CDSE typically sends a SAFE ZIP; extract the best image inside
        if zipfile.is_zipfile(tmp):
            with zipfile.ZipFile(tmp) as zf:
                all_imgs = [m for m in zf.namelist() if m.lower().endswith((".tif", ".tiff", ".jp2"))]
                if not all_imgs:
                    raise CopernicusError(
                        f"Copernicus ZIP for {product_id} contained no GeoTIFF or JP2 file"
                    )

                def _img_priority(name: str) -> int:
                    nl = name.lower()
                    if "tci_10m" in nl or "tci.jp2" in nl or "tci.tif" in nl:
                        return 0
                    if "10m" in nl and ("b02" in nl or "b04" in nl or "b03" in nl):
                        return 1
                    if "measurement" in nl and nl.endswith((".tif", ".tiff")):
                        return 2
                    if nl.endswith((".tif", ".tiff")):
                        return 3
                    return 4

                chosen = sorted(all_imgs, key=_img_priority)[0]
                extracted_tmp = dest_path.with_suffix(dest_path.suffix + ".extracted")
                with zf.open(chosen) as src, extracted_tmp.open("wb") as dst:
                    dst.write(src.read())
                print(f"  [copernicus] extracted {chosen} from ZIP")

            tmp.unlink(missing_ok=True)

            if chosen.lower().endswith(".jp2"):
                try:
                    import rasterio
                    with rasterio.open(extracted_tmp) as src_ds:
                        profile = src_ds.profile.copy()
                        profile.update(driver="GTiff", compress="deflate")
                        with rasterio.open(dest_path, "w", **profile) as dst_ds:
                            dst_ds.write(src_ds.read())
                    extracted_tmp.unlink(missing_ok=True)
                    print(f"  [copernicus] converted {chosen} (JP2) -> {dest_path.name} (GeoTIFF)")
                except Exception as exc:
                    print(f"  [copernicus] Warning: could not convert JP2 to GTiff: {exc}; using raw file")
                    extracted_tmp.replace(dest_path)
            else:
                extracted_tmp.replace(dest_path)
        else:
            tmp.replace(dest_path)

        return dest_path


def download_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()
