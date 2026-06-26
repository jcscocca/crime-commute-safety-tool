from __future__ import annotations

import csv
from collections.abc import Iterable
from math import isfinite
from pathlib import Path

DEFAULT_AREA_CSV = (
    Path(__file__).resolve().parent.parent / "data" / "seattle_police_beats_2018_area.csv"
)

# Placeholder ``beat`` codes that SPD records on incidents but that are not real police
# beats and therefore have no polygon in the published "Seattle Police Beats 2018-Present"
# layer. ``-`` marks an untagged/unknown beat; ``OOJ`` marks "out of jurisdiction" (the
# incident is outside Seattle). These can never be covered by the area lookup, so the
# coverage check skips them rather than reporting them as missing geometry.
NON_GEOGRAPHIC_BEATS: frozenset[str] = frozenset({"-", "OOJ"})


def load_beat_areas(path: Path | None = None) -> dict[str, float]:
    source = path or DEFAULT_AREA_CSV
    areas: dict[str, float] = {}
    with Path(source).open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            beat = (row.get("beat") or "").strip()
            if not beat:
                continue
            area = float(row["area_km2"])
            if not isfinite(area) or area <= 0:
                raise ValueError(f"Beat {beat} has non-positive area {area}.")
            areas[beat] = area
    return areas


def missing_beat_areas(
    incident_beats: Iterable[str | None], area_lookup: dict[str, float]
) -> set[str]:
    return {
        beat
        for beat in incident_beats
        if beat and beat not in NON_GEOGRAPHIC_BEATS and beat not in area_lookup
    }
