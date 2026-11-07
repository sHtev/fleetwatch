from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from fleetwatch.models import EventKind
from fleetwatch.scoring import Sample, haversine_miles, score_driver

START = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
YORK = (53.9590, -1.0815)
LEEDS = (53.7965, -1.5478)


def drive(
    vehicle_id: int = 1,
    count: int = 11,
    step_seconds: int = 10,
    speed: float = 25.0,
    limit: float | None = 30.0,
    start: datetime = START,
) -> list[Sample]:
    """Samples heading north from York: 0.001 degrees latitude (about 111 m) apart."""
    return [
        Sample(
            vehicle_id=vehicle_id,
            kind=EventKind.POSITION,
            recorded_at=start + timedelta(seconds=i * step_seconds),
            latitude=YORK[0] + i * 0.001,
            longitude=YORK[1],
            speed_mph=speed,
            speed_limit_mph=limit,
        )
        for i in range(count)
    ]


def test_haversine_york_to_leeds() -> None:
    assert haversine_miles(*YORK, *LEEDS) == pytest.approx(22.06, abs=0.05)  # 35.5 km, by hand


def test_clean_driving_scores_100() -> None:
    result = score_driver(drive())
    assert result.score == 100.0
    assert result.distance_miles == pytest.approx(0.691, abs=0.005)
    assert result.driving_seconds == 100


def test_speeding_share_costs_a_point_per_percent() -> None:
    samples = drive()  # 11 samples, 10 intervals of 10 s
    samples[4:10] = [replace(s, speed_mph=40.0) for s in samples[4:10]]  # 6 intervals at 40 in a 30
    result = score_driver(samples)
    assert result.speeding_percent == pytest.approx(60.0)
    assert result.score == pytest.approx(40.0)


@pytest.mark.parametrize(("speed", "speeding"), [(35.0, False), (35.1, True)])
def test_speeding_tolerance_is_10_percent_plus_2_mph(speed: float, speeding: bool) -> None:
    result = score_driver(drive(speed=speed, limit=30.0))
    assert (result.speeding_seconds > 0) is speeding


def test_unknown_speed_limit_is_not_speeding() -> None:
    assert score_driver(drive(speed=120.0, limit=None)).speeding_seconds == 0


def test_harsh_events_are_counted_per_100_miles() -> None:
    samples = drive()
    samples[3] = replace(samples[3], kind=EventKind.HARSH_BRAKING)
    result = score_driver(samples)
    assert result.harsh_events == 1
    assert result.harsh_per_100_miles == pytest.approx(144.7, abs=0.5)  # 1 event in 0.691 miles
    assert result.score == 0.0  # 144.7 x 3 points: floored at zero


def test_parked_gap_is_not_driving() -> None:
    morning = drive(count=6)
    afternoon = drive(count=6, start=START + timedelta(hours=4))
    result = score_driver(morning + afternoon)
    assert result.driving_seconds == 100  # two 50-second stretches; the 4-hour gap is ignored


def test_vehicles_are_scored_separately_then_combined() -> None:
    # Interleaved samples from two vans must not be treated as one journey.
    result = score_driver(drive(vehicle_id=1) + drive(vehicle_id=2))
    assert result.driving_seconds == 200
    assert result.distance_miles == pytest.approx(1.382, abs=0.01)


def test_no_samples() -> None:
    result = score_driver([])
    assert result.score == 100.0
    assert result.distance_miles == 0
