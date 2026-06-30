import pytest

from app.crime.seattle_socrata import (
    CALLS_DATA_FLOOR,
    CRIME_DATA_FLOOR,
    arrest_from_mapping,
    call_from_mapping,
    crime_incident_from_mapping,
)
from app.crime.sources import (
    LAYER_CALLS,
    LAYER_REPORTED,
    SOURCE_SPD_911,
    SOURCE_SPD_ARRESTS,
    SOURCE_SPD_CRIME,
    get_crime_source,
    sources_for_layer,
)


def test_source_constants_match_stored_tags():
    assert SOURCE_SPD_CRIME == "seattle_spd_crime"
    assert SOURCE_SPD_ARRESTS == "seattle_spd_arrests"
    assert SOURCE_SPD_911 == "seattle_spd_911"
    assert arrest_from_mapping({"arrest_number": "x"}).source_dataset == SOURCE_SPD_ARRESTS
    assert call_from_mapping({"cad_event_number": "x"}).source_dataset == SOURCE_SPD_911


def test_registry_resolves_known_sources():
    crime = get_crime_source(SOURCE_SPD_CRIME)
    assert crime.dataset_attr == "socrata_dataset_id"
    assert crime.mapper is crime_incident_from_mapping
    assert crime.date_field == "offense_date"
    assert crime.data_floor == CRIME_DATA_FLOOR

    arrests = get_crime_source(SOURCE_SPD_ARRESTS)
    assert arrests.dataset_attr == "socrata_arrests_dataset_id"
    assert arrests.mapper is arrest_from_mapping
    assert arrests.date_field == "arrest_occurred_date_time"
    assert arrests.data_floor == CRIME_DATA_FLOOR

    calls = get_crime_source(SOURCE_SPD_911)
    assert calls.dataset_attr == "socrata_calls_dataset_id"
    assert calls.mapper is call_from_mapping
    assert calls.date_field == "cad_event_original_time_queued"
    # The call set is far larger, so it ingests from a later floor than reported crime.
    assert calls.data_floor == CALLS_DATA_FLOOR
    assert calls.data_floor > CRIME_DATA_FLOOR


def test_registry_rejects_unknown_source():
    with pytest.raises(ValueError, match="Unknown crime source"):
        get_crime_source("nope")


def test_layers_map_to_underlying_sources():
    assert sources_for_layer(LAYER_REPORTED) == (SOURCE_SPD_CRIME, SOURCE_SPD_ARRESTS)
    assert sources_for_layer(LAYER_CALLS) == (SOURCE_SPD_911,)


def test_layers_are_disjoint_so_a_call_is_never_blended_with_its_report():
    reported = set(sources_for_layer(LAYER_REPORTED))
    calls = set(sources_for_layer(LAYER_CALLS))
    assert reported.isdisjoint(calls)


def test_unknown_layer_rejected():
    with pytest.raises(ValueError, match="Unknown layer"):
        sources_for_layer("nope")
