# TerreX acquisition scripts

TerreX acquisition is a pre-demo, networked phase that uses the official
Bhoonidhi API only. The FastAPI runtime remains air-gapped and never imports
these modules.

1. Complete the one-time human registration described in `docs/bhoonidhi_setup.md`.
2. Set `BHOONIDHI_USER` and `BHOONIDHI_PASS` locally.
3. Run `python scripts/acquire_all.py` from the repository root.
4. Validate with `python scripts/validate_provenance.py`.
5. Run the normal ingestion endpoint or `scripts/ingest.py` after validation.

The scripts use the fixed Kolkata AOI `[88.40, 22.56, 88.48, 22.60]`, search
the requested date windows, accept only `Online=Y` products, record delayed
`Online=N` products, and write a strict `.provenance.json` sidecar immediately
after each download. Missing coverage is reported as a gap; no alternate
commercial or Google imagery is substituted.
