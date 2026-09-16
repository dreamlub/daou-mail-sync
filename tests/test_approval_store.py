import csv
from dataclasses import replace

from daou_approval.export import HEADERS, export_overtime
from daou_approval.models import ApprovalDocument, ApprovalStep, DocumentSummary, OvertimeFields
from daou_approval.store import ApprovalStore

SUMMARY = DocumentSummary(
    document_id="1519998181029584896",
    doc_num="발트루스트-2026-DX담당-00070",
    form_name="초과근무명령서",
    title="야간 재기동 작업",
    drafter_name="홍길동",
    drafter_dept_name="DX기획2팀",
    drafted_at="2026-09-16T10:00:00.000+09:00",
    completed_at="2026-09-16T18:00:00.000+09:00",
    doc_status="COMPLETE",
    doc_status_name="완료",
    attach_count=0,
    readable=True,
    folder_key="approve",
)

DOCUMENT = ApprovalDocument(
    summary=SUMMARY,
    body_html="<table><tr><td>제목</td></tr></table>",
    body_text="제목",
    steps=(
        ApprovalStep(0, "DRAFT", "홍길동", "팀장", "DX기획2팀", "기안", "2026-09-16", ""),
        ApprovalStep(1, "APPROVAL", "임꺽정", "이사", "DX담당", "승인", "2026-09-16", "확인함"),
    ),
    overtime=OvertimeFields(
        target_name="홍길동",
        shift_hours="9시 ~ 18시",
        start_date="2026-09-17",
        end_date="2026-09-17",
        start_time="03:00",
        end_time="04:30",
        overtime_period_raw="2026-09-17(목) ~ 2026-09-17(목) 03 시 00 분 ~ 04 시 30 분",
        extended_minutes=0,
        night_minutes=90,
        total_minutes=90,
        reason="순차 재기동 예정",
        form_layout="current",
    ),
)


def test_recording_a_document_stores_its_steps_and_overtime_fields(tmp_path):
    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        store.record(DOCUMENT)

        assert store.counts() == (1, 1, 0)
        steps = store.connection.execute(
            "SELECT actor_name, status, opinion FROM approval_steps ORDER BY step_order"
        ).fetchall()
        minutes = store.connection.execute(
            "SELECT night_minutes, total_minutes FROM overtime_orders"
        ).fetchone()

    assert steps == [("홍길동", "기안", ""), ("임꺽정", "승인", "확인함")]
    assert minutes == (90, 90)


def test_recording_twice_replaces_steps_rather_than_duplicating_them(tmp_path):
    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        store.record(DOCUMENT)
        store.record(DOCUMENT)

        count = store.connection.execute("SELECT COUNT(*) FROM approval_steps").fetchone()[0]

    assert count == 2


def test_needs_fetch_tracks_the_stored_status(tmp_path):
    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        assert store.needs_fetch(SUMMARY) is True
        store.record(DOCUMENT)
        assert store.needs_fetch(SUMMARY) is False

        moved = replace(SUMMARY, doc_status="RETURN")
        assert store.needs_fetch(moved) is True


def test_export_writes_a_utf8_bom_csv_excel_can_open(tmp_path):
    target = tmp_path / "out" / "overtime.csv"
    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        store.record(DOCUMENT)
        written = export_overtime(store, target)

    assert written == 1
    assert target.read_bytes().startswith(b"\xef\xbb\xbf")
    with target.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0][0] == "문서번호"
    assert rows[1][0] == "발트루스트-2026-DX담당-00070"
    assert rows[0][11] == "일시원문"
    assert rows[1][6] == "홍길동"


def test_export_writes_a_real_excel_table(tmp_path):
    from openpyxl import load_workbook

    from daou_approval.export import export_overtime_xlsx

    target = tmp_path / "out" / "overtime.xlsx"
    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        store.record(DOCUMENT)
        written = export_overtime_xlsx(store, target)

    assert written == 1
    sheet = load_workbook(target).active
    assert sheet.title == "초과근무명령서"
    assert sheet["A1"].value == "문서번호"
    assert sheet["A2"].value == "발트루스트-2026-DX담당-00070"
    assert sheet.freeze_panes == "A2"
    assert "OvertimeOrders" in sheet.tables
    # minutes must arrive as numbers so Excel can sum them
    assert sheet.cell(row=2, column=HEADERS.index("총시간(분)") + 1).value == 90


def test_a_reason_starting_with_an_equals_sign_stays_text(tmp_path):
    from dataclasses import replace

    from openpyxl import load_workbook

    from daou_approval.export import export_overtime_xlsx

    document = replace(DOCUMENT, overtime=replace(DOCUMENT.overtime, reason="=1+1 긴급 대응"))
    target = tmp_path / "overtime.xlsx"
    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        store.record(document)
        export_overtime_xlsx(store, target)

    sheet = load_workbook(target).active
    cell = sheet.cell(row=2, column=HEADERS.index("사유") + 1)
    assert cell.data_type == "s"
