from daou_approval.body import parse_cells, parse_overtime

CURRENT_FORM = """
<table>
  <tr><td colspan="4">초과근무 명령서</td></tr>
  <tr><td>문서번호</td><td></td><td>기안일</td><td>2026-09-16(수)</td></tr>
  <tr><td>신청부서</td><td>DX기획2팀</td><td>신청자</td><td>홍길동</td></tr>
  <tr><td><table><tr><td>신청</td><td>팀장 홍길동 2026/09/16</td></tr></table></td></tr>
  <tr><td>제목</td><td>야간 재기동 작업</td></tr>
  <tr><td>대상자 상세정보</td></tr>
  <tr><td>이름</td><td>홍길동</td><td>출근 ~ 퇴근시간</td><td>9시 ~ 18시</td></tr>
  <tr><td>초과근무 정보</td></tr>
  <tr><td>초과근무 일시</td>
      <td>2026-09-17(목) ~ 2026-09-17(목) 03 시 00 분 ~ 04 시 30 분</td></tr>
  <tr><td>연장근로 시간(A)</td><td>총 0 시간 0 분 ※ 22:00 이전 연장근로 시간</td></tr>
  <tr><td>야간근로 시간(B)</td><td>총 1 시간 30 분 ※ 22:00 ~ 익일 06:00 사이의 야간근로 시간</td></tr>
  <tr><td>총 시간(C) ※(A)+(B)</td><td>총 1 시간 30 분</td></tr>
  <tr><td>상세사유</td>
      <td>※ 초과근무 사유를 상세히 기재해 주세요. ※ 특이사항이 있는 경우 기재해 주세요.
          서비스 영향이 가장 적은 시간대에 순차 재기동 예정입니다.</td></tr>
</table>
"""

LEGACY_FORM = """
<table>
  <tr><td>제목</td><td>프리퀀시 QC 작업</td></tr>
  <tr><td>일시</td><td>2026-06-26(금) ~ 2026-06-26(금) 17 시 00 분 ~ 21 시 00 분</td></tr>
  <tr><td>초과근무인원</td><td>임꺽정</td></tr>
  <tr><td>사유</td><td>프리퀀시 개발 QC 및 수정 작업</td></tr>
</table>
"""


def test_parses_current_form_layout():
    fields, body_text = parse_overtime(CURRENT_FORM)

    assert fields.form_layout == "current"
    assert fields.target_name == "홍길동"
    assert fields.shift_hours == "9시 ~ 18시"
    assert (fields.start_date, fields.end_date) == ("2026-09-17", "2026-09-17")
    assert (fields.start_time, fields.end_time) == ("03:00", "04:30")
    assert fields.extended_minutes == 0
    assert fields.night_minutes == 90
    assert fields.total_minutes == 90
    assert "초과근무 명령서" in body_text


def test_current_form_reason_drops_the_printed_instructions():
    fields, _ = parse_overtime(CURRENT_FORM)

    assert fields.reason == "서비스 영향이 가장 적은 시간대에 순차 재기동 예정입니다."
    assert "기재해" not in fields.reason


def test_parses_legacy_form_layout():
    fields, _ = parse_overtime(LEGACY_FORM)

    assert fields.form_layout == "legacy"
    assert fields.target_name == "임꺽정"
    assert (fields.start_time, fields.end_time) == ("17:00", "21:00")
    assert fields.reason == "프리퀀시 개발 QC 및 수정 작업"
    assert fields.total_minutes is None


def test_nested_tables_do_not_split_the_enclosing_cell():
    cells, _ = parse_cells("<table><tr><td>바깥<table><tr><td>안쪽</td></tr></table></td></tr></table>")

    assert cells == ["바깥 안쪽"]


def test_missing_period_leaves_dates_blank_instead_of_guessing():
    fields, _ = parse_overtime("<table><tr><td>초과근무 일시</td><td>미정</td></tr></table>")

    assert fields.start_date == ""
    assert fields.overtime_period_raw == "미정"


BLANK_NIGHT_HOURS = """
<table>
  <tr><td>초과근무 일시</td><td>2026-09-15(화) ~ 2026-09-15(화) 17 시 00 분 ~ 19 시 30 분</td></tr>
  <tr><td>연장근로 시간(A)</td><td>총 2 시간 30 분 ※ 22:00 이전 연장근로 시간</td></tr>
  <tr><td>야간근로 시간(B)</td><td>총 시간 분 ※ 22:00 ~ 익일 06:00 사이의 야간근로 시간</td></tr>
  <tr><td>총 시간(C) ※(A)+(B)</td><td>총 2 시간 30 분</td></tr>
</table>
"""


def test_a_blank_hours_box_counts_as_zero_not_unknown():
    fields, _ = parse_overtime(BLANK_NIGHT_HOURS)

    assert fields.extended_minutes == 150
    assert fields.night_minutes == 0
    assert fields.total_minutes == 150


def test_the_legacy_form_leaves_the_split_unknown_rather_than_zero():
    fields, _ = parse_overtime(LEGACY_FORM)

    assert fields.extended_minutes is None
    assert fields.night_minutes is None


def test_a_single_date_covers_both_ends_of_the_period():
    fields, _ = parse_overtime(
        "<table><tr><td>초과근무 일시</td>"
        "<td>2026-09-08(화) ~ 17 시 00 분 ~ 21 시 00 분</td></tr></table>"
    )

    assert (fields.start_date, fields.end_date) == ("2026-09-08", "2026-09-08")
    assert (fields.start_time, fields.end_time) == ("17:00", "21:00")


def test_times_survive_a_period_with_no_dates_at_all():
    fields, _ = parse_overtime(
        "<table><tr><td>초과근무 일시</td><td>~ 17 시 30 분 ~ 21 시 00 분</td></tr></table>"
    )

    assert (fields.start_date, fields.end_date) == ("", "")
    assert (fields.start_time, fields.end_time) == ("17:30", "21:00")
