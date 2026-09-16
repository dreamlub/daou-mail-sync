from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
SHEET_TITLE = "초과근무명령서"
SPREADSHEET_KEY = "spreadsheet_id"

# 사유 runs long and 문서번호/제목 need room; the rest stay narrow enough to scan.
COLUMN_WIDTHS = {
    "문서번호": 210,
    "제목": 320,
    "일시원문": 340,
    "사유": 520,
    "문서ID": 170,
}
DEFAULT_WIDTH = 96


def authorize_sheets(client_secret: Path, token_file: Path) -> None:
    """Run the consent flow. Pick the Google account the sheet should live in."""
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), scopes=[SHEETS_SCOPE])
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(credentials.to_json(), encoding="utf-8")


def _load(token_file: Path):
    if not token_file.is_file():
        raise FileNotFoundError(f"Google Sheets token not found: {token_file}")
    credentials = Credentials.from_authorized_user_info(
        json.loads(token_file.read_text(encoding="utf-8")), [SHEETS_SCOPE]
    )
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token_file.write_text(credentials.to_json(), encoding="utf-8")
    if not credentials.valid:
        raise RuntimeError("Google Sheets token is invalid; run auth-sheets again")
    return credentials


class SheetsPublisher:
    """Publishes the overtime table into one spreadsheet, replacing it each run."""

    def __init__(self, token_file: Path, title: str) -> None:
        self.service = build("sheets", "v4", credentials=_load(token_file), cache_discovery=False)
        self.title = title

    def _reachable(self, spreadsheet_id: str) -> bool:
        try:
            self.service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        except HttpError:
            return False
        return True

    def ensure_spreadsheet(self, existing_id: str | None) -> tuple[str, bool]:
        """Reuse the spreadsheet this database already publishes to, or start one."""
        if existing_id and self._reachable(existing_id):
            return existing_id, False
        created = (
            self.service.spreadsheets()
            .create(
                body={
                    "properties": {"title": self.title, "locale": "ko_KR"},
                    "sheets": [{"properties": {"title": SHEET_TITLE, "sheetId": 0}}],
                }
            )
            .execute()
        )
        return str(created["spreadsheetId"]), True

    def publish(self, spreadsheet_id: str, headers: tuple[str, ...], rows: list[tuple]) -> int:
        values = [list(headers)] + [[_cell(value) for value in row] for row in rows]
        self.service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id, range=SHEET_TITLE, body={}
        ).execute()
        self.service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{SHEET_TITLE}!A1",
            # RAW so a 사유 that opens with "-" or "=" is never read as a formula.
            valueInputOption="RAW",
            body={"values": values},
        ).execute()
        self.service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": _formatting(headers, len(rows))},
        ).execute()
        return len(rows)

    @staticmethod
    def url(spreadsheet_id: str) -> str:
        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"


def _cell(value: object) -> Any:
    if value is None:
        return ""
    if isinstance(value, int):
        return value
    return str(value)


def _formatting(headers: tuple[str, ...], row_count: int) -> list[dict]:
    columns = len(headers)
    requests: list[dict] = [
        {
            "updateSheetProperties": {
                "properties": {"sheetId": 0, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "repeatCell": {
                "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                        "backgroundColor": {"red": 0.93, "green": 0.93, "blue": 0.93},
                        "verticalAlignment": "MIDDLE",
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor,verticalAlignment)",
            }
        },
        {
            "repeatCell": {
                "range": {"sheetId": 0, "startRowIndex": 1, "endRowIndex": row_count + 1},
                "cell": {"userEnteredFormat": {"wrapStrategy": "CLIP"}},
                "fields": "userEnteredFormat.wrapStrategy",
            }
        },
        {"setBasicFilter": {"filter": {"range": {"sheetId": 0, "endColumnIndex": columns}}}},
    ]
    for index, header in enumerate(headers):
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": 0,
                        "dimension": "COLUMNS",
                        "startIndex": index,
                        "endIndex": index + 1,
                    },
                    "properties": {"pixelSize": COLUMN_WIDTHS.get(header, DEFAULT_WIDTH)},
                    "fields": "pixelSize",
                }
            }
        )
    return requests
