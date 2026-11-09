"""Request and response shapes (the FastAPI equivalent of DRF serializers)."""

from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from fleetwatch.models import Carriageway, EventKind, VehicleClass


class VehicleCreate(BaseModel):
    registration: str = Field(min_length=2, max_length=16)
    description: str | None = Field(default=None, max_length=100)
    vehicle_class: VehicleClass = VehicleClass.VAN


class VehicleRead(VehicleCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class DriverCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class DriverRead(DriverCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class DriverListItem(DriverRead):
    vehicle_registration: str | None  # the vehicle they last drove, if any


class DriverScoreRead(BaseModel):
    """The score, plus the numbers behind it, so a coach can explain it to the driver."""

    driver_id: int
    since: datetime
    until: datetime
    score: float
    distance_miles: float
    driving_minutes: float
    harsh_events: int
    harsh_per_100_miles: float
    speeding_percent: float


class EventCreate(BaseModel):
    vehicle_id: int
    driver_id: int | None = None
    kind: EventKind
    recorded_at: AwareDatetime  # devices must send a timezone, e.g. ...Z
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    speed_mph: float = Field(ge=0, le=200)
    speed_limit_mph: float | None = Field(default=None, gt=0, le=70)  # UK maximum is 70
    carriageway: Carriageway | None = None


class VehiclePosition(BaseModel):
    """Where a vehicle was last seen, for the live map."""

    vehicle_id: int
    registration: str
    driver_id: int | None
    driver_name: str | None
    recorded_at: datetime
    latitude: float
    longitude: float
    speed_mph: float
    speed_limit_mph: float | None  # posted
    effective_limit_mph: float | None  # what this vehicle must keep to


class EventRead(EventCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
