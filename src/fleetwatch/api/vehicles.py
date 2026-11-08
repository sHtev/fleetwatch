from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fleetwatch.db import get_session
from fleetwatch.models import Driver, Event, Vehicle
from fleetwatch.schemas import EventRead, VehicleCreate, VehiclePosition, VehicleRead
from fleetwatch.scoring import effective_limit_mph

router = APIRouter(prefix="/vehicles", tags=["vehicles"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_vehicle(body: VehicleCreate, session: SessionDep) -> VehicleRead:
    vehicle = Vehicle(**body.model_dump())
    session.add(vehicle)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Registration already exists") from None
    return VehicleRead.model_validate(vehicle)


@router.get("")
def list_vehicles(session: SessionDep) -> list[VehicleRead]:
    vehicles = session.scalars(select(Vehicle).order_by(Vehicle.registration))
    return [VehicleRead.model_validate(v) for v in vehicles]


@router.get("/positions")
def latest_positions(session: SessionDep) -> list[VehiclePosition]:
    """Each vehicle's most recent event (Postgres DISTINCT ON: the first row per vehicle)."""
    rows = session.execute(
        select(Event, Vehicle.registration, Vehicle.vehicle_class, Driver.name)
        .join(Vehicle, Event.vehicle_id == Vehicle.id)
        .outerjoin(Driver, Event.driver_id == Driver.id)
        .ext(distinct_on(Event.vehicle_id))
        .order_by(Event.vehicle_id, Event.recorded_at.desc())
    )
    return [
        VehiclePosition(
            vehicle_id=event.vehicle_id,
            registration=registration,
            driver_id=event.driver_id,
            driver_name=driver_name,
            recorded_at=event.recorded_at,
            latitude=event.latitude,
            longitude=event.longitude,
            speed_mph=event.speed_mph,
            speed_limit_mph=event.speed_limit_mph,
            effective_limit_mph=effective_limit_mph(
                event.speed_limit_mph, event.carriageway, vehicle_class
            ),
        )
        for event, registration, vehicle_class, driver_name in rows
    ]


@router.get("/{vehicle_id}/events")
def list_vehicle_events(
    vehicle_id: int,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[EventRead]:
    """Most recent events first."""
    if session.get(Vehicle, vehicle_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vehicle not found")
    events = session.scalars(
        select(Event)
        .where(Event.vehicle_id == vehicle_id)
        .order_by(Event.recorded_at.desc())
        .limit(limit)
    )
    return [EventRead.model_validate(e) for e in events]
