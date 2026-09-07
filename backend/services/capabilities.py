"""Auditable mapping of the six mandatory PS capabilities to live code paths."""

CAPABILITIES = [
    {
        "id": "2.2.1",
        "name": "Semantic and Multimodal Retrieval",
        "status": "implemented",
        "evidence": ["POST /api/search/text", "POST /api/search/image", "AOI/date/sensor filters", "Qdrant ranking"],
    },
    {
        "id": "2.2.2",
        "name": "Multi-Temporal Change Analysis",
        "status": "implemented",
        "evidence": ["GET/POST /api/change/detect", "Prithvi feature differencing", "four change classes", "earliest supported observation"],
    },
    {
        "id": "2.2.3",
        "name": "False-Alarm Suppression and Quality Handling",
        "status": "implemented",
        "evidence": ["cloud/haze/quality masks", "registration checks", "radiometric normalization", "temporal consistency"],
    },
    {
        "id": "2.2.4",
        "name": "Discovery and Clustering",
        "status": "implemented",
        "evidence": ["GET /api/discovery", "embedding-based clustering", "reference-tile ranking"],
    },
    {
        "id": "2.2.5",
        "name": "Analyst Workflow and Provenance",
        "status": "implemented",
        "evidence": ["review queue", "POST /api/feedback", "audit persistence", "GeoJSON/CSV/report/evidence exports"],
    },
    {
        "id": "2.2.6",
        "name": "Scale, Incremental Ingestion and Sovereignty",
        "status": "implemented",
        "evidence": ["POST /api/ingest/process-incoming", "GeoTIFF/COG ingestion", "local PostGIS/Qdrant", "offline mode"],
    },
]
