import time
from gliner import GLiNER

t0 = time.perf_counter()
print("Loading GLiNER small model...")
model = GLiNER.from_pretrained("urchade/gliner_small-v2.1")
print(f"Model loaded in {time.perf_counter()-t0:.2f}s")

queries = [
    "New buildings near Hooghly river in Kolkata after 2024 with cloud < 10% on Sentinel-2",
    "Flooded agricultural land in Rajarhat Action Area on Sentinel-1 SAR since September 2024",
    "Dense urban expansion along EM Bypass in Salt Lake Sector 5",
]
labels = ["visual subject", "location", "satellite sensor", "date range", "cloud cover threshold", "distance"]

for q in queries:
    t1 = time.perf_counter()
    entities = model.predict_entities(q, labels, threshold=0.3)
    elapsed_ms = (time.perf_counter() - t1) * 1000
    print(f"\nQuery: '{q}' ({elapsed_ms:.1f} ms)")
    for e in entities:
        print(f"  -> [{e['label']}] '{e['text']}' (score: {e['score']:.2f})")
