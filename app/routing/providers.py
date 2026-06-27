from __future__ import annotations

from typing import Protocol

from app.routing.mock_provider import MockRoutingProvider
from app.routing.schemas import RouteAlternativeData, RouteRequestData


class RoutingProvider(Protocol):
    def get_routes(self, request: RouteRequestData) -> list[RouteAlternativeData]:
        """Return ranked provider alternatives for a normalized route request."""


class UnsupportedRoutingProviderError(ValueError):
    pass


class RoutingProviderError(RuntimeError):
    """A routing provider was reachable-in-principle but failed at request time."""


def get_routing_provider(provider_name: str) -> RoutingProvider:
    if provider_name == "mock":
        return MockRoutingProvider()
    raise UnsupportedRoutingProviderError(f"Unsupported routing provider: {provider_name}")
