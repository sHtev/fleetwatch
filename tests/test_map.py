from fastapi.testclient import TestClient

from fleetwatch.main import app

client = TestClient(app)


def test_map_page_is_served() -> None:
    response = client.get("/map")
    assert response.status_code == 200
    assert "leaflet" in response.text


def test_rounds_have_a_line_and_stops() -> None:
    rounds = client.get("/map/rounds").json()
    assert [r["name"] for r in rounds] == ["North", "East", "South", "West"]
    for r in rounds:
        assert len(r["stops"]) == 12
        assert all(53.85 < lat < 54.05 and -1.25 < lon < -0.95 for lat, lon in r["line"])
