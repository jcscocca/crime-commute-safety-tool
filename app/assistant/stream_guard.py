from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable

# Words withheld behind the write head. Sized above the longest output-guard phrase
# (~10 words for the presence-claim spans) so a completing match always overlaps the
# unreleased tail — at worst an innocuous prefix of a violation has rendered.
HOLDBACK_WORDS = 12

_WORD = re.compile(r"\S+")


class StreamGuardTripped(Exception):
    """The accumulated narration matched an output-guard pattern."""

    def __init__(self, redirect: str) -> None:
        self.redirect = redirect
        super().__init__(redirect)


async def guarded_stream(
    deltas: AsyncIterator[str],
    check: Callable[[str], str | None],
) -> AsyncIterator[str]:
    """Re-run ``check`` over the full accumulated text on every delta, releasing
    text ``HOLDBACK_WORDS`` whole words behind the write head. ``check`` returns
    the redirect to raise with, or ``None`` when the text is clean. Takes
    ownership of ``deltas``: it is closed deterministically on any exit."""
    accumulated = ""
    released = 0
    try:
        async for delta in deltas:
            accumulated += delta
            redirect = check(accumulated)
            if redirect is not None:
                raise StreamGuardTripped(redirect)
            boundary = _release_boundary(accumulated)
            if boundary > released:
                yield accumulated[released:boundary]
                released = boundary
        redirect = check(accumulated)
        if redirect is not None:
            raise StreamGuardTripped(redirect)
        if len(accumulated) > released:
            yield accumulated[released:]
    finally:
        closer = getattr(deltas, "aclose", None)
        if closer is not None:
            await closer()


def _release_boundary(text: str) -> int:
    """Character index releasable now: everything before the word that starts the
    final ``HOLDBACK_WORDS``-word tail."""
    starts = [match.start() for match in _WORD.finditer(text)]
    if len(starts) <= HOLDBACK_WORDS:
        return 0
    return starts[len(starts) - HOLDBACK_WORDS]
