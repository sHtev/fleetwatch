"""speeds in mph

Hand-written: autogenerate would see a rename as drop + add, and lose the data.

Revision ID: 51d6eebfd1c3
Revises: 8ae08824af8e
Create Date: 2026-11-07 20:47:30.603900

"""

from collections.abc import Sequence

from alembic import op

revision: str = "51d6eebfd1c3"
down_revision: str | Sequence[str] | None = "8ae08824af8e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KPH_PER_MPH = 1.609344


def upgrade() -> None:
    op.alter_column("events", "speed_kph", new_column_name="speed_mph")
    op.alter_column("events", "speed_limit_kph", new_column_name="speed_limit_mph")
    op.execute(
        f"UPDATE events SET speed_mph = speed_mph / {KPH_PER_MPH}, "
        f"speed_limit_mph = speed_limit_mph / {KPH_PER_MPH}"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE events SET speed_mph = speed_mph * {KPH_PER_MPH}, "
        f"speed_limit_mph = speed_limit_mph * {KPH_PER_MPH}"
    )
    op.alter_column("events", "speed_mph", new_column_name="speed_kph")
    op.alter_column("events", "speed_limit_mph", new_column_name="speed_limit_kph")
