"""Drive simulated vans on their York delivery rounds and post their telematics to the API.

    uv run python scripts/simulate.py                  # 2 hours of history, as fast as possible
    uv run python scripts/simulate.py --realtime       # live: one sample every 5 s per van

Rounds come from data/york_rounds.json (see scripts/build_routes.py). Each van speeds up and
slows down smoothly, slows for sharp corners, brakes to a stop at each drop and parks there
with the engine off, then returns to the depot and starts its round again.
"""

import argparse
import json
import math
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from fleetwatch.models import Carriageway, VehicleClass
from fleetwatch.scoring import effective_limit_mph

ROUNDS_FILE = Path(__file__).parent.parent / "data" / "york_rounds.json"
SAMPLE_SECONDS = 5  # how often the device reports
PHYSICS_SECONDS = 1  # how often the driver reacts, so short stretches aren't skipped over
BATCH_SIZE = 60

ACCELERATION_MPH_PER_S = 2.0  # a loaded van: 0-30 mph in about 15 s
BRAKING_MPH_PER_S = 4.0  # comfortable braking
CORNER_MPH = 15.0
CORNER_DEGREES = 60  # a change of direction sharper than this is a corner
CORNER_LOOK_AHEAD_MILES = 0.03  # about 50 yards
LIMIT_LOOK_AHEAD_MILES = 0.1  # drivers slow down before the sign, not after it
DWELL_SECONDS = (60, 240)  # parked at each drop
DEPOT_DWELL_SECONDS = 600  # reloading between rounds


@dataclass
class Style:
    """How a driver drives: speed relative to the limit, and harsh events per sample."""

    speed_factor: float
    harsh_chance: float
    knows_van_limits: bool  # or just follows the signs, which are for cars


STYLES = {
    "careful": Style(speed_factor=0.92, harsh_chance=0.0005, knows_van_limits=True),
    "average": Style(speed_factor=1.0, harsh_chance=0.0015, knows_van_limits=False),
    "heavy-footed": Style(speed_factor=1.15, harsh_chance=0.006, knows_van_limits=False),
}
FLEET = [  # registration, driver name, driving style, round, vehicle class
    ("YK24 ABC", "Sam Patel", "careful", "North", VehicleClass.VAN),
    ("YK73 DEF", "Alex Jones", "average", "East", VehicleClass.VAN),
    ("YJ22 GHI", "Chris Wood", "heavy-footed", "South", VehicleClass.VAN),
    ("YH21 JKL", "Jo Clarke", "average", "West", VehicleClass.CAR),  # a car-derived van
]


def miles_between(a: list[float], b: list[float]) -> float:
    """Flat-earth approximation: fine over a few miles."""
    dlat = (b[0] - a[0]) * 69.17  # miles per degree of latitude
    dlon = (b[1] - a[1]) * 69.17 * math.cos(math.radians(a[0]))
    return math.hypot(dlat, dlon)


def heading(a: list[float], b: list[float]) -> float:
    dlat = b[0] - a[0]
    dlon = (b[1] - a[1]) * math.cos(math.radians(a[0]))
    return math.degrees(math.atan2(dlon, dlat))


def turn_degrees(a: list[float], b: list[float], c: list[float]) -> float:
    """How sharply the road turns at b, going from a to c."""
    change = abs(heading(b, c) - heading(a, b)) % 360
    return min(change, 360 - change)


