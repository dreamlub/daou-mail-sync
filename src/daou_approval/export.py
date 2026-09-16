from __future__ import annotations

import csv
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from .store import ApprovalStore

OVERTIME_QUERY = """
SELECT
    d.doc_num,
    d.title,
    d.drafter_name,
    d.drafter_dept_name,
    substr(d.drafted_at, 1, 10) AS drafted_on,
    d.doc_status_name,
    o.target_name,
    o.start_date,
    o.end_date,
    o.start_time,
    o.end_time,
    o.period_raw,
    o.extended_minutes,
    o.night_minutes,
    o.total_minutes,
    o.reason,
    o.form_layout,
    d.document_id
FROM overtime_orders AS o
JOIN documents AS d ON d.document_id = o.document_id
ORDER BY o.start_date DESC, d.drafted_at DESC
"""

HEADERS = (
    "문서번호",
    "제목",
    "기안자",
    "기안부서",
    "기안일",
    "결재상태",
    "대상자",
    "시작일",
    "종료일",
    "시작시각",
    "종료시각",
    "일시원문",
    "연장근로(분)",
    "야간근로(분)",
    "총시간(분)",
    "사유",
    "양식버전",
    "문서ID",
)


# Excel column widths in character units; 사유 and 일시원문 carry the long text.
COLUMN_WIDTHS = {
    "문서번호": 28,
    "제목": 42,
    "기안부서": 16,
    "일시원문": 46,
    "사유": 60,
    "문서ID": 22,
}
DEFAULT_WIDTH = 12


def overtime_rows(store: ApprovalStore) -> list[tuple]:
    """Every stored 초과근무명령서, one row per document, newest overtime first."""
    return store.connection.execute(OVERTIME_QUERY).fetchall()


def export_overtime(store: ApprovalStore, path: Path) -> int:
    """Write every stored 초과근무명령서 to CSV, Excel-readable on Windows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = overtime_rows(store)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADERS)
        writer.writerows(rows)
    return len(rows)


def export_overtime_xlsx(store: ApprovalStore, path: Path) -> int:
    """Write every stored 초과근무명령서 into a real Excel table."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = overtime_rows(store)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "초과근무명령서"
    sheet.append(list(HEADERS))
    for row in rows:
        sheet.append(["" if value is None else value for value in row])

    _guard_formulas(sheet)
    _style(sheet, len(rows))
    workbook.save(path)
    return len(rows)


def _guard_formulas(sheet) -> None:
    """A 사유 that opens with "=" is text, not a formula Excel should evaluate."""
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell.value, str) and cell.value.startswith("="):
                cell.data_type = "s"


def _style(sheet, row_count: int) -> None:
    header_fill = PatternFill("solid", fgColor="EEEEEE")
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")
    for index, header in enumerate(HEADERS, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = COLUMN_WIDTHS.get(
            header, DEFAULT_WIDTH
        )
    sheet.freeze_panes = "A2"
    if row_count:
        # A real Excel table brings its own filter and banded rows.
        reference = f"A1:{get_column_letter(len(HEADERS))}{row_count + 1}"
        table = Table(displayName="OvertimeOrders", ref=reference)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleLight9", showRowStripes=True, showColumnStripes=False
        )
        sheet.add_table(table)
