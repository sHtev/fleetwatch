"""Build realistic York delivery rounds from OpenStreetMap, and save them to data/york_rounds.json.

Run occasionally, not as part of simulations or tests: it calls two free public services
(Overpass for OpenStreetMap data, OSRM for routing), politely and one request at a time.

    uv run python scripts/build_routes.py

Each round starts and ends at a depot on Clifton Moor and visits real addresses in one sector
of the city. OSRM orders the stops (its "trip" service) and gives the road route as OpenStreetMap
node IDs; Overpass then tells us which road each stretch is on, and that road's speed limit.
The public OSRM server's map data is older than Overpass's, so the two don't always agree.

Data © OpenStreetMap contributors, under the Open Database Licence (ODbL).
"""

import argparse
import json
import math
import random
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSRM_URL = "https://router.project-osrm.org/trip/v1/driving/"
USER_AGENT = "fleetwatch-demo/0.1 (personal learning project)"
PAUSE_SECONDS = 2  # between requests to the public servers
RETRY_WAITS_SECONDS = [10, 30, 60]  # when a server says it's busy
BUSY_STATUSES = {429, 502, 503, 504}

DEPOT = (53.9876, -1.1023)  # Clifton Moor industrial estate
CITY_CENTRE = (53.9600, -1.0800)
ADDRESS_RADIUS_METRES = 4500
ROUNDS = ["North", "East", "South", "West"]  # one sector of the city each
STOPS_PER_ROUND = 12
DATA = Path(__file__).parent.parent / "data"
OUTPUT = DATA / "york_rounds.json"
ADDRESS_CACHE = DATA / ".york_addresses.json"  # not committed; delete it to refetch

# UK defaults when OSM has no maxspeed tag. Most York roads are lit urban roads, so 30 mph.
DEFAULT_LIMIT_MPH = {"motorway": 70, "trunk": 60, "primary": 30}
URBAN_DEFAULT_MPH = 30


def bearing_degrees(origin: tuple[float, float], point: tuple[float, float]) -> float:
    """Compass bearing from origin to point: 0 is north, 90 east."""
    dlat = point[0] - origin[0]
    dlon = (point[1] - origin[1]) * math.cos(math.radians(origin[0]))
    return math.degrees(math.atan2(dlon, dlat)) % 360


