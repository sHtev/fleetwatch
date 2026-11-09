from fastapi.testclient import TestClient


def test_score_endpoint_uses_driver_events_in_window(client: TestClient) -> None:
    vehicle_id = client.post("/vehicles", json={"registration": "YK24 ABC"}).json()["id"]
    driver_id = client.post("/drivers", json={"name": "Sam"}).json()["id"]
    other_driver_id = client.post("/drivers", json={"name": "Alex"}).json()["id"]

    def position(second: int, speed: float, driver: int) -> dict:
        return {
            "vehicle_id": vehicle_id,
            "driver_id": driver,
            "kind": "position",
            "recorded_at": f"2026-11-07T09:00:{second:02d}Z",
            "latitude": 53.959 + second * 0.0001,
            "longitude": -1.08,
            "speed_mph": speed,
            "speed_limit_mph": 30.0,
        }

    # Sam: 4 intervals of 10 s, the last 2 over the limit. Alex's events must be ignored.
    batch = [position(s, 25.0 if s < 20 else 40.0, driver_id) for s in range(0, 50, 10)]
    batch += [position(s + 5, 60.0, other_driver_id) for s in range(0, 50, 10)]
    assert client.post("/events", json=batch).status_code == 201

    response = client.get(
        f"/drivers/{driver_id}/score",
        params={"since": "2026-11-07T00:00:00Z", "until": "2026-11-08T00:00:00Z"},
    )
    assert response.status_code == 200
    score = response.json()
    assert score["speeding_percent"] == 50.0
    assert score["score"] == 50.0
    assert score["driving_minutes"] == 0.7


def test_events_with_unknown_driver_are_rejected(client: TestClient) -> None:
    vehicle_id = client.post("/vehicles", json={"registration": "YK24 ABC"}).json()["id"]
    response = client.post(
        "/events",
        json=[
            {
                "vehicle_id": vehicle_id,
                "driver_id": 999999,
                "kind": "position",
                "recorded_at": "2026-11-07T09:00:00Z",
                "latitude": 53.959,
                "longitude": -1.08,
                "speed_mph": 20.0,
            }
        ],
    )
    assert response.status_code == 422
    assert "drivers" in response.json()["detail"]


def test_score_for_unknown_driver_404(client: TestClient) -> None:
    assert client.get("/drivers/999999/score").status_code == 404


def test_score_applies_the_vehicle_class_limit(client: TestClient) -> None:
    """58 mph on a national-limit single carriageway: legal in a car, speeding in a van."""
    van = client.post("/vehicles", json={"registration": "YK24 ABC"}).json()
    car = client.post("/vehicles", json={"registration": "AB12 CDE", "vehicle_class": "car"}).json()
    assert van["vehicle_class"] == "van"  # the default

    def drive(vehicle_id: int, driver_id: int) -> list[dict]:
        return [
            {
                "vehicle_id": vehicle_id,
                "driver_id": driver_id,
                "kind": "position",
                "recorded_at": f"2026-11-07T09:00:{second:02d}Z",
                "latitude": 53.959 + second * 0.0001,
                "longitude": -1.08,
                "speed_mph": 58.0,
                "speed_limit_mph": 60.0,
                "carriageway": "single",
            }
            for second in range(0, 50, 10)
        ]

    in_van = client.post("/drivers", json={"name": "Sam"}).json()["id"]
    in_car = client.post("/drivers", json={"name": "Alex"}).json()["id"]
    client.post("/events", json=drive(van["id"], in_van) + drive(car["id"], in_car))

    window = {"since": "2026-11-07T00:00:00Z", "until": "2026-11-08T00:00:00Z"}
    assert client.get(f"/drivers/{in_van}/score", params=window).json()["speeding_percent"] == 100
    assert client.get(f"/drivers/{in_car}/score", params=window).json()["speeding_percent"] == 0


def test_driver_list_shows_the_vehicle_each_last_drove(client: TestClient) -> None:
    first = client.post("/vehicles", json={"registration": "YK24 ABC"}).json()["id"]
    second = client.post("/vehicles", json={"registration": "YK73 DEF"}).json()["id"]
    sam = client.post("/drivers", json={"name": "Sam"}).json()["id"]
    client.post("/drivers", json={"name": "Alex"})  # hasn't driven yet

    def event(vehicle_id: int, minute: int) -> dict:
        return {
            "vehicle_id": vehicle_id,
            "driver_id": sam,
            "kind": "position",
            "recorded_at": f"2026-11-07T09:{minute:02d}:00Z",
            "latitude": 53.959,
            "longitude": -1.08,
            "speed_mph": 20.0,
        }

    client.post("/events", json=[event(first, 0), event(second, 30)])

    drivers = {d["name"]: d for d in client.get("/drivers").json()}
    assert drivers["Sam"]["vehicle_registration"] == "YK73 DEF"
    assert drivers["Alex"]["vehicle_registration"] is None
