import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from fleetwatch.db import engine

BEFORE_MPH = "8ae08824af8e"


def test_mph_migration_converts_existing_speeds(schema: None) -> None:
    cfg = Config("alembic.ini")
    command.downgrade(cfg, BEFORE_MPH)
    try:
        with engine.begin() as conn:
            vehicle_id = conn.execute(
                text("INSERT INTO vehicles (registration) VALUES ('MIG 1') RETURNING id")
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO events (vehicle_id, kind, recorded_at, latitude, longitude,"
                    " speed_kph, speed_limit_kph)"
                    " VALUES (:v, 'position', now(), 53.96, -1.08, 80.4672, 48.28032)"
                ),
                {"v": vehicle_id},
            )

        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            speed, limit = conn.execute(
                text("SELECT speed_mph, speed_limit_mph FROM events WHERE vehicle_id = :v"),
                {"v": vehicle_id},
            ).one()
        assert speed == pytest.approx(50.0)
        assert limit == pytest.approx(30.0)
    finally:
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM events"))
            conn.execute(text("DELETE FROM vehicles"))
