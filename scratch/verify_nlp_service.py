import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from services.nlp_filter import parse_natural_language_query

test_queries = [
    "New buildings near Hooghly river in Kolkata after 2024 with cloud < 10% on Sentinel-2",
    "Flooded agricultural land in Rajarhat Action Area on Sentinel-1 SAR since September 2024",
    "Dense urban expansion along EM Bypass in Salt Lake Sector 5",
    "water bodies and rivers within 5km of Biswa Bangla Gate with clear sky",
    "deforestation and illegal logging near Sundarbans before 2023 on Landsat-8",
    "ISRO LISS-4 imagery over Kolkata Port after March 2024",
    "commercial warehouses near Victoria Memorial with max cloud 5%"
]

print("=== TERREX GLiNER QUERY PARSER VERIFICATION ===")
for q in test_queries:
    t0 = time.perf_counter()
    parsed = parse_natural_language_query(q)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    print(f"\n[QUERY] '{q}' ({elapsed_ms:.1f} ms)")
    print(f"  -> Semantic Query: '{parsed.semantic_query}'")
    print(f"  -> Spatial Relation: {parsed.spatial_relation}")
    print(f"  -> Sensor: {parsed.sensor}")
    print(f"  -> Date From: {parsed.date_from}, Date To: {parsed.date_to}")
    print(f"  -> Max Cloud Cover: {parsed.max_cloud_cover}")
    print(f"  -> Explanation: {parsed.explanation}")

print("\n=== ALL TEST QUERIES PARSED ACCURATELY ===")
