from app.routing.place_resolver import UnknownRoutePlaceError, resolve_route_place


def test_resolve_route_place_supports_aliases_and_display_coordinates():
    place = resolve_route_place("Capitol Hill")

    assert place.label == "Capitol Hill"
    assert place.location_type == "neighborhood"
    assert round(place.latitude, 3) == 47.623
    assert round(place.longitude, 3) == -122.321
    assert place.display_latitude is not None
    assert place.display_longitude is not None


def test_resolve_route_place_rejects_unknown_places():
    try:
        resolve_route_place("Not A Seattle Place")
    except UnknownRoutePlaceError as exc:
        assert "Unknown route place" in str(exc)
    else:
        raise AssertionError("Expected UnknownRoutePlaceError")
