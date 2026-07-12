from __future__ import annotations

import re
from collections.abc import AsyncIterator, Callable

# Words withheld behind the write head. The hard invariant holds for ANY value >= 1:
# the word that completes a guard match is always the newest word, which is always
# inside the held tail, and the check runs before any release of that delta — so a
# complete violating phrase can never have rendered. The size only bounds how much
# innocuous PREFIX of a long-span match (the presence-claim pattern's two
# {0,40}-char gaps allow ~15-word spans) may briefly render before the trip
# replaces it; 16 covers natural sentences of that shape.
HOLDBACK_WORDS = 16

_WORD = re.compile(r"\S+")
_TRAILING_PARTIAL = re.compile(r"\S+\Z")


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
            redirect = check(_checkable_prefix(accumulated))
            if redirect is not None:
                raise StreamGuardTripped(redirect)
            boundary = _release_boundary(accumulated)
            if boundary > released:
                yield accumulated[released:boundary]
                released = boundary
        # Load-bearing full-text scan: the in-loop checks trim a trailing partial
        # word, so this is the only check that sees the final word when the stream
        # ends mid-word.
        redirect = check(accumulated)
        if redirect is not None:
            raise StreamGuardTripped(redirect)
        if len(accumulated) > released:
            yield accumulated[released:]
    finally:
        closer = getattr(deltas, "aclose", None)
        if closer is not None:
            try:
                await closer()
            except Exception:
                pass  # never mask the in-flight StreamGuardTripped / normal completion


def _checkable_prefix(text: str) -> str:
    """Text up to the last complete word. The guard patterns are \\b-anchored and \\b
    matches at end-of-string, so scanning a mid-word delta boundary would false-trip
    ("Safe" + "way"). The trailing partial word is always the newest word — held far
    inside the holdback — and the end-of-stream full-text scan covers it once complete."""
    if not text or text[-1].isspace():
        return text
    match = _TRAILING_PARTIAL.search(text)
    return text[: match.start()] if match else text


def _release_boundary(text: str) -> int:
    """Character index releasable now: everything before the word that starts the
    final ``HOLDBACK_WORDS``-word tail."""
    starts = [match.start() for match in _WORD.finditer(text)]
    if len(starts) <= HOLDBACK_WORDS:
        return 0
    return starts[len(starts) - HOLDBACK_WORDS]
