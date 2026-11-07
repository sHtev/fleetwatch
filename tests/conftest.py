import os

# Point the app at the test database before anything imports fleetwatch.config.
os.environ["DATABASE_URL"] = (
    "postgresql+psycopg://fleetwatch:fleetwatch@localhost:5432/fleetwatch_test"
)

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from fleetwatch.db import engine, get_session  # noqa: E402
from fleetwatch.main import app  # noqa: E402


@pytest.fixture(scope="session")
def schema() -> None:
    """Build the schema with the real migrations, checking downgrade works too."""
    alembic_cfg = Config("alembic.ini")
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")


@pytest.fixture
def session(schema: None) -> Iterator[Session]:
    """A session inside a transaction that is rolled back after each test.

    The app's commits become savepoints, so nothing persists between tests.
    """
    with engine.connect() as connection, connection.begin() as transaction:
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
