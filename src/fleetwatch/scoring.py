"""Driver scoring from telematics samples. Pure functions: no database or web code here.

The score starts at 100 and loses points for:
- harsh braking and acceleration, per 100 miles driven
- the share of driving time spent over the speed limit (beyond a tolerance)
"""

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from fleetwatch.models import Carriageway, EventKind, VehicleClass

# Gaps longer than this mean the vehicle was parked or lost signal: don't count them as driving.
MAX_GAP_SECONDS = 60
# The police guidance of "10% plus 2 mph": small overspeeds aren't counted.
SPEEDING_TOLERANCE_FRACTION = 0.10
SPEEDING_TOLERANCE_MPH = 2.0
POINTS_PER_INCIDENT_PER_100_MILES = 3.0
POINTS_PER_PERCENT_SPEEDING = 1.0
EARTH_RADIUS_MILES = 3958.8
HARSH_KINDS = {EventKind.HARSH_BRAKING, EventKind.HARSH_ACCELERATION}
# National limits by vehicle class and road (GOV.UK, England and Wales).
CLASS_LIMITS_MPH = {
    VehicleClass.CAR: {Carriageway.SINGLE: 60, Carriageway.DUAL: 70, Carriageway.MOTORWAY: 70},
    VehicleClass.VAN: {Carriageway.SINGLE: 50, Carriageway.DUAL: 60, Carriageway.MOTORWAY: 70},
}


@dataclass(frozen=True)
class Sample:
    vehicle_id: int
    kind: EventKind
    recorded_at: datetime
    latitude: float
    longitude: float
    speed_mph: float
    speed_limit_mph: float | None
    carriageway: Carriageway | None = None
    vehicle_class: VehicleClass = VehicleClass.CAR


@dataclass(frozen=True)
class DriverScore:
    distance_miles: float
    driving_seconds: float
    speeding_seconds: float
    harsh_events: int

    @property
    def harsh_per_100_miles(self) -> float:
        return self.harsh_events / self.distance_miles * 100 if self.distance_miles else 0.0

    @property
    def speeding_percent(self) -> float:
        return self.speeding_seconds / self.driving_seconds * 100 if self.driving_seconds else 0.0

    @property
    def score(self) -> float:
        penalty = (
            self.harsh_per_100_miles * POINTS_PER_INCIDENT_PER_100_MILES
            + self.speeding_percent * POINTS_PER_PERCENT_SPEEDING
        )
        return round(max(0.0, 100.0 - penalty), 1)


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def effective_limit_mph(
    posted: float | None, carriageway: Carriageway | None, vehicle_class: VehicleClass
) -> float | None:
    """The limit this vehicle must keep to: the posted limit or its class limit, if lower."""
    if posted is None or carriageway is None:
        return posted
    if posted >= 70 and carriageway == Carriageway.SINGLE:
        carriageway = Carriageway.DUAL  # 70 only exists on dual carriageways and motorways
    return float(min(posted, CLASS_LIMITS_MPH[vehicle_class][carriageway]))


def is_speeding(sample: Sample) -> bool:
    limit = effective_limit_mph(sample.speed_limit_mph, sample.carriageway, sample.vehicle_class)
    if limit is None:
        return False
    return sample.speed_mph > limit * (1 + SPEEDING_TOLERANCE_FRACTION) + SPEEDING_TOLERANCE_MPH


def score_driver(samples: Iterable[Sample]) -> DriverScore:
    """Score one driver. Samples can span several vehicles and arrive in any order."""
    by_vehicle: dict[int, list[Sample]] = defaultdict(list)
    for sample in samples:
        by_vehicle[sample.vehicle_id].append(sample)

    distance_miles = driving_seconds = speeding_seconds = 0.0
    harsh_events = 0
    for vehicle_samples in by_vehicle.values():
        vehicle_samples.sort(key=lambda s: s.recorded_at)
        harsh_events += sum(1 for s in vehicle_samples if s.kind in HARSH_KINDS)
        # Each interval between consecutive samples takes the earlier sample's speed.
        for earlier, later in zip(vehicle_samples, vehicle_samples[1:], strict=False):
            gap = (later.recorded_at - earlier.recorded_at).total_seconds()
            if gap > MAX_GAP_SECONDS:
                continue
            distance_miles += haversine_miles(
                earlier.latitude, earlier.longitude, later.latitude, later.longitude
            )
            driving_seconds += gap
            if is_speeding(earlier):
                speeding_seconds += gap

    return DriverScore(
        distance_miles=distance_miles,
        driving_seconds=driving_seconds,
        speeding_seconds=speeding_seconds,
        harsh_events=harsh_events,
    )
