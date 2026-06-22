from __future__ import annotations

from hashlib import sha256

from sqlalchemy.orm import Session

from app.models import ImportBatch, PlaceCluster
from app.normalization.geo import snap_to_grid
from app.schemas import DirectPlaceImportResult

DIRECT_CLUSTER_VERSION = "direct-1"
DIRECT_CLUSTER_METHOD = "direct_user_input"


def persist_direct_place_import(
    session: Session,
    result: DirectPlaceImportResult,
    payload: bytes,
    filename: str,
    user_id_hash: str,
) -> dict[str, object]:
    batch = ImportBatch(
        user_id_hash=user_id_hash,
        source_type=result.source_type,
        original_filename=filename,
        file_hash_sha256=sha256(payload).hexdigest(),
        parser_version=result.parser_version,
        detected_schema=result.detected_schema,
        status="normalized",
        privacy_mode="tableau_safe",
    )
    session.add(batch)
    session.flush()
    clusters = []
    for place in result.direct_place_clusters:
        display_latitude = place.display_latitude
        display_longitude = place.display_longitude
        if display_latitude is None or display_longitude is None:
            display_latitude, display_longitude = snap_to_grid(place.latitude, place.longitude)
        clusters.append(
            PlaceCluster(
                user_id_hash=user_id_hash,
                cluster_version=DIRECT_CLUSTER_VERSION,
                cluster_method=DIRECT_CLUSTER_METHOD,
                centroid_latitude=place.latitude,
                centroid_longitude=place.longitude,
                display_latitude=display_latitude,
                display_longitude=display_longitude,
                cluster_radius_m=100,
                visit_count=place.visit_count,
                total_dwell_minutes=place.total_dwell_minutes,
                median_dwell_minutes=place.median_dwell_minutes,
                first_seen_utc=None,
                last_seen_utc=None,
                dominant_days=place.dominant_days,
                dominant_hours=place.dominant_hours,
                inferred_place_type=place.inferred_place_type,
                sensitivity_class=place.sensitivity_class,
                display_label=place.display_label,
                label_source=place.source_type,
            )
        )
    session.add_all(clusters)
    session.commit()
    return {
        "id": batch.id,
        "status": batch.status,
        "source_type": batch.source_type,
        "detected_schema": batch.detected_schema,
        "observation_count": 0,
        "source_stop_count": 0,
        "place_cluster_count": len(clusters),
    }
