"""vehicle class and carriageway

Revision ID: b1de20b16f75
Revises: 51d6eebfd1c3
Create Date: 2026-11-08 19:21:43.949466

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b1de20b16f75"
down_revision: str | Sequence[str] | None = "51d6eebfd1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# add_column doesn't create Postgres enum types, and drop_column doesn't drop them.
vehicle_class = postgresql.ENUM("car", "van", name="vehicle_class", create_type=False)
carriageway = postgresql.ENUM("single", "dual", "motorway", name="carriageway", create_type=False)


def upgrade() -> None:
    """Upgrade schema."""
    vehicle_class.create(op.get_bind())
    carriageway.create(op.get_bind())
    # Existing vehicles become goods vans: the stricter limits, until someone says otherwise.
    op.add_column(
        "vehicles",
        sa.Column("vehicle_class", vehicle_class, server_default="van", nullable=False),
    )
    op.add_column("events", sa.Column("carriageway", carriageway, nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("events", "carriageway")
    op.drop_column("vehicles", "vehicle_class")
    carriageway.drop(op.get_bind())
    vehicle_class.drop(op.get_bind())
