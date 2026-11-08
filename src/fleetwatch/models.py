import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fleetwatch.db import Base


class EventKind(enum.StrEnum):
    POSITION = "position"
    HARSH_BRAKING = "harsh_braking"
    HARSH_ACCELERATION = "harsh_acceleration"
    SPEEDING = "speeding"


class VehicleClass(enum.StrEnum):
    """Which UK speed limits apply. Car-derived vans have car limits; other vans don't."""

    CAR = "car"  # cars and car-derived vans
    VAN = "van"  # goods vehicles up to 7.5 tonnes


class Carriageway(enum.StrEnum):
    SINGLE = "single"
    DUAL = "dual"
    MOTORWAY = "motorway"


def pg_enum(cls: type[enum.StrEnum], name: str) -> Enum:
    """A Postgres enum that stores the values ("van"), not the Python names ("VAN")."""
    return Enum(cls, name=name, values_callable=lambda members: [m.value for m in members])


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration: Mapped[str] = mapped_column(String(16), unique=True)
    description: Mapped[str | None] = mapped_column(String(100))
    vehicle_class: Mapped[VehicleClass] = mapped_column(
        pg_enum(VehicleClass, "vehicle_class"), server_default=VehicleClass.VAN.value
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    events: Mapped[list["Event"]] = relationship(back_populates="vehicle")


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    events: Mapped[list["Event"]] = relationship(back_populates="driver")


class Event(Base):
    """Something a vehicle reported: a position fix, or a driving incident at a position."""

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_vehicle_recorded", "vehicle_id", "recorded_at"),
        Index("ix_events_driver_recorded", "driver_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    # Who was driving, if the device knew (drivers log in with a card or the app).
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"))
    kind: Mapped[EventKind] = mapped_column(pg_enum(EventKind, "event_kind"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    latitude: Mapped[float]
    longitude: Mapped[float]
    speed_mph: Mapped[float]
    speed_limit_mph: Mapped[float | None]  # the posted limit, from the device's map data
    carriageway: Mapped[Carriageway | None] = mapped_column(pg_enum(Carriageway, "carriageway"))

    vehicle: Mapped[Vehicle] = relationship(back_populates="events")
    driver: Mapped[Driver | None] = relationship(back_populates="events")
