from __future__ import annotations

from app.data.seattle_route_places import SEATTLE_ROUTE_PLACES
from app.routing.schemas import RouteLocation


class UnknownRoutePlaceError(ValueError):
    pass


def resolve_route_place(label: str) -> RouteLocation:
    key = _normalize(label)
    record = _place_index().get(key)
    if record is None:
        raise UnknownRoutePlaceError(f"Unknown route place: {label}")
    return RouteLocation(
        label=str(record["label"]),
        latitude=float(record["latitude"]),
        longitude=float(record["longitude"]),
        display_latitude=_optional_float(record.get("display_latitude")),
        display_longitude=_optional_float(record.get("display_longitude")),
        location_type=str(record.get("location_type", "unknown")),
        source="local_fixture",
    )


def _place_index() -> dict[str, dict[str, object]]:
    index: dict[str, dict[str, object]] = {}
    for key, record in SEATTLE_ROUTE_PLACES.items():
        index[_normalize(key)] = record
        index[_normalize(str(record["label"]))] = record
        for alias in record.get("aliases", []):
            index[_normalize(str(alias))] = record
    return index


def _normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)
