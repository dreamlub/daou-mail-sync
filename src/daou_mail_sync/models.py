from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Mailbox:
    wire_name: str
    name: str
    flags: frozenset[str]

    @property
    def selectable(self) -> bool:
        return "\\Noselect" not in self.flags

    @property
    def excluded_by_default(self) -> bool:
        lowered = {flag.lower() for flag in self.flags}
        return "\\trash" in lowered or "\\junk" in lowered


@dataclass(frozen=True, slots=True)
class SourceMessage:
    folder: str
    uid_validity: str
    uid: str
    flags: frozenset[str]
    raw: bytes

