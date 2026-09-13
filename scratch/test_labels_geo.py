import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from gliner import GLiNER
from services.offline_geocoder import offline_geocoder

m = GLiNER.from_pretrained("urchade/gliner_small-v2.1")
queries = [
    "New buildings near Hooghly river in Kolkata after 2024 with cloud < 10% on Sentinel-2",
    "Flooded agricultural land in Rajarhat Action Area on Sentinel-1 SAR since September 2024",
    "Dense urban expansion along EM Bypass in Salt Lake Sector 5",
    "water bodies and rivers within 5km of Biswa Bangla Gate with clear sky",
    "deforestation and illegal logging near Sundarbans before 2023 on Landsat-8",
    "industrial warehouses near Kolkata Port"
]

labels = [
    "visual subject",
    "geographic location or city",
    "satellite sensor",
    "date range",
    "cloud cover threshold"
]

for q in queries:
    ents = m.predict_entities(q, labels, threshold=0.3)
    print(f"\nQuery: {q}")
    for e in ents:
        is_geo = offline_geocoder.geocode(e['text']) is not None
        print(f"  [{e['label']}] '{e['text']}' (score: {e['score']:.2f}, in_geocoder: {is_geo})")
