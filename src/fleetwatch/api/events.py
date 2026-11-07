from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from fleetwatch.db import get_session
from fleetwatch.models import Driver, Event, Vehicle
from fleetwatch.schemas import EventCreate, EventRead

router = APIRouter(prefix="/events", tags=["events"])
SessionDep = Annotated[Session, Depends(get_session)]


EventBatch = Annotated[list[EventCreate], Body(min_length=1, max_length=1000)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_events(body: EventBatch, session: SessionDep) -> list[EventRead]:
    """Accepts a batch, as devices buffer events and send them together."""
    check_known(session, Vehicle, {e.vehicle_id for e in body}, "vehicles")
    check_known(session, Driver, {e.driver_id for e in body if e.driver_id is not None}, "drivers")

    events = [Event(**e.model_dump()) for e in body]
    session.add_all(events)
    session.commit()
    return [EventRead.model_validate(e) for e in events]


def check_known(session: Session, model: type[Vehicle | Driver], ids: set[int], label: str) -> None:
    """Reject the whole batch if it refers to anything we don't know about."""
    known = set(session.scalars(select(model.id).where(model.id.in_(ids))))
    if unknown := ids - known:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown {label}: {sorted(unknown)}"
        )
