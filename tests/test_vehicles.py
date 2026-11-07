from fastapi.testclient import TestClient


def test_create_and_list_vehicles(client: TestClient) -> None:
    for registration in ["YK24 ABC", "AB12 CDE"]:
        response = client.post("/vehicles", json={"registration": registration})
        assert response.status_code == 201

    listed = client.get("/vehicles").json()
    assert [v["registration"] for v in listed] == ["AB12 CDE", "YK24 ABC"]


def test_duplicate_registration_conflicts(client: TestClient) -> None:
    client.post("/vehicles", json={"registration": "YK24 ABC"})
    response = client.post("/vehicles", json={"registration": "YK24 ABC"})
    assert response.status_code == 409


def test_events_for_unknown_vehicle_404(client: TestClient) -> None:
    assert client.get("/vehicles/999999/events").status_code == 404


def test_positions_are_each_vehicles_latest_event(client: TestClient) -> None:
    van_a = client.post("/vehicles", json={"registration": "YK24 ABC"}).json()["id"]
    van_b = client.post("/vehicles", json={"registration": "AB12 CDE"}).json()["id"]
    driver = client.post("/drivers", json={"name": "Sam"}).json()["id"]

    def at(vehicle_id: int, second: int, lat: float) -> dict:
        return {
            "vehicle_id": vehicle_id,
            "driver_id": driver if vehicle_id == van_a else None,
            "kind": "position",
            "recorded_at": f"2026-11-07T09:00:{second:02d}Z",
            "latitude": lat,
            "longitude": -1.08,
            "speed_mph": 20.0,
            "speed_limit_mph": 30.0,
        }

    # Sent out of order: the latest is chosen by recorded_at, not by arrival.
    client.post("/events", json=[at(van_a, 10, 53.97), at(van_a, 5, 53.96), at(van_b, 1, 53.95)])

    positions = {p["registration"]: p for p in client.get("/vehicles/positions").json()}
    assert positions["YK24 ABC"]["latitude"] == 53.97
    assert positions["YK24 ABC"]["driver_name"] == "Sam"
    assert positions["AB12 CDE"]["driver_name"] is None
