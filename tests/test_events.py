from typing import Any

from fastapi.testclient import TestClient


def make_vehicle(client: TestClient) -> int:
    return client.post("/vehicles", json={"registration": "YK24 ABC"}).json()["id"]


def event(vehicle_id: int, recorded_at: str, **overrides: Any) -> dict[str, Any]:
    return {
        "vehicle_id": vehicle_id,
        "kind": "position",
        "recorded_at": recorded_at,
        "latitude": 53.958,
        "longitude": -1.080,
        "speed_mph": 26.0,
        "speed_limit_mph": 30.0,
    } | overrides


def test_batch_is_stored_and_listed_newest_first(client: TestClient) -> None:
    vehicle_id = make_vehicle(client)
    batch = [
        event(vehicle_id, "2026-11-07T09:00:00Z"),
        event(vehicle_id, "2026-11-07T09:00:05Z", kind="harsh_braking", speed_mph=18.0),
    ]
    response = client.post("/events", json=batch)
    assert response.status_code == 201
    assert len(response.json()) == 2

    listed = client.get(f"/vehicles/{vehicle_id}/events").json()
    assert [e["kind"] for e in listed] == ["harsh_braking", "position"]


def test_unknown_vehicle_rejects_whole_batch(client: TestClient) -> None:
    vehicle_id = make_vehicle(client)
    batch = [event(vehicle_id, "2026-11-07T09:00:00Z"), event(999999, "2026-11-07T09:00:01Z")]

    response = client.post("/events", json=batch)
    assert response.status_code == 422
    assert client.get(f"/vehicles/{vehicle_id}/events").json() == []


def test_timestamp_without_timezone_is_rejected(client: TestClient) -> None:
    vehicle_id = make_vehicle(client)
    response = client.post("/events", json=[event(vehicle_id, "2026-11-07T09:00:00")])
    assert response.status_code == 422


def test_empty_batch_is_rejected(client: TestClient) -> None:
    assert client.post("/events", json=[]).status_code == 422
