"""Drive simulated vans around York and post their telematics to the API.

uv run python scripts/simulate.py                  # 2 hours of history, as fast as possible
uv run python scripts/simulate.py --realtime       # live: one sample every 5 s per van
"""

import argparse
import math
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

SAMPLE_SECONDS = 5
BATCH_SIZE = 60

# Rough points around York, with the speed limit (mph) on the leg *to* each point.
WAYPOINTS = [
    ((53.9623, -1.0819), 20),  # Minster
    ((53.9895, -1.1035), 40),  # Clifton Moor
    ((53.9887, -1.0475), 40),  # Monks Cross
    ((53.9461, -1.0518), 30),  # Heslington
    ((53.9380, -1.0730), 30),  # Fulford
    ((53.9550, -1.1250), 30),  # Acomb
]


@dataclass
class Style:
    """How a driver drives: speed relative to the limit, and harsh events per sample."""

    speed_factor: float
    harsh_chance: float


STYLES = {
    "careful": Style(speed_factor=0.9, harsh_chance=0.0005),
    "average": Style(speed_factor=1.0, harsh_chance=0.002),
    "heavy-footed": Style(speed_factor=1.15, harsh_chance=0.008),
}
FLEET = [  # registration, driver name, driving style
    ("YK24 ABC", "Sam Patel", "careful"),
    ("YK73 DEF", "Alex Jones", "average"),
    ("YJ22 GHI", "Chris Wood", "heavy-footed"),
]


def miles_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Flat-earth approximation: fine over a few kilometres."""
    dlat = (b[0] - a[0]) * 69.17  # miles per degree of latitude
    dlon = (b[1] - a[1]) * 69.17 * math.cos(math.radians(a[0]))
    return math.hypot(dlat, dlon)


class Van:
    def __init__(self, vehicle_id: int, driver_id: int, style: Style, rng: random.Random) -> None:
        self.vehicle_id, self.driver_id, self.style, self.rng = vehicle_id, driver_id, style, rng
        self.leg = rng.randrange(len(WAYPOINTS))  # start somewhere different on the loop
        self.position = WAYPOINTS[self.leg][0]

    def step(self, at: datetime) -> dict:
        """Move along the loop for one sample interval and report where we are."""
        target, limit = WAYPOINTS[(self.leg + 1) % len(WAYPOINTS)]
        speed = max(0.0, self.rng.gauss(limit * self.style.speed_factor, limit * 0.08))
        remaining = miles_between(self.position, target)
        travelled = speed * SAMPLE_SECONDS / 3600
        if travelled >= remaining:
            self.position, self.leg = target, (self.leg + 1) % len(WAYPOINTS)
        else:
            fraction = travelled / remaining
            self.position = (
                self.position[0] + (target[0] - self.position[0]) * fraction,
                self.position[1] + (target[1] - self.position[1]) * fraction,
            )

        kind = "position"
        if self.rng.random() < self.style.harsh_chance:
            kind = self.rng.choice(["harsh_braking", "harsh_acceleration"])
        return {
            "vehicle_id": self.vehicle_id,
            "driver_id": self.driver_id,
            "kind": kind,
            "recorded_at": at.isoformat(),
            "latitude": round(self.position[0], 6),
            "longitude": round(self.position[1], 6),
            "speed_mph": round(speed, 1),
            "speed_limit_mph": float(limit),
        }


def ensure_fleet(client: httpx.Client, rng: random.Random) -> list[Van]:
    """Create the vehicles and drivers if they don't exist yet (safe to run repeatedly)."""
    vehicles = {v["registration"]: v["id"] for v in client.get("/vehicles").json()}
    drivers = {d["name"]: d["id"] for d in client.get("/drivers").json()}
    vans = []
    for registration, name, style in FLEET:
        if registration not in vehicles:
            response = client.post("/vehicles", json={"registration": registration})
            vehicles[registration] = response.raise_for_status().json()["id"]
        if name not in drivers:
            drivers[name] = (
                client.post("/drivers", json={"name": name}).raise_for_status().json()["id"]
            )
        vans.append(Van(vehicles[registration], drivers[name], STYLES[style], rng))
    return vans


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--hours", type=float, default=2.0, help="history to generate (default 2)")
    parser.add_argument("--realtime", action="store_true", help="send live, until Ctrl-C")
    parser.add_argument("--seed", type=int, default=None, help="repeatable random runs")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    with httpx.Client(base_url=args.api, timeout=10) as client:
        vans = ensure_fleet(client, rng)
        if args.realtime:
            while True:
                now = datetime.now(UTC)
                client.post("/events", json=[van.step(now) for van in vans]).raise_for_status()
                time.sleep(SAMPLE_SECONDS)

        steps = int(args.hours * 3600 / SAMPLE_SECONDS)
        start = datetime.now(UTC) - timedelta(hours=args.hours)
        batch: list[dict] = []
        for i in range(steps):
            at = start + timedelta(seconds=i * SAMPLE_SECONDS)
            batch.extend(van.step(at) for van in vans)
            if len(batch) >= BATCH_SIZE or i == steps - 1:
                client.post("/events", json=batch).raise_for_status()
                batch = []
        print(f"Sent {steps * len(vans)} events for {len(vans)} vans over {args.hours} hours.")
        for van, (_, name, style) in zip(vans, FLEET, strict=True):
            score = client.get(f"/drivers/{van.driver_id}/score").json()
            print(
                f"  {name:<11} ({style:<12}) score {score['score']:>5}  "
                f"{score['distance_miles']:>6} miles  speeding {score['speeding_percent']}%  "
                f"harsh {score['harsh_events']}"
            )


if __name__ == "__main__":
    main()
