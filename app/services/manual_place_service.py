from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlaceCluster
from app.normalization.geo import snap_to_grid
from app.places.schemas import ManualPlaceCreate, ManualPlaceResponse, ManualPlaceUpdate

MANUAL_CLUSTER_VERSION = "manual-1"
MANUAL_CLUSTER_METHOD = "manual_public_dashboard"


def create_manual_place(
    session: Session,
    user_id_hash: str,
    payload: ManualPlaceCreate,
) -> ManualPlaceResponse:
    display_latitude, display_longitude = snap_to_grid(payload.latitude, payload.longitude)
    place = PlaceCluster(
        user_id_hash=user_id_hash,
        cluster_version=MANUAL_CLUSTER_VERSION,
        cluster_method=MANUAL_CLUSTER_METHOD,
        centroid_latitude=payload.latitude,
        centroid_longitude=payload.longitude,
        display_latitude=display_latitude,
        display_longitude=display_longitude,
        cluster_radius_m=100,
        visit_count=payload.visit_count,
        total_dwell_minutes=payload.total_dwell_minutes,
        median_dwell_minutes=payload.median_dwell_minutes,
        dominant_days=payload.typical_days,
        dominant_hours=payload.typical_hours,
        inferred_place_type="manual_place",
        sensitivity_class=payload.sensitivity_class,
        display_label=payload.display_label.strip(),
        label_source="manual",
    )
    session.add(place)
    session.commit()
    session.refresh(place)
    return _place_response(place)


def update_manual_place(
    session: Session,
    user_id_hash: str,
    place_id: str,
    payload: ManualPlaceUpdate,
) -> ManualPlaceResponse | None:
    place = _get_user_place(session, user_id_hash, place_id)
    if place is None:
        return None

    values = payload.model_dump(exclude_unset=True)
    if "display_label" in values and values["display_label"] is not None:
        place.display_label = values["display_label"].strip()
    if "latitude" in values and values["latitude"] is not None:
        place.centroid_latitude = values["latitude"]
    if "longitude" in values and values["longitude"] is not None:
        place.centroid_longitude = values["longitude"]
    if "latitude" in values or "longitude" in values:
        place.display_latitude, place.display_longitude = snap_to_grid(
            place.centroid_latitude,
            place.centroid_longitude,
        )
    if "visit_count" in values and values["visit_count"] is not None:
        place.visit_count = values["visit_count"]
    if "total_dwell_minutes" in values:
        place.total_dwell_minutes = values["total_dwell_minutes"]
    if "median_dwell_minutes" in values:
        place.median_dwell_minutes = values["median_dwell_minutes"]
    if "typical_days" in values:
        place.dominant_days = values["typical_days"]
    if "typical_hours" in values:
        place.dominant_hours = values["typical_hours"]
    if "sensitivity_class" in values and values["sensitivity_class"] is not None:
        place.sensitivity_class = values["sensitivity_class"]

    session.commit()
    session.refresh(place)
    return _place_response(place)


def delete_manual_place(session: Session, user_id_hash: str, place_id: str) -> bool:
    place = _get_user_place(session, user_id_hash, place_id)
    if place is None:
        return False
    session.delete(place)
    session.commit()
    return True


def _get_user_place(session: Session, user_id_hash: str, place_id: str) -> PlaceCluster | None:
    return session.scalar(
        select(PlaceCluster).where(
            PlaceCluster.id == place_id,
            PlaceCluster.user_id_hash == user_id_hash,
            PlaceCluster.cluster_method == MANUAL_CLUSTER_METHOD,
            PlaceCluster.label_source == "manual",
        )
    )


def _place_response(place: PlaceCluster) -> ManualPlaceResponse:
    return ManualPlaceResponse(
        id=place.id,
        display_label=place.display_label or "Entered place",
        latitude=place.display_latitude,
        longitude=place.display_longitude,
        visit_count=place.visit_count,
        total_dwell_minutes=place.total_dwell_minutes,
        median_dwell_minutes=place.median_dwell_minutes,
        typical_days=place.dominant_days,
        typical_hours=place.dominant_hours,
        inferred_place_type=place.inferred_place_type,
        sensitivity_class=place.sensitivity_class,
    )
