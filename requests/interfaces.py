"""Interface definitions for Requests."""
import sys

if sys.version_info < (3, 8):
    from typing_extensions import Protocol
    from typing_extensions import TypedDict
else:
    from typing import Protocol
    from typing import TypedDict


class CharacterDetectorResults(TypedDict):
    encoding: str
    confidence: float
    language: str


class CharacterDetector(Protocol):
    """Interface required for someone to implement a character detector."""

    def __call__(self, content: bytes) -> CharacterDetectorResults:
        ...