class Van:
    def __init__(
        self,
        vehicle_id: int,
        vehicle_class: VehicleClass,
        driver_id: int,
        style: Style,
        round_: dict,
        rng: random.Random,
    ) -> None:
        self.vehicle_id, self.vehicle_class = vehicle_id, vehicle_class
        self.driver_id, self.style, self.rng = driver_id, style, rng
        self.path = round_["path"]  # [lat, lon, limit_mph, carriageway, limit_source, road]
        self.stops = {s["path_index"] for s in round_["stops"]}
        # Distance along the round to each point, for "how far to the next stop".
        self.miles_to = [0.0]
        for a, b in zip(self.path, self.path[1:], strict=False):
            self.miles_to.append(self.miles_to[-1] + miles_between(a, b))
        self.index, self.along = 0, 0.0  # on the stretch from path[index], this far along it
        self.speed = 0.0
        self.mood = 0.0  # the driver's current speed relative to the limit wanders a little
        self.parked_seconds = rng.randint(0, 300)  # vans leave the depot at different times

    def position(self) -> tuple[float, float]:
        a, b = self.path[self.index], self.path[self.index + 1]
        stretch = self.miles_to[self.index + 1] - self.miles_to[self.index]
        fraction = self.along / stretch if stretch else 0.0
        return a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction

    def preferred_speed(self, i: int) -> float:
        """The speed this driver would like on the stretch from path[i]."""
        limit, carriageway = self.path[i][2], Carriageway(self.path[i][3])
        if self.style.knows_van_limits:
            limit = effective_limit_mph(limit, carriageway, self.vehicle_class)
        return limit * self.style.speed_factor + self.mood

    def target_speed(self) -> float:
        self.mood = 0.98 * self.mood + self.rng.gauss(0, 0.45)  # same wander, at 1 s steps
        target = self.preferred_speed(self.index)

        # Anything ahead that needs a lower speed (a drop, a lower limit, a sharp corner) caps
        # today's speed at whatever still lets us brake down to it in time: v² = u² + 2ad,
        # with speeds in mph, distances in miles and braking in mph per second.
        def reachable(speed_there: float, miles_away: float) -> float:
            return math.sqrt(speed_there**2 + 2 * BRAKING_MPH_PER_S * 3600 * max(miles_away, 0))

        here = self.miles_to[self.index] + self.along
        next_stop = min((i for i in self.stops if i > self.index), default=len(self.path) - 1)
        target = min(target, reachable(0, self.miles_to[next_stop] - here))
        for i in range(self.index + 1, len(self.path) - 1):
            ahead = self.miles_to[i] - here
            if ahead > LIMIT_LOOK_AHEAD_MILES:
                break
            target = min(target, reachable(self.preferred_speed(i), ahead))
            if ahead <= CORNER_LOOK_AHEAD_MILES and (
                turn_degrees(self.path[i - 1], self.path[i], self.path[i + 1]) > CORNER_DEGREES
            ):
                target = min(target, reachable(CORNER_MPH, ahead))
        return max(target, 0.0)

    def drive(self, seconds: float) -> None:
        """Change speed towards the target, then move along the round."""
        target = self.target_speed()
        change = target - self.speed
        change = max(-BRAKING_MPH_PER_S * seconds, min(change, ACCELERATION_MPH_PER_S * seconds))
        average_speed = self.speed + change / 2
        self.speed += change

        travel = average_speed * seconds / 3600
        while travel > 0:
            stretch = self.miles_to[self.index + 1] - self.miles_to[self.index]
            if self.along + travel < stretch:
                self.along += travel
                return
            travel -= stretch - self.along
            self.index, self.along = self.index + 1, 0.0
            if self.index == len(self.path) - 1:  # back at the depot
                self.index, self.speed = 0, 0.0
                self.parked_seconds = DEPOT_DWELL_SECONDS
                return
            if self.index in self.stops:
                self.speed = 0.0
                self.parked_seconds = self.rng.randint(*DWELL_SECONDS)
                return

    def step(self, at: datetime) -> dict | None:
        """One sample interval. Returns an event, or None while parked with the engine off."""
        if self.parked_seconds > 0:
            self.parked_seconds -= SAMPLE_SECONDS
            return None
        for _ in range(SAMPLE_SECONDS // PHYSICS_SECONDS):
            if self.parked_seconds > 0:  # arrived during this interval
                break
            self.drive(PHYSICS_SECONDS)

        kind = "position"
        if self.speed > 5 and self.rng.random() < self.style.harsh_chance:
            kind = self.rng.choice(["harsh_braking", "harsh_acceleration"])
        lat, lon = self.position()
        return {
            "vehicle_id": self.vehicle_id,
            "driver_id": self.driver_id,
            "kind": kind,
            "recorded_at": at.isoformat(),
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "speed_mph": round(self.speed, 1),
            "speed_limit_mph": float(self.path[self.index][2]),
            "carriageway": self.path[self.index][3],
        }


def ensure_fleet(client: httpx.Client, rng: random.Random) -> list[Van]:
    """Create the vehicles and drivers if they don't exist yet (safe to run repeatedly)."""
    rounds = {r["name"]: r for r in json.loads(ROUNDS_FILE.read_text())["rounds"]}
    vehicles = {v["registration"]: v["id"] for v in client.get("/vehicles").json()}
    drivers = {d["name"]: d["id"] for d in client.get("/drivers").json()}
    vans = []
    for registration, name, style, round_name, vehicle_class in FLEET:
        if registration not in vehicles:
            vehicle = {"registration": registration, "vehicle_class": vehicle_class}
            response = client.post("/vehicles", json=vehicle)
            vehicles[registration] = response.raise_for_status().json()["id"]
        if name not in drivers:
            response = client.post("/drivers", json={"name": name})
            drivers[name] = response.raise_for_status().json()["id"]
        vans.append(
            Van(
                vehicles[registration],
                vehicle_class,
                drivers[name],
                STYLES[style],
                rounds[round_name],
                rng,
            )
        )
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
                events = [e for van in vans if (e := van.step(datetime.now(UTC)))]
                if events:
                    client.post("/events", json=events).raise_for_status()
                time.sleep(SAMPLE_SECONDS)

        steps = int(args.hours * 3600 / SAMPLE_SECONDS)
        start = datetime.now(UTC) - timedelta(hours=args.hours)
        batch: list[dict] = []
        sent = 0
        for i in range(steps):
            at = start + timedelta(seconds=i * SAMPLE_SECONDS)
            batch.extend(e for van in vans if (e := van.step(at)))
            if batch and (len(batch) >= BATCH_SIZE or i == steps - 1):
                client.post("/events", json=batch).raise_for_status()
                sent += len(batch)
                batch = []
        print(f"Sent {sent} events for {len(vans)} vans over {args.hours} hours.")
        for van, (_, name, style, round_name, vehicle_class) in zip(vans, FLEET, strict=True):
            score = client.get(f"/drivers/{van.driver_id}/score").json()
            print(
                f"  {name:<11} ({style:<12}) {round_name:<5} {vehicle_class:<3} "
                f"score {score['score']:>5}  "
                f"{score['distance_miles']:>5} miles in {score['driving_minutes']:>5} min  "
                f"speeding {score['speeding_percent']}%  harsh {score['harsh_events']}"
            )


if __name__ == "__main__":
    main()
