"""Small, credential-safe client for the documented Bhoonidhi API.

This module is intentionally kept under ``scripts/``.  It is never imported by
the FastAPI application: network access is confined to the pre-demo acquisition
phase.  Endpoint URLs can be overridden because NRSC occasionally changes the
API gateway prefix without changing the response contract.
"""
from __future__ import annotations

import os
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import requests
except ImportError:  # dependency is only needed when acquisition is actually run
    requests = None


class BhoonidhiError(RuntimeError):
    """Base error raised for authentication, catalog, or download failures."""


class DelayedProductError(BhoonidhiError):
    """Raised when a catalog item is available but not online (``Online=N``)."""


@dataclass
class _Token:
    value: str
    expires_at: float


def _first(data: Dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in data and data[name] not in (None, ""):
            return data[name]
    return default


class BhoonidhiClient:
    """Authenticated Bhoonidhi catalog/download client.

    The defaults mirror the public ``bhoonidhi-api`` OpenAPI gateway.  Set
    ``BHOONIDHI_API_BASE`` or the individual endpoint variables when the portal
    publishes a gateway revision.  Credentials are read only from the process
    environment (``python-dotenv`` may be used by the caller for a local,
    ignored ``.env`` file).
    """

    def __init__(self, session: Optional[Any] = None) -> None:
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        except ImportError:
            pass
            
        self.user = os.getenv("BHOONIDHI_USER")
        self.password = os.getenv("BHOONIDHI_PASS")
        if not self.user or not self.password:
            raise BhoonidhiError(
                "BHOONIDHI_USER and BHOONIDHI_PASS must be set before acquisition; "
                "register manually at https://bhoonidhi.nrsc.gov.in/bhoonidhi/registration.html"
            )
        base = os.getenv("BHOONIDHI_API_BASE", "https://bhoonidhi.nrsc.gov.in/bhoonidhi-api").rstrip("/")
        self.auth_url = os.getenv("BHOONIDHI_AUTH_URL", f"{base}/auth/token")
        self.search_url = os.getenv("BHOONIDHI_SEARCH_URL", f"{base}/search")
        self.download_url_template = os.getenv("BHOONIDHI_DOWNLOAD_URL", f"{base}/download/{{scene_id}}")
        if session is None and requests is None:
            raise BhoonidhiError("The acquisition environment is missing the 'requests' package")
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/json", "User-Agent": "TerreX-Bhoonidhi/1.0"})
        self._token: Optional[_Token] = None
        self._last_search: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _backoff(attempt: int) -> None:
        time.sleep(min(30.0, 2.0 ** attempt))

    def authenticate(self) -> str:
        """Authenticate once, retrying 429 responses with exponential backoff."""
        payload_variants = (
            {"userId": self.user, "password": self.password},
            {"username": self.user, "password": self.password},
        )
        last_error: Optional[str] = None
        for payload in payload_variants:
            for attempt in range(4):
                response = self.session.post(self.auth_url, json=payload, timeout=60)
                if response.status_code == 429:
                    self._backoff(attempt)
                    continue
                if response.status_code in (400, 401) and payload is payload_variants[0]:
                    last_error = response.text[:300]
                    break
                if not response.ok:
                    raise BhoonidhiError(f"Bhoonidhi authentication failed ({response.status_code}): {response.text[:300]}")
                body = response.json() if response.content else {}
                token = _first(body, "access_token", "accessToken", "token", default=None)
                if isinstance(body.get("data"), dict):
                    token = token or _first(body["data"], "access_token", "accessToken", "token")
                if not token:
                    raise BhoonidhiError("Bhoonidhi authentication response did not contain an access token")
                expires = float(_first(body, "expires_in", "expiresIn", default=3600) or 3600)
                self._token = _Token(str(token), time.time() + max(60.0, expires - 60.0))
                self.session.headers.update({"Authorization": f"Bearer {token}"})
                return str(token)
        raise BhoonidhiError(f"Bhoonidhi authentication rejected the supplied account: {last_error or 'unknown error'}")

    def _ensure_token(self) -> None:
        if self._token is None or time.time() >= self._token.expires_at:
            self.authenticate()

    @staticmethod
    def _items(body: Any) -> Iterable[Dict[str, Any]]:
        if isinstance(body, list):
            return (item for item in body if isinstance(item, dict))
        if not isinstance(body, dict):
            return ()
        for key in ("results", "items", "scenes", "products", "data"):
            value = body.get(key)
            if isinstance(value, list):
                return (item for item in value if isinstance(item, dict))
            if isinstance(value, dict):
                nested = BhoonidhiClient._items(value)
                if nested:
                    return nested
        return ()

    @staticmethod
    def _normalise_scene(raw: Dict[str, Any], requested_bbox: List[float]) -> Dict[str, Any]:
        bbox = _first(raw, "bbox", "boundingBox", "footprint", "geometry", default=requested_bbox)
        if isinstance(bbox, dict):
            coords = bbox.get("coordinates")
            flat = [p for ring in coords or [] for p in (ring if isinstance(ring, list) else [])]
            if flat and isinstance(flat[0], list):
                pts = [p for p in flat if isinstance(p, list) and len(p) >= 2]
                bbox = [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)]
        if not isinstance(bbox, list) or len(bbox) != 4:
            bbox = requested_bbox
        date = _first(raw, "acquisition_date", "acquisitionDate", "date", "sensingDate", "startTime")
        if isinstance(date, str):
            date = date[:10]
        online = str(_first(raw, "Online", "online", "online_status", "onlineStatus", default="N")).upper()
        scene_id = str(_first(raw, "scene_id", "sceneId", "productId", "id", "catalogId", default=""))
        scene = {
            "scene_id": scene_id,
            "acquisition_date": date,
            "online_status": "Y" if online in {"Y", "YES", "TRUE", "1"} else "N",
            "resolution": float(_first(raw, "resolution_m", "resolution", "spatialResolution", default=0) or 0),
            "cloud_cover": _first(raw, "cloud_cover", "cloudCover", "cloudCoverPercent", "cloud_percent"),
            "footprint": bbox,
            "bbox": bbox,
            "satellite": str(_first(raw, "satellite", "platform", "spacecraft", default="")),
            "sensor": str(_first(raw, "sensor", "instrument", "payload", default="")),
            "underlying_dataset": str(_first(raw, "underlying_dataset", "dataset", "productType", default="")),
            "raw": raw,
        }
        return scene

    def search(
        self,
        bbox: List[float],
        start_date: str,
        end_date: str,
        satellite: str,
        sensor: str,
        cloud_cover_max: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        self._ensure_token()
        params: Dict[str, Any] = {
            "minLon": bbox[0], "minLat": bbox[1], "maxLon": bbox[2], "maxLat": bbox[3],
            "startDate": start_date, "endDate": end_date, "satellite": satellite, "sensor": sensor,
        }
        if cloud_cover_max is not None:
            params["cloudCoverMax"] = cloud_cover_max
        for attempt in range(2):
            response = self.session.get(self.search_url, params=params, timeout=90)
            if response.status_code in (404, 405):
                response = self.session.post(self.search_url, json=params, timeout=90)
            if response.status_code == 401 and attempt == 0:
                self._token = None
                self._ensure_token()
                continue
            if response.status_code == 429:
                self._backoff(attempt)
                continue
            if not response.ok:
                raise BhoonidhiError(f"Bhoonidhi search failed ({response.status_code}): {response.text[:300]}")
            scenes = [self._normalise_scene(item, bbox) for item in self._items(response.json())]
            for scene in scenes:
                self._last_search[scene["scene_id"]] = scene
            return scenes
        raise BhoonidhiError("Bhoonidhi search rate limit was not cleared after retries")

    def download(self, scene_id: str, dest_path: Path) -> Path:
        scene = self._last_search.get(scene_id)
        if scene is None:
            raise BhoonidhiError(f"Scene {scene_id} was not returned by a Bhoonidhi search; refusing an unverified download")
        if scene.get("online_status") != "Y":
            raise DelayedProductError(f"Scene {scene_id} is available but delayed (Online=N); order it manually")
        self._ensure_token()
        url = self.download_url_template.format(scene_id=scene_id)
        for attempt in range(2):
            response = self.session.get(url, stream=True, timeout=300)
            if response.status_code in (404, 405):
                response = self.session.post(self.download_url_template.split("/{scene_id}")[0], json={"sceneId": scene_id}, stream=True, timeout=300)
            if response.status_code == 401 and attempt == 0:
                self._token = None
                self._ensure_token()
                continue
            if response.status_code == 429:
                self._backoff(attempt)
                continue
            if not response.ok:
                raise BhoonidhiError(f"Bhoonidhi download failed for {scene_id} ({response.status_code}): {response.text[:300]}")
            content_type = str(getattr(response, "headers", {}).get("Content-Type", "")).lower()
            if "json" in content_type:
                raise BhoonidhiError(f"Bhoonidhi returned a JSON error payload for {scene_id}: {response.text[:300]}")
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = dest_path.with_suffix(dest_path.suffix + ".download")
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
            if zipfile.is_zipfile(temporary):
                with zipfile.ZipFile(temporary) as archive:
                    tif_members = [name for name in archive.namelist() if name.lower().endswith((".tif", ".tiff"))]
                    if not tif_members:
                        raise BhoonidhiError(f"Bhoonidhi download for {scene_id} was a ZIP without a GeoTIFF")
                    with archive.open(tif_members[0]) as source, dest_path.open("wb") as target:
                        target.write(source.read())
                temporary.unlink(missing_ok=True)
            else:
                temporary.replace(dest_path)
            return dest_path
        raise BhoonidhiError(f"Bhoonidhi download rate limit was not cleared for {scene_id}")


def download_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()
