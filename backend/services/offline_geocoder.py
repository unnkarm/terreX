import json
import logging
import math
import re
import difflib
from pathlib import Path
from typing import Optional, Any, Dict, List, Tuple
from shapely.geometry import shape

from config import settings

logger = logging.getLogger("terrex.offline_geocoder")

# Comprehensive offline gazetteer of landmarks, neighborhoods, and geographic points of interest
GAZETTEER_POINTS: List[Dict[str, Any]] = [
    # --- Central Kolkata ---
    {
        "name": "Esplanade",
        "zone": "Central Kolkata",
        "lon": 88.3526,
        "lat": 22.5645,
        "feature_type": "commercial_transit",
        "keywords": ["esplanade", "dharmatala", "curzon park", "lenin sarani", "chowringhee north"],
    },
    {
        "name": "BBD Bagh / Dalhousie",
        "zone": "Central Kolkata",
        "lon": 88.3490,
        "lat": 22.5728,
        "feature_type": "civic_commercial",
        "keywords": ["bbd bagh", "dalhousie", "writers building", "lal dighi", "governor house", "gpo"],
    },
    {
        "name": "Maidan / Victoria Memorial",
        "zone": "Central Kolkata",
        "lon": 88.3426,
        "lat": 22.5448,
        "feature_type": "civic_park",
        "keywords": ["maidan", "victoria memorial", "brigade parade", "race course", "st paul cathedral", "red road"],
    },
    {
        "name": "Park Street / Chowringhee",
        "zone": "Central Kolkata",
        "lon": 88.3540,
        "lat": 22.5510,
        "feature_type": "commercial_hub",
        "keywords": ["park street", "chowringhee", "camac street", "russell street", "flurys", "middleton row"],
    },
    {
        "name": "College Street / Bowbazar",
        "zone": "Central Kolkata",
        "lon": 88.3650,
        "lat": 22.5740,
        "feature_type": "academic_commercial",
        "keywords": ["college street", "bowbazar", "presidency", "calcutta university", "bhatpara", "medical college"],
    },
    {
        "name": "Sealdah Station Area",
        "zone": "Central Kolkata",
        "lon": 88.3715,
        "lat": 22.5670,
        "feature_type": "railway_transit",
        "keywords": ["sealdah", "baithakkhana", "entally", "moulali", "sealdah station", "apc road"],
    },
    {
        "name": "Chandni Chowk / Dharmatala",
        "zone": "Central Kolkata",
        "lon": 88.3565,
        "lat": 22.5675,
        "feature_type": "commercial_market",
        "keywords": ["chandni chowk", "ganesh chandra avenue", "e-mall", "bentinck street"],
    },
    {
        "name": "Babu Ghat / Strand Road",
        "zone": "Central Kolkata",
        "lon": 88.3410,
        "lat": 22.5680,
        "feature_type": "waterfront",
        "keywords": ["babu ghat", "strand road", "millennium park", "eden gardens", "hooghly ghat"],
    },
    {
        "name": "Princep Ghat Waterfront",
        "zone": "Central Kolkata",
        "lon": 88.3325,
        "lat": 22.5560,
        "feature_type": "waterfront",
        "keywords": ["princep ghat", "waterfront", "vidyasagar setu approach", "fort william west"],
    },
    {
        "name": "Burrabazar Commercial Core",
        "zone": "Central Kolkata",
        "lon": 88.3530,
        "lat": 22.5830,
        "feature_type": "commercial_dense",
        "keywords": ["burrabazar", "barabazar", "postabazar", "mg road", "canning street", "mehta building"],
    },

    # --- North Kolkata & North 24 Parganas ---
    {
        "name": "Shyambazar Five-Point",
        "zone": "North Kolkata",
        "lon": 88.3705,
        "lat": 22.6025,
        "feature_type": "transit_hub",
        "keywords": ["shyambazar", "hatibagan", "bhupen bose ave", "five point crossing"],
    },
    {
        "name": "Sovabazar / Bagbazar Ghat",
        "zone": "North Kolkata",
        "lon": 88.3620,
        "lat": 22.6010,
        "feature_type": "heritage_waterfront",
        "keywords": ["sovabazar", "bagbazar", "rajbari", "kumartuli", "ahiritola ghat"],
    },
    {
        "name": "Maniktala / Phoolbagan",
        "zone": "North Kolkata",
        "lon": 88.3780,
        "lat": 22.5840,
        "feature_type": "residential_commercial",
        "keywords": ["maniktala", "phoolbagan", "kankurgachi", "vivekananda road"],
    },
    {
        "name": "Ultadanga / VIP Road",
        "zone": "North Kolkata",
        "lon": 88.3970,
        "lat": 22.5960,
        "feature_type": "transit_junction",
        "keywords": ["ultadanga", "hudco", "vip road", "bidhan nagar station", "gouribari"],
    },
    {
        "name": "Dum Dum / Nagerbazar",
        "zone": "North 24 Parganas",
        "lon": 88.4200,
        "lat": 22.6280,
        "feature_type": "residential_transit",
        "keywords": ["dum dum", "nagerbazar", "dum dum cantonment", "jessore road"],
    },
    {
        "name": "NSCBI Airport (Kolkata)",
        "zone": "North 24 Parganas",
        "lon": 88.4470,
        "lat": 22.6530,
        "feature_type": "airport_runway",
        "keywords": ["airport", "nscbi", "netaji subhash chandra bose", "ccu", "airfield", "runway"],
    },
    {
        "name": "Dakshineswar Temple Reach",
        "zone": "North 24 Parganas",
        "lon": 88.3580,
        "lat": 22.6550,
        "feature_type": "waterfront_religious",
        "keywords": ["dakshineswar", "kali temple", "vivekananda setu", "nivedita setu", "skywalk"],
    },
    {
        "name": "Belgharia / Agarpara",
        "zone": "North 24 Parganas",
        "lon": 88.3850,
        "lat": 22.6650,
        "feature_type": "residential_urban",
        "keywords": ["belgharia", "agarpara", "rathtala", "bt road"],
    },
    {
        "name": "Sodepur / Khardaha",
        "zone": "North 24 Parganas",
        "lon": 88.3800,
        "lat": 22.7000,
        "feature_type": "residential_urban",
        "keywords": ["sodepur", "khardaha", "bt road north", "ghola"],
    },
    {
        "name": "Barrackpore Cantonment",
        "zone": "North 24 Parganas",
        "lon": 88.3770,
        "lat": 22.7630,
        "feature_type": "military_urban",
        "keywords": ["barrackpore", "cantonment", "latbagan", "barrackpore air force"],
    },

    # --- South Kolkata & South 24 Parganas ---
    {
        "name": "Ballygunge / Gariahat",
        "zone": "South Kolkata",
        "lon": 88.3640,
        "lat": 22.5200,
        "feature_type": "commercial_residential",
        "keywords": ["ballygunge", "gariahat", "golpark", "rashbehari", "pantaloons", "ballygunge circular"],
    },
    {
        "name": "Alipore / Majerhat",
        "zone": "South Kolkata",
        "lon": 88.3320,
        "lat": 22.5320,
        "feature_type": "civic_residential",
        "keywords": ["alipore", "zoo", "national library", "majerhat", "command hospital", "woodlands"],
    },
    {
        "name": "Bhawanipore / Kalighat",
        "zone": "South Kolkata",
        "lon": 88.3480,
        "lat": 22.5260,
        "feature_type": "heritage_residential",
        "keywords": ["bhawanipore", "kalighat", "hazra", "harish mukherjee", "temple"],
    },
    {
        "name": "Dhakuria / Lake Gardens",
        "zone": "South Kolkata",
        "lon": 88.3620,
        "lat": 22.5080,
        "feature_type": "residential_urban",
        "keywords": ["dhakuria", "lake gardens", "lords more", "selimpur"],
    },
    {
        "name": "Rabindra Sarobar / Southern Ave",
        "zone": "South Kolkata",
        "lon": 88.3540,
        "lat": 22.5120,
        "feature_type": "urban_lake_park",
        "keywords": ["rabindra sarobar", "dhakuria lake", "southern avenue", "menoka", "lake stadium"],
    },
    {
        "name": "Jadavpur / Prince Anwar Shah",
        "zone": "South Kolkata",
        "lon": 88.3680,
        "lat": 22.4980,
        "feature_type": "academic_commercial",
        "keywords": ["jadavpur", "university", "south city", "prince anwar shah", "8b bus stand"],
    },
    {
        "name": "Tollygunge / Kudghat",
        "zone": "South Kolkata",
        "lon": 88.3450,
        "lat": 22.4880,
        "feature_type": "residential_urban",
        "keywords": ["tollygunge", "mahanayak uttam kumar", "kudghat", "karunamoyee south", "golf club"],
    },
    {
        "name": "Garia / Patuli",
        "zone": "South Kolkata",
        "lon": 88.3840,
        "lat": 22.4690,
        "feature_type": "residential_waterfront",
        "keywords": ["garia", "patuli", "floating market", "kavi subhash", "garia more"],
    },
    {
        "name": "Ruby / Kasba EM Bypass",
        "zone": "South Kolkata",
        "lon": 88.3990,
        "lat": 22.5130,
        "feature_type": "commercial_medical",
        "keywords": ["ruby", "kasba", "anandapur", "em bypass south", "desun", "acropolis"],
    },
    {
        "name": "Science City / Topsia",
        "zone": "South Kolkata",
        "lon": 88.3950,
        "lat": 22.5400,
        "feature_type": "civic_exhibition",
        "keywords": ["science city", "topsia", "park circus connector", "milan mela", "jw marriott"],
    },
    {
        "name": "Park Circus / Tangra",
        "zone": "South Kolkata",
        "lon": 88.3760,
        "lat": 22.5410,
        "feature_type": "commercial_dining",
        "keywords": ["park circus", "tangra", "chinatown", "bridge no 4", "quest mall", "syed amir ali"],
    },
    {
        "name": "Behala / Taratala Industrial",
        "zone": "South Kolkata",
        "lon": 88.3180,
        "lat": 22.5020,
        "feature_type": "industrial_residential",
        "keywords": ["behala", "taratala", "diamond harbour road", "chowrasta", "behala tram depot"],
    },
    {
        "name": "Khidirpur / Port Docks",
        "zone": "South Kolkata",
        "lon": 88.3120,
        "lat": 22.5400,
        "feature_type": "port_maritime",
        "keywords": ["khidirpur", "garden reach", "netaji subhash dock", "port", "grse", "kpd"],
    },

    # --- East Kolkata & IT Corridor (Bidhannagar / New Town) ---
    {
        "name": "Salt Lake Sector 5",
        "zone": "Bidhannagar / IT Corridor",
        "lon": 88.4300,
        "lat": 22.5775,
        "bbox": [88.415, 22.565, 88.445, 22.590],
        "feature_type": "it_commercial_hub",
        "keywords": ["salt lake sector 5", "salt lake sector v", "sector 5", "sector v", "wipro", "tcs gitanjali park", "technopolis", "it hub", "ring road", "webel bhavan", "sdf building", "college more"],
    },
    {
        "name": "New Town / Rajarhat",
        "zone": "New Town Rajarhat",
        "lon": 88.4775,
        "lat": 22.6000,
        "bbox": [88.455, 22.575, 88.500, 22.625],
        "feature_type": "planned_smart_city",
        "keywords": ["new town", "rajarhat", "new town rajarhat", "action area 1", "action area 2", "action area 3", "biswa bangla", "biswa bangla gate", "eco park", "city centre 2", "chinar park", "shapoorji", "unitech infospace"],
    },
    {
        "name": "Salt Lake Sector I & II",
        "zone": "Bidhannagar",
        "lon": 88.4100,
        "lat": 22.5850,
        "feature_type": "planned_residential",
        "keywords": ["salt lake", "bidhannagar", "city centre 1", "karunamoyee", "central park", "salt lake stadium"],
    },
    {
        "name": "Salt Lake Sector V (Tech Hub)",
        "zone": "Bidhannagar",
        "lon": 88.4330,
        "lat": 22.5740,
        "bbox": [88.415, 22.565, 88.445, 22.590],
        "feature_type": "it_commercial",
        "keywords": ["sector v", "sector 5", "salt lake sector 5", "wipro", "tcs gitobitan", "technopolis", "it hub", "ring road"],
    },
    {
        "name": "New Town Action Area I",
        "zone": "New Town Rajarhat",
        "lon": 88.4600,
        "lat": 22.5850,
        "feature_type": "planned_urban",
        "keywords": ["new town", "action area 1", "axis mall", "nazrul tirtha", "novotel", "major arterial road"],
    },
    {
        "name": "Biswa Bangla Gate & Eco Park",
        "zone": "New Town Rajarhat",
        "lon": 88.4680,
        "lat": 22.5850,
        "feature_type": "civic_landmark",
        "keywords": ["biswa bangla", "biswa bangla gate", "action area 2", "eco park", "mother wax museum", "convention centre"],
    },
    {
        "name": "New Town Action Area III",
        "zone": "New Town Rajarhat",
        "lon": 88.4850,
        "lat": 22.5680,
        "feature_type": "it_residential",
        "keywords": ["action area 3", "unitech", "infospace", "shapoorji", "downtown new town"],
    },
    {
        "name": "Rajarhat Main / Chinar Park",
        "zone": "New Town Rajarhat",
        "lon": 88.4480,
        "lat": 22.6200,
        "feature_type": "commercial_residential",
        "keywords": ["rajarhat", "chinar park", "city centre 2", "atghara", "rajarhat chowmatha"],
    },
    {
        "name": "East Kolkata Wetlands",
        "zone": "Ramsar Conservation Site",
        "lon": 88.4500,
        "lat": 22.5200,
        "feature_type": "wetland_conservation",
        "keywords": ["wetlands", "east kolkata wetlands", "bhery", "sewage fisheries", "ramsar site", "dhapa"],
    },

    # --- Howrah & West Bank ---
    {
        "name": "Howrah (central)",
        "zone": "Howrah District",
        "lon": 88.3150,
        "lat": 22.5850,
        "bbox": [88.28, 22.55, 88.35, 22.62],
        "feature_type": "industrial_transit_core",
        "keywords": ["howrah", "howrah central", "howrah station", "shibpur", "santragachi", "kadamtala", "kona expressway", "nabanna", "vidyasagar setu west"],
    },
    {
        "name": "Howrah Railway Terminus",
        "zone": "Howrah",
        "lon": 88.3430,
        "lat": 22.5830,
        "bbox": [88.28, 22.55, 88.35, 22.62],
        "feature_type": "railway_terminal",
        "keywords": ["howrah station", "howrah junction", "railway terminus", "howrah ghat", "yatri niwas"],
    },
    {
        "name": "Howrah Bridge (Rabindra Setu)",
        "zone": "Howrah",
        "lon": 88.3470,
        "lat": 22.5850,
        "feature_type": "bridge_infrastructure",
        "keywords": ["howrah bridge", "rabindra setu", "cantilever bridge"],
    },
    {
        "name": "Vidyasagar Setu Corridor",
        "zone": "Howrah / Kolkata",
        "lon": 88.3310,
        "lat": 22.5560,
        "feature_type": "bridge_highway",
        "keywords": ["vidyasagar setu", "toll plaza", "second hooghly bridge", "nabanna approach"],
    },
    {
        "name": "Shibpur / Botanical Garden / IIEST",
        "zone": "Howrah",
        "lon": 88.3120,
        "lat": 22.5550,
        "bbox": [88.28, 22.55, 88.35, 22.62],
        "feature_type": "park_academic",
        "keywords": ["shibpur", "botanical garden", "iiest", "great banyan tree", "shalimar", "nabanna"],
    },
    {
        "name": "Santragachi Bus & Rail Terminal",
        "zone": "Howrah",
        "lon": 88.2780,
        "lat": 22.5800,
        "bbox": [88.28, 22.55, 88.35, 22.62],
        "feature_type": "transit_terminal",
        "keywords": ["santragachi", "santragachi jheel", "kona expressway", "santragachi station"],
    },
    {
        "name": "Belur Math / Bally",
        "zone": "Howrah",
        "lon": 88.3550,
        "lat": 22.6320,
        "feature_type": "heritage_waterfront",
        "keywords": ["belur math", "bally", "ramakrishna mission", "bally bridge"],
    },
    {
        "name": "Uttarpara / Hindmotor",
        "zone": "Hooghly",
        "lon": 88.3440,
        "lat": 22.6680,
        "feature_type": "industrial_residential",
        "keywords": ["uttarpara", "hindmotor", "kotrung", "ambassador factory"],
    },

    # --- Hooghly Reach ---
    {
        "name": "Serampore Historic Town",
        "zone": "Hooghly",
        "lon": 88.3450,
        "lat": 22.7500,
        "feature_type": "heritage_town",
        "keywords": ["serampore", "rishra", "danish town", "serampore college"],
    },
    {
        "name": "Chandannagar Waterfront",
        "zone": "Hooghly",
        "lon": 88.3680,
        "lat": 22.8680,
        "feature_type": "heritage_waterfront",
        "keywords": ["chandannagar", "strand", "french colony", "dupleix museum"],
    },
    {
        "name": "Chinsurah / Bandel / Hooghly",
        "zone": "Hooghly",
        "lon": 88.3840,
        "lat": 22.9230,
        "feature_type": "heritage_railway",
        "keywords": ["bandel", "chinsurah", "hooghly imambara", "jubilee bridge", "bandel church"],
    },

    # --- Outlying Districts within Scene Coverage ---
    {
        "name": "Baruipur South 24 Pgs",
        "zone": "South 24 Parganas",
        "lon": 88.4350,
        "lat": 22.3650,
        "feature_type": "district_hq",
        "keywords": ["baruipur", "padmapukur", "south 24 parganas"],
    },
    {
        "name": "Barasat District HQ",
        "zone": "North 24 Parganas",
        "lon": 88.4800,
        "lat": 22.7200,
        "feature_type": "district_hq",
        "keywords": ["barasat", "champadali", "dakbangla", "north 24 parganas"],
    },
    {
        "name": "Habra / Ashoknagar",
        "zone": "North 24 Parganas",
        "lon": 88.6300,
        "lat": 22.8350,
        "feature_type": "semi_urban",
        "keywords": ["habra", "ashoknagar", "jessore road east"],
    },
    {
        "name": "Kalyani AIIMS / Nadia",
        "zone": "Nadia",
        "lon": 88.4400,
        "lat": 22.9750,
        "feature_type": "planned_academic",
        "keywords": ["kalyani", "aiims kalyani", "kalyani expressway", "nadia"],
    },
    {
        "name": "Ranaghat / Chakdaha",
        "zone": "Nadia",
        "lon": 88.5800,
        "lat": 23.1800,
        "feature_type": "semi_urban",
        "keywords": ["ranaghat", "chakdaha", "churni river"],
    },
    {
        "name": "Krishnanagar / Nadia HQ",
        "zone": "Nadia",
        "lon": 88.5000,
        "lat": 23.4000,
        "feature_type": "district_hq",
        "keywords": ["krishnanagar", "ghurni", "dhubulia", "jalangi"],
    },
    {
        "name": "Bardhaman City / Damodar",
        "zone": "Purba Bardhaman",
        "lon": 87.8600,
        "lat": 23.2400,
        "feature_type": "district_city",
        "keywords": ["bardhaman", "burdwan", "damodar", "curzon gate"],
    },
    {
        "name": "Kharagpur / IIT Campus",
        "zone": "Paschim Medinipur",
        "lon": 87.3200,
        "lat": 22.3400,
        "feature_type": "academic_railway",
        "keywords": ["kharagpur", "iit", "medinipur", "midnapore"],
    },
    {
        "name": "Diamond Harbour / Estuary",
        "zone": "South 24 Parganas",
        "lon": 88.1900,
        "lat": 22.1900,
        "feature_type": "estuary_port",
        "keywords": ["diamond harbour", "falta", "estuary", "hooghly mouth"],
    },
    {
        "name": "Canning / Sundarbans Gateway",
        "zone": "South 24 Parganas",
        "lon": 88.6650,
        "lat": 22.3120,
        "feature_type": "river_gateway",
        "keywords": ["canning", "matla river", "sundarbans gateway"],
    },
    {
        "name": "Sundarbans Biosphere",
        "zone": "Sundarbans",
        "lon": 88.8500,
        "lat": 21.9500,
        "feature_type": "mangrove_delta",
        "keywords": ["sundarbans", "delta", "mangrove", "gosaba", "sajnekhali"],
    },

    # --- National Fallback POIs ---
    {
        "name": "Delhi NCR (Yamuna Basin)",
        "zone": "National Capital Region",
        "lon": 77.2090,
        "lat": 28.6139,
        "feature_type": "capital_metro",
        "keywords": ["delhi", "new delhi", "yamuna", "connaught place", "ncr"],
    },
]


