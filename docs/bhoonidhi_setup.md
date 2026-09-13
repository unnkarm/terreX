# Bhoonidhi setup

TerreX acquires imagery before an air-gapped demo. Register once at
https://bhoonidhi.nrsc.gov.in/bhoonidhi/registration.html, accept the End User
Licence Agreement, and verify that the account can search and download an
`Online=Y` product. Account creation, CAPTCHA handling, and EULA acceptance are
deliberately human steps and are not automated.

Set credentials only in the local process environment (or the ignored root
`.env` file):

```powershell
$env:BHOONIDHI_USER = "your-user-id"
$env:BHOONIDHI_PASS = "your-password"
```

Optional endpoint overrides are available as `BHOONIDHI_API_BASE`,
`BHOONIDHI_AUTH_URL`, `BHOONIDHI_SEARCH_URL`, and `BHOONIDHI_DOWNLOAD_URL` if
NRSC changes the gateway prefix. Never commit credentials, tokens, or `.env`.

The client targets the public API gateway at `/bhoonidhi-api`, authenticates
with `POST /auth/token`, searches with the AOI/date/platform/instrument fields
(`minLon`, `minLat`, `maxLon`, `maxLat`, `startDate`, `endDate`, `satellite`,
`sensor`, and optional `cloudCoverMax`), and downloads by scene id. The endpoint
variables make a gateway revision explicit rather than silently guessing.

Run acquisition from the repository root with `python scripts/acquire_all.py`.
The script authenticates once, reuses the token, backs off on HTTP 429, records
`Online=N` products as delayed, and writes a provenance sidecar beside every
downloaded GeoTIFF.
