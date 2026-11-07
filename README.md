# Fleetwatch

A small fleet telematics demo: simulated vehicles send events (position, speed, harsh braking) to a FastAPI service, which stores them in Postgres and scores drivers. A React Native (Expo) driver app comes later.

## Running locally

```sh
docker compose up -d --wait        # Postgres on localhost:5432
uv run fastapi dev src/fleetwatch/main.py
```

API docs: http://localhost:8000/docs

## Live map

With the API running, open http://localhost:8000/map and start the simulator with `--realtime`. Vans move along their rounds every few seconds, coloured by speed against the limit (green within it, amber within the 10% + 2 mph tolerance, red speeding, grey parked). Click a van for its driver's score.

## Simulated fleet

```sh
uv run python scripts/simulate.py              # 2 hours of history for 3 vans around York
uv run python scripts/simulate.py --realtime   # live events every 5 s, until Ctrl-C
```

It prints each driver's score. Scores come from `GET /drivers/{id}/score`, which starts at 100 and loses points for harsh braking or acceleration (per 100 miles) and for time spent over the speed limit, beyond the police guidance tolerance of 10% plus 2 mph. Speeds are in mph and distances in miles. The response includes the figures behind the score, so it can be explained to the driver. See `src/fleetwatch/scoring.py`.

## Delivery rounds

`data/york_rounds.json` holds four delivery rounds from a depot on Clifton Moor, each visiting 12 real York addresses, with the speed limit of every stretch of road. It's built by `scripts/build_routes.py`, which uses OpenStreetMap data through the public Overpass API, and OSRM to order the stops and route between them. Rebuild it only occasionally: those are free public services.

Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), available under the Open Database Licence (ODbL).

## Migrations

Alembic, in `migrations/`. After changing `models.py`:

```sh
uv run alembic revision --autogenerate -m "describe the change"   # then review the file
uv run alembic upgrade head
```

## Tests

```sh
uv run pytest
uv run ruff check .
```
