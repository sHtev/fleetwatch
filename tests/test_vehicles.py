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
