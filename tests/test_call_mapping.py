from app.crime.seattle_socrata import call_from_mapping

# Shape mirrors a real SPD Call Data (33kz-ixgy) row; only the fields the mapper reads.
_ROW = {
    "cad_event_number": "2026000185409",
    "cad_event_original_time_queued": "2026-06-26T23:55:35.000",
    "cad_event_arrived_time": "2026-06-26T23:58:10.000",
    "final_call_type": "TRAFFIC - BLOCKING TRAFFIC",
    "initial_call_type": "TRAFFIC - GENERAL",
    "cad_event_clearance_description": "REPORT WRITTEN (NO ARREST)",
    "priority": "3",
    "dispatch_precinct": "West",
    "dispatch_sector": "DAVID",
    "dispatch_beat": "D2",
    "dispatch_neighborhood": "DOWNTOWN COMMERCIAL",
    "dispatch_address": "5XX BLOCK OF PINE ST",
    "dispatch_latitude": "47.61410377",
    "dispatch_longitude": "-122.31683585",
}

# CAD operational fields we deliberately never carry into CrimeIncidentData.
_DROPPED_FIELDS = ("priority", "cad_event_clearance_description", "initial_call_type")


def test_call_row_maps_to_incident_fields():
    incident = call_from_mapping(_ROW)
    assert incident.external_incident_id == "2026000185409"
    assert incident.source_dataset == "seattle_spd_911"
    assert incident.offense_start_utc is not None
    assert incident.offense_start_utc.isoformat() == "2026-06-26T23:55:35+00:00"
    assert incident.report_utc is not None
    assert incident.report_utc.isoformat() == "2026-06-26T23:58:10+00:00"
    # Final call type drives the filterable dimension; category/nibrs stay null.
    assert incident.offense_subcategory == "TRAFFIC - BLOCKING TRAFFIC"
    assert incident.offense_category is None
    assert incident.nibrs_group is None
    assert incident.precinct == "West"
    assert incident.sector == "DAVID"
    assert incident.beat == "D2"
    assert incident.mcpp == "DOWNTOWN COMMERCIAL"
    assert incident.block_address == "5XX BLOCK OF PINE ST"
    assert incident.latitude == 47.61410377
    assert incident.longitude == -122.31683585
    # Reports/offense ids are not part of CAD events.
    assert incident.report_number is None
    assert incident.offense_id is None


def test_call_mapper_treats_redacted_coordinates_as_missing():
    incident = call_from_mapping(
        {**_ROW, "dispatch_latitude": "REDACTED", "dispatch_longitude": "REDACTED"}
    )
    assert incident.latitude is None
    assert incident.longitude is None
    assert incident.external_incident_id == "2026000185409"


def test_call_mapper_drops_cad_operational_fields_by_construction():
    dumped = call_from_mapping(_ROW).model_dump()
    for forbidden in _DROPPED_FIELDS:
        assert forbidden not in dumped


def test_call_mapper_falls_back_to_initial_call_type():
    incident = call_from_mapping({**_ROW, "final_call_type": ""})
    assert incident.offense_subcategory == "TRAFFIC - GENERAL"
