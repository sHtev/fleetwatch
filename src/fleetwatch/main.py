from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fleetwatch.api import drivers, events, live_map, vehicles
from fleetwatch.config import settings

app = FastAPI(title="Fleetwatch", version="0.1.0")
# Browsers need this to call the API from another origin, such as the Expo web dev server.
# The phone app doesn't: CORS is a browser rule.
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET"])
app.include_router(vehicles.router)
app.include_router(events.router)
app.include_router(drivers.router)
app.include_router(live_map.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
