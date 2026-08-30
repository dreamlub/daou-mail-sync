from __future__ import annotations

import base64
import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.modify"


def authorize(client_secret: Path, token_file: Path, expected_account: str) -> str:
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), scopes=[GMAIL_SCOPE])
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    actual_account = str(service.users().getProfile(userId="me").execute()["emailAddress"])
    if actual_account.casefold() != expected_account.casefold():
        raise RuntimeError(
            f"authorized Google account is {actual_account}, expected {expected_account}"
        )
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(credentials.to_json(), encoding="utf-8")
    return actual_account


class GmailClient:
    def __init__(self, token_file: Path, expected_account: str) -> None:
        if not token_file.is_file():
            raise FileNotFoundError(f"Google token file not found: {token_file}")
        credentials = Credentials.from_authorized_user_info(
            json.loads(token_file.read_text(encoding="utf-8")), [GMAIL_SCOPE]
        )
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            token_file.write_text(credentials.to_json(), encoding="utf-8")
        if not credentials.valid:
            raise RuntimeError("Google OAuth token is invalid; run auth-google again")
        self.service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        profile = self.service.users().getProfile(userId="me").execute()
        actual_account = str(profile["emailAddress"])
        if actual_account.casefold() != expected_account.casefold():
            raise RuntimeError(
                f"Google token belongs to {actual_account}, expected {expected_account}"
            )
        self._labels: dict[str, str] | None = None

    def _label_index(self) -> dict[str, str]:
        if self._labels is None:
            response = self.service.users().labels().list(userId="me").execute()
            self._labels = {
                str(label["name"]): str(label["id"])
                for label in response.get("labels", [])
            }
        return self._labels

    def ensure_label(self, name: str) -> str:
        labels = self._label_index()
        if name in labels:
            return labels[name]
        result = (
            self.service.users()
            .labels()
            .create(
                userId="me",
                body={
                    "name": name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            .execute()
        )
        label_id = str(result["id"])
        labels[name] = label_id
        return label_id

    def labels_for(self, folder: str, flags: frozenset[str]) -> list[str]:
        label_ids = [self.ensure_label("DaouOffice")]
        if folder.upper() != "INBOX":
            safe_folder = folder.replace("/", "_").replace("\\", "_")
            label_ids.append(self.ensure_label(f"DaouOffice/{safe_folder}"))
        else:
            label_ids.append("INBOX")
        lowered = {flag.lower() for flag in flags}
        if "\\seen" not in lowered:
            label_ids.append("UNREAD")
        if "\\flagged" in lowered:
            label_ids.append("STARRED")
        return label_ids

    def insert(self, raw: bytes, label_ids: list[str]) -> str:
        body = {
            "raw": base64.urlsafe_b64encode(raw).decode("ascii"),
            "labelIds": label_ids,
        }
        result = (
            self.service.users()
            .messages()
            .insert(userId="me", internalDateSource="dateHeader", body=body)
            .execute()
        )
        return str(result["id"])

    def add_labels(self, gmail_id: str, label_ids: list[str]) -> None:
        self.service.users().messages().modify(
            userId="me",
            id=gmail_id,
            body={"addLabelIds": label_ids},
        ).execute()
