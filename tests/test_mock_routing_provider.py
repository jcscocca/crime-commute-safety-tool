from app.routing.mock_provider import MockRoutingProvider
from app.routing.place_resolver import resolve_route_place
from app.routing.schemas import RouteRequestData


def test_mock_provider_returns_ranked_route_alternatives_with_segments():
    request = RouteRequestData(
        user_id_hash="user-hash",
        origin=resolve_route_place("Capitol Hill"),
        destination=resolve_route_place("Downtown Seattle"),
        mode="transit",
        time_window="weekday_morning",
    )

    alternatives = MockRoutingProvider().get_routes(request)

    assert len(alternatives) >= 2
    assert alternatives[0].rank == 1
    assert alternatives[0].provider == "mock"
    assert alternatives[0].route_label
    assert alternatives[0].duration_minutes is not None
    assert alternatives[0].segments
    assert alternatives[0].segments[0].sequence == 1
    assert alternatives[0].segments[0].start_label == "Capitol Hill"
