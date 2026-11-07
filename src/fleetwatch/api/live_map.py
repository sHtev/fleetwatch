"""The live map page, and the delivery rounds it draws."""

import json
from functools import cache
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from fleetwatch.config import settings

router = APIRouter(tags=["map"])
MAP_PAGE = Path(__file__).parent.parent / "static" / "map.html"


@router.get("/map", include_in_schema=False)
def map_page() -> FileResponse:
    return FileResponse(MAP_PAGE)


@cache
def load_rounds() -> list[dict]:
    """Just what the map needs: each round's line and stops, from data/york_rounds.json."""
    data = json.loads(Path(settings.rounds_file).read_text())
    return [
        {
            "name": r["name"],
            "line": [p[:2] for p in r["path"]],
            "stops": [
                {"label": s["label"], "at": r["path"][s["path_index"]][:2]} for s in r["stops"]
            ],
        }
        for r in data["rounds"]
    ]


@router.get("/map/rounds")
def rounds() -> list[dict]:
    return load_rounds()