def sector(point: tuple[float, float]) -> str:
    """North, East, South or West of the city centre."""
    return ROUNDS[int((bearing_degrees(CITY_CENTRE, point) + 45) % 360 // 90)]


def parse_maxspeed(tags: dict[str, str]) -> tuple[int, str, str]:
    """Return (limit_mph, carriageway, source) for an OSM way's tags."""
    highway = tags.get("highway", "")
    dual = tags.get("dual_carriageway") == "yes" or highway == "motorway"
    value = tags.get("maxspeed", "")
    if match := re.fullmatch(r"(\d+) mph", value):
        limit, source = int(match[1]), "osm"
    elif value == "GB:nsl_dual":
        limit, source, dual = 70, "osm", True
    elif value in ("GB:nsl_single", "national"):
        limit, source = (70 if dual else 60), "osm"
    elif value == "GB:motorway":
        limit, source, dual = 70, "osm", True
    elif value.isdigit():  # OSM's default unit is km/h
        limit, source = round(int(value) / 1.609344), "osm"
    else:
        limit, source = DEFAULT_LIMIT_MPH.get(highway, URBAN_DEFAULT_MPH), "default"
    return limit, ("dual" if dual else "single"), source


def polite_request(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
    """One request, pausing afterwards, and backing off if the server is busy."""
    for wait in [*RETRY_WAITS_SECONDS, None]:
        response = client.request(method, url, **kwargs)
        if response.status_code not in BUSY_STATUSES or wait is None:
            break
        print(f"    server busy ({response.status_code}), retrying in {wait} s")
        time.sleep(wait)
    response.raise_for_status()
    time.sleep(PAUSE_SECONDS)
    return response


def overpass(client: httpx.Client, query: str) -> list[dict]:
    response = polite_request(client, "POST", OVERPASS_URL, data={"data": query}, timeout=180)
    return response.json()["elements"]


def fetch_addresses(client: httpx.Client) -> list[dict]:
    """Addresses with a house number and street, as points (buildings give their centre)."""
    if ADDRESS_CACHE.exists():
        return json.loads(ADDRESS_CACHE.read_text())
    lat, lon = CITY_CENTRE
    elements = overpass(
        client,
        f'[out:json][timeout:90];nwr["addr:housenumber"]["addr:street"]'
        f"(around:{ADDRESS_RADIUS_METRES},{lat},{lon});out center tags;",
    )
    addresses = []
    for e in elements:
        point = (e["lat"], e["lon"]) if "lat" in e else (e["center"]["lat"], e["center"]["lon"])
        tags = e["tags"]
        addresses.append(
            {"point": point, "label": tags["addr:street"]}  # street only, not the house
        )
    DATA.mkdir(exist_ok=True)
    ADDRESS_CACHE.write_text(json.dumps(addresses))
    return addresses


def plan_trip(client: httpx.Client, stops: list[dict]) -> tuple[list[dict], list[dict], list[int]]:
    """Ask OSRM for the best order to visit the stops, from and back to the depot.

    Returns the stops in visiting order; one entry per route point, with its position and,
    if OSRM gave it exactly, its OSM node ID; and the route index where each leg ends.
    """
    points = [DEPOT] + [s["point"] for s in stops]
    coordinates = ";".join(f"{lon},{lat}" for lat, lon in points)
    response = polite_request(
        client,
        "GET",
        OSRM_URL + coordinates,
        params={
            "source": "first",
            "roundtrip": "true",
            "overview": "full",
            "geometries": "geojson",
            "annotations": "nodes",
        },
        timeout=60,
    )
    body = response.json()
    if body["code"] != "Ok":
        raise RuntimeError(f"OSRM: {body}")
    trip = body["trips"][0]
    # waypoint_index says where each input point comes in the trip; the depot is first.
    order = sorted(range(len(stops)), key=lambda i: body["waypoints"][i + 1]["waypoint_index"])

    # The geometry has one coordinate per node, and each leg starts on the coordinate the
    # previous leg ended on. OSRM writes node IDs with only 10 significant digits, so newer
    # 11-digit IDs come back as rounded floats (1.103618381e+10) naming a different node:
    # keep only the exact ones.
    geometry = trip["geometry"]["coordinates"]
    route, leg_ends, offset = [], [], 0
    for leg_number, leg in enumerate(trip["legs"]):
        nodes = leg["annotation"]["nodes"]
        skip = 0 if leg_number == 0 else 1  # shared with the previous leg
        for node, (lon, lat) in zip(
            nodes[skip:], geometry[offset + skip : offset + len(nodes)], strict=True
        ):
            route.append({"point": (lat, lon), "node": node if isinstance(node, int) else None})
        offset += len(nodes) - 1
        leg_ends.append(len(route) - 1)
    if len(route) != len(geometry):
        raise RuntimeError(f"Route has {len(route)} points but geometry has {len(geometry)}")
    return [stops[i] for i in order], route, leg_ends


def fetch_roads(client: httpx.Client, node_ids: set[int]) -> dict[tuple[int, int], dict]:
    """The road (OSM way tags) for each pair of neighbouring nodes."""
    ids = ",".join(map(str, sorted(node_ids)))
    elements = overpass(
        client, f"[out:json][timeout:120];node(id:{ids});way(bn)[highway];out body;"
    )
    road_for_pair = {}
    for way in elements:
        for a, b in zip(way["nodes"], way["nodes"][1:], strict=False):
            road_for_pair[(a, b)] = road_for_pair[(b, a)] = way["tags"]
    return road_for_pair


def build_round(client: httpx.Client, name: str, stops: list[dict]) -> dict:
    ordered, route, leg_ends = plan_trip(client, stops)
    road_for_pair = fetch_roads(client, {p["node"] for p in route if p["node"] is not None})

    # Each point carries the limit of the stretch it starts. Where the road can't be identified
    # (an inexact node ID, or a node deleted from OSM since OSRM's map data was built), carry the
    # previous stretch's limit forward: it's nearly always the same road.
    path, carried = [], 0
    previous_fields = (URBAN_DEFAULT_MPH, "single", "default", "")
    for here, after in zip(route, [*route[1:], None], strict=True):
        tags = road_for_pair.get((here["node"], after["node"])) if after else None
        if tags is not None:
            fields = (*parse_maxspeed(tags), tags.get("name", ""))
        else:
            fields = (*previous_fields[:2], "carried", previous_fields[3])
            carried += 1
        lat, lon = here["point"]
        path.append([round(lat, 6), round(lon, 6), *fields])
        previous_fields = fields
    print(f"    {name}: {carried} of {len(path)} stretches carried the previous road's limit")

    return {
        "name": name,
        # The last leg returns to the depot, so it has no stop.
        "stops": [
            {"label": s["label"], "path_index": end}
            for s, end in zip(ordered, leg_ends, strict=False)
        ],
        "path": path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--seed", type=int, default=7, help="which addresses get picked")
    args = parser.parse_args()
    rng = random.Random(args.seed)

    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        addresses = fetch_addresses(client)
        print(f"{len(addresses)} York addresses from OpenStreetMap")
        rounds = []
        for name in ROUNDS:
            candidates = [a for a in addresses if sector(a["point"]) == name]
            stops = rng.sample(candidates, STOPS_PER_ROUND)
            round_ = build_round(client, name, stops)
            from_osm = sum(1 for p in round_["path"] if p[4] == "osm") / len(round_["path"])
            print(
                f"  {name}: {len(round_['path'])} points, {from_osm:.0%} of speed limits from OSM"
            )
            rounds.append(round_)

    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "attribution": "Data © OpenStreetMap contributors (ODbL). Routing by OSRM.",
                "depot": DEPOT,
                "path_fields": ["lat", "lon", "limit_mph", "carriageway", "limit_source", "road"],
                "rounds": rounds,
            },
            indent=1,
        )
    )
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
