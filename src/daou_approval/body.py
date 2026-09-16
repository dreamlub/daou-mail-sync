from __future__ import annotations

import re
from html.parser import HTMLParser

from .models import OvertimeFields

_BLOCK_TAGS = frozenset({"br", "p", "div", "tr", "td", "th", "li", "table", "span"})
_WHITESPACE = re.compile(r"\s+")
# Drafters routinely fill in only half of the 일시 row — one date, or none while
# still setting the clock — so dates and times are read independently.
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TIMES = re.compile(r"(\d{1,2})\s*시\s*(\d{1,2})\s*분\s*~\s*(\d{1,2})\s*시\s*(\d{1,2})\s*분")
_DURATION = re.compile(r"(\d+)\s*시간\s*(\d+)\s*분")
# The form prints its own instructions into the 사유 cell: a ※ sentence ending in
# "주세요." that may be trailed by a parenthetical example. Everything else was typed.
_GUIDANCE = re.compile(r"※[^※]*?주세요\.\s*(?:\([^)]*\))?")


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text.replace("\xa0", " ")).strip()


class _CellCollector(HTMLParser):
    """Collect the text of every top-level <td>, keeping nested tables intact."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cells: list[str] = []
        self.all_text: list[str] = []
        self._stack: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag in ("td", "th"):
            self._stack.append([])
        elif tag in _BLOCK_TAGS:
            self._push(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._stack:
            finished = "".join(self._stack.pop())
            if self._stack:
                self._stack[-1].append(finished)
            else:
                self.cells.append(_normalize(finished))
        elif tag in _BLOCK_TAGS:
            self._push(" ")

    def handle_data(self, data: str) -> None:
        self._push(data)

    def _push(self, data: str) -> None:
        self.all_text.append(data)
        if self._stack:
            self._stack[-1].append(data)


def parse_cells(html: str) -> tuple[list[str], str]:
    """Return the top-level table cells and the flattened body text."""
    collector = _CellCollector()
    collector.feed(html)
    collector.close()
    return collector.cells, _normalize("".join(collector.all_text))


def _label_map(cells: list[str]) -> dict[str, str]:
    """Pair every cell that looks like a label with the cell that follows it."""
    pairs: dict[str, str] = {}
    for index, cell in enumerate(cells[:-1]):
        if cell and cell not in pairs:
            pairs[cell] = cells[index + 1]
    return pairs


def _lookup(pairs: dict[str, str], *labels: str) -> str:
    for label in labels:
        if label in pairs:
            return pairs[label]
    for label in labels:
        for key, value in pairs.items():
            if key.startswith(label):
                return value
    return ""


def _strip_note(value: str) -> str:
    return _normalize(value.split("※", 1)[0])


def _duration_field(pairs: dict[str, str], *labels: str) -> int | None:
    """Read a 총 N 시간 M 분 cell.

    A blank cell under a label that exists means nobody worked those hours, which
    is 0 — not unknown. Only the label being absent entirely (the 2025 form has no
    연장/야간 split) leaves it unknown.
    """
    for label in labels:
        for key, value in pairs.items():
            if key == label or key.startswith(label):
                return _minutes(_strip_note(value)) or 0
    return None


def _minutes(value: str) -> int | None:
    match = _DURATION.search(value)
    if match is None:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _clean_reason(value: str) -> str:
    """Drop the ※-prefixed instructions the form ships with, keep what was typed."""
    return _normalize(_GUIDANCE.sub(" ", value))


def parse_overtime(html: str) -> tuple[OvertimeFields, str]:
    """Lift the 초과근무명령서 fields out of a document body.

    Two form generations are in circulation: the 2025 layout carries a single
    일시/사유 pair, while the current one splits 연장근로(A) and 야간근로(B) out and
    names the person in a 대상자 상세정보 block.
    """
    cells, body_text = parse_cells(html)
    pairs = _label_map(cells)

    period_raw = _lookup(pairs, "초과근무 일시", "일시")
    layout = "current" if "초과근무 일시" in pairs else "legacy"

    dates = _DATE.findall(period_raw)
    start_date = dates[0] if dates else ""
    end_date = dates[1] if len(dates) > 1 else start_date

    start_time = end_time = ""
    times = _TIMES.search(period_raw)
    if times is not None:
        start_time = f"{int(times.group(1)):02d}:{int(times.group(2)):02d}"
        end_time = f"{int(times.group(3)):02d}:{int(times.group(4)):02d}"

    extended = _duration_field(pairs, "연장근로 시간(A)", "연장근로 시간")
    night = _duration_field(pairs, "야간근로 시간(B)", "야간근로 시간")
    total = _duration_field(pairs, "총 시간(C)", "총 시간")
    if total is None and (extended is not None or night is not None):
        total = (extended or 0) + (night or 0)

    fields = OvertimeFields(
        target_name=_lookup(pairs, "이름", "초과근무인원"),
        shift_hours=_lookup(pairs, "출근 ~ 퇴근시간", "출근~퇴근시간"),
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time,
        overtime_period_raw=period_raw,
        extended_minutes=extended,
        night_minutes=night,
        total_minutes=total,
        reason=_clean_reason(_lookup(pairs, "상세사유", "사유")),
        form_layout=layout,
    )
    return fields, body_text
