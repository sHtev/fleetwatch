from fastapi import FastAPI

from fleetwatch.api import drivers, events, vehicles

app = FastAPI(title="Fleetwatch", version="0.1.0")
app.include_router(vehicles.router)
app.include_router(events.router)
app.include_router(drivers.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