def _haversine_km(lon0: float, lat0: float, lon1: float, lat1: float) -> float:
    R = 6371.0
    dlat = math.radians(lat1 - lat0)
    dlon = math.radians(lon1 - lon0)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat0)) * math.cos(math.radians(lat1)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _compass_direction(lon0: float, lat0: float, lon1: float, lat1: float) -> str:
    dlon = math.radians(lon1 - lon0)
    y = math.sin(dlon) * math.cos(math.radians(lat1))
    x = math.cos(math.radians(lat0)) * math.sin(math.radians(lat1)) - math.sin(math.radians(lat0)) * math.cos(math.radians(lat1)) * math.cos(dlon)
    bearing_deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"]
    return dirs[int((bearing_deg + 22.5) // 45)]


class OfflineGeocoder:
    """
    Provides fully offline forward-geocoding and reverse-geocoding by matching
    coordinates and query terms against the local gazetteer and GeoJSON features.
    """

    def __init__(self):
        self.gazetteer_path = settings.DATA_DIR / "gazetteer.geojson"
        self._features: Dict[str, Any] = {}
        self._landmarks = GAZETTEER_POINTS
        self.reload()

    def reload(self):
        self._features = {}
        if self.gazetteer_path.exists():
            try:
                with open(self.gazetteer_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    features = data.get("features", [])
                    for feat in features:
                        props = feat.get("properties", {})
                        name = props.get("name")
                        if name and "geometry" in feat:
                            self._features[name.lower().strip()] = feat
                logger.info(f"Loaded {len(self._features)} offline geographical features from {self.gazetteer_path.name}")
            except Exception as e:
                logger.error(f"Failed to load {self.gazetteer_path.name}: {e}")

    def geocode(self, location_name: str) -> Optional[Dict[str, Any]]:
        """
        Fuzzy match the location name against known landmarks and features.
        Supports spaceless queries (e.g. 'newtown', 'saltlake', 'sector5'),
        alias normalization, keyword searches, and GeoJSON shapes.
        """
        if not location_name:
            return None

        query = location_name.lower().strip()
        query_norm = re.sub(r"[^a-z0-9]", "", query) if "re" in globals() else "".join(c for c in query if c.isalnum())

        # Explicit aliases
        ALIASES = {
            "newtown": "New Town / Rajarhat",
            "newtownrajarhat": "New Town / Rajarhat",
            "rajarhat": "New Town / Rajarhat",
            "saltlake": "Salt Lake Sector 5",
            "saltlakesector5": "Salt Lake Sector 5",
            "saltlakesectorv": "Salt Lake Sector 5",
            "sector5": "Salt Lake Sector 5",
            "sectorv": "Salt Lake Sector 5",
            "howrah": "Howrah (central)",
            "howrahcentral": "Howrah (central)",
            "howrahstation": "Howrah Railway Terminus",
        }
        if query_norm in ALIASES:
            target_name = ALIASES[query_norm]
            for lm in self._landmarks:
                if lm["name"].lower() == target_name.lower():
                    return lm

        # 1. Exact and normalized keyword matching
        for lm in self._landmarks:
            lm_name_norm = "".join(c for c in lm["name"].lower() if c.isalnum())
            if query == lm["name"].lower() or (query_norm and query_norm == lm_name_norm):
                return lm
            for kw in lm.get("keywords", []):
                kw_lower = kw.lower()
                kw_norm = "".join(c for c in kw_lower if c.isalnum())
                if kw_lower == query or (kw_norm and kw_norm == query_norm):
                    return lm
                if len(kw_lower) > 3 and (kw_lower in query or (kw_norm and len(kw_norm) >= 4 and kw_norm in query_norm)):
                    return lm

        # 2. Fuzzy match landmark names
        names = [lm["name"].lower() for lm in self._landmarks]
        matches = difflib.get_close_matches(query, names, n=1, cutoff=0.7)
        if matches:
            matched_name = matches[0]
            for lm in self._landmarks:
                if lm["name"].lower() == matched_name:
                    return lm

        # 3. Check GeoJSON features
        if self._features:
            feature_keys = list(self._features.keys())
            matches = difflib.get_close_matches(query, feature_keys, n=1, cutoff=0.7)
            if matches:
                feat = self._features[matches[0]]
                return {
                    "name": feat["properties"].get("name"),
                    "geometry": feat["geometry"],
                }

        return None

    def reverse_geocode(self, lon: float, lat: float) -> Dict[str, Any]:
        """
        Calculates great-circle distance to nearest landmark in the gazetteer,
        determines cardinal bearing, and generates a dynamic human-friendly subtitle.
        """
        closest_dist = float("inf")
        closest_lm: Optional[Dict[str, Any]] = None
        closest_dir = "N"

        for lm in self._landmarks:
            dist_km = _haversine_km(lm["lon"], lm["lat"], lon, lat)
            if dist_km < closest_dist:
                closest_dist = dist_km
                closest_lm = lm
                closest_dir = _compass_direction(lm["lon"], lm["lat"], lon, lat)

        if not closest_lm:
            return {
                "name": f"{lat:.4f}°N, {lon:.4f}°E",
                "zone": "Kolkata Region",
                "subtitle": f"{lat:.4f}°N, {lon:.4f}°E",
                "distance_km": 0.0,
                "direction": "N",
                "feature_type": "terrain",
            }

        name = closest_lm["name"]
        zone = closest_lm["zone"]
        ftype = closest_lm.get("feature_type", "urban")

        if closest_dist < 0.5:
            subtitle = f"{name} ({zone})"
        elif closest_dist < 3.5:
            subtitle = f"{name} ({closest_dist:.1f} km {closest_dir})"
        elif closest_dist < 12.0:
            subtitle = f"{name} Area ({closest_dist:.1f} km {closest_dir})"
        else:
            subtitle = f"{zone} ({closest_dist:.0f} km from {name})"

        return {
            "name": name,
            "zone": zone,
            "subtitle": subtitle,
            "distance_km": round(closest_dist, 2),
            "direction": closest_dir,
            "feature_type": ftype,
        }


offline_geocoder = OfflineGeocoder()

