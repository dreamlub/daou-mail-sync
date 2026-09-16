from daou_approval.sheets_client import (
    COLUMN_WIDTHS,
    DEFAULT_WIDTH,
    SheetsPublisher,
    _cell,
    _formatting,
)

HEADERS = ("문서번호", "제목", "사유", "총시간(분)")


def test_numbers_stay_numbers_so_the_sheet_can_sum_them():
    assert _cell(90) == 90
    assert _cell(0) == 0


def test_missing_values_become_blank_cells_not_the_word_none():
    assert _cell(None) == ""


def test_everything_else_is_written_as_text():
    assert _cell("발트루스트-2026-DX담당-00070") == "발트루스트-2026-DX담당-00070"


def test_the_header_row_is_frozen_and_filterable():
    requests = _formatting(HEADERS, 313)

    frozen = next(r for r in requests if "updateSheetProperties" in r)
    assert frozen["updateSheetProperties"]["properties"]["gridProperties"]["frozenRowCount"] == 1
    assert any("setBasicFilter" in request for request in requests)


def test_wide_columns_get_room_and_the_rest_stay_narrow():
    requests = [r for r in _formatting(HEADERS, 1) if "updateDimensionProperties" in r]
    widths = [r["updateDimensionProperties"]["properties"]["pixelSize"] for r in requests]

    assert len(widths) == len(HEADERS)
    assert widths[HEADERS.index("사유")] == COLUMN_WIDTHS["사유"]
    assert widths[HEADERS.index("총시간(분)")] == DEFAULT_WIDTH


def test_the_spreadsheet_url_is_built_from_its_id():
    assert SheetsPublisher.url("abc123").endswith("/spreadsheets/d/abc123/edit")
