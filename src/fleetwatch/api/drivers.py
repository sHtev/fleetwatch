from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import AwareDatetime
from sqlalchemy import select
from sqlalchemy.orm import Session

from fleetwatch.db import get_session
from fleetwatch.models import Driver, Event
from fleetwatch.schemas import DriverCreate, DriverRead, DriverScoreRead
from fleetwatch.scoring import Sample, score_driver

router = APIRouter(prefix="/drivers", tags=["drivers"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_driver(body: DriverCreate, session: SessionDep) -> DriverRead:
    driver = Driver(**body.model_dump())
    session.add(driver)
    session.commit()
    return DriverRead.model_validate(driver)


@router.get("")
def list_drivers(session: SessionDep) -> list[DriverRead]:
    drivers = session.scalars(select(Driver).order_by(Driver.name))
    return [DriverRead.model_validate(d) for d in drivers]


@router.get("/{driver_id}/score")
def get_driver_score(
    driver_id: int,
    session: SessionDep,
    since: Annotated[AwareDatetime | None, Query()] = None,
    until: Annotated[AwareDatetime | None, Query()] = None,
) -> DriverScoreRead:
    """Score over a time window: by default, the last 7 days."""
    if session.get(Driver, driver_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Driver not found")
    until = until or datetime.now(UTC)
    since = since or until - timedelta(days=7)

    events = session.scalars(
        select(Event).where(
            Event.driver_id == driver_id, Event.recorded_at >= since, Event.recorded_at < until
        )
    )
    result = score_driver(
        Sample(
            vehicle_id=e.vehicle_id,
            kind=e.kind,
            recorded_at=e.recorded_at,
            latitude=e.latitude,
            longitude=e.longitude,
            speed_mph=e.speed_mph,
            speed_limit_mph=e.speed_limit_mph,
        )
        for e in events
    )
    return DriverScoreRead(
        driver_id=driver_id,
        since=since,
        until=until,
        score=result.score,
        distance_miles=round(result.distance_miles, 2),
        driving_minutes=round(result.driving_seconds / 60, 1),
        harsh_events=result.harsh_events,
        harsh_per_100_miles=round(result.harsh_per_100_miles, 1),
        speeding_percent=round(result.speeding_percent, 1),
    )
