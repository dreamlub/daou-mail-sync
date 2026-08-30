from __future__ import annotations

from pathlib import Path

from daou_mail_sync.models import Mailbox, SourceMessage
from daou_mail_sync.state import SyncState
from daou_mail_sync.sync import sync_mail


class FakeSource:
    def __init__(self) -> None:
        self.messages = {
            "1": SourceMessage("INBOX", "10", "1", frozenset(), b"Message-ID: <1>\r\n\r\none"),
            "2": SourceMessage(
                "INBOX", "10", "2", frozenset({"\\Seen"}), b"Message-ID: <2>\r\n\r\ntwo"
            ),
        }

    def mailboxes(self) -> list[Mailbox]:
        return [Mailbox("INBOX", "INBOX", frozenset())]

    def select(self, mailbox: Mailbox) -> tuple[str, list[str]]:
        return "10", ["1", "2"]

    def fetch(self, mailbox: Mailbox, uid_validity: str, uid: str) -> SourceMessage:
        return self.messages[uid]


class FakeGmail:
    def __init__(self) -> None:
        self.inserted: list[bytes] = []
        self.relabeled: list[str] = []

    def labels_for(self, folder: str, flags: frozenset[str]) -> list[str]:
        return ["label"]

    def insert(self, raw: bytes, label_ids: list[str]) -> str:
        self.inserted.append(raw)
        return f"gmail-{len(self.inserted)}"

    def add_labels(self, gmail_id: str, label_ids: list[str]) -> None:
        self.relabeled.append(gmail_id)


def test_dry_run_does_not_fetch_or_write(tmp_path: Path) -> None:
    source = FakeSource()
    with SyncState(tmp_path / "state.sqlite3") as state:
        result = sync_mail(source, state, None, apply=False)

    assert result.discovered == 2
    assert result.pending == 2
    assert result.inserted == 0


def test_apply_limit_and_resume_without_duplicates(tmp_path: Path) -> None:
    source = FakeSource()
    gmail = FakeGmail()
    state_path = tmp_path / "state.sqlite3"

    with SyncState(state_path) as state:
        first = sync_mail(source, state, gmail, apply=True, limit=1)
    with SyncState(state_path) as state:
        second = sync_mail(source, state, gmail, apply=True)
    with SyncState(state_path) as state:
        third = sync_mail(source, state, gmail, apply=True)

    assert first.inserted == 1
    assert second.inserted == 1
    assert third.pending == 0
    assert len(gmail.inserted) == 2


def test_same_raw_message_in_two_folders_is_inserted_once(tmp_path: Path) -> None:
    raw = b"Message-ID: <same>\r\n\r\nsame body"
    source = FakeSource()
    source.messages = {
        "1": SourceMessage("INBOX", "10", "1", frozenset(), raw),
    }
    archive = Mailbox("Archive", "Archive", frozenset())
    source.mailboxes = lambda: [Mailbox("INBOX", "INBOX", frozenset()), archive]

    def select(mailbox: Mailbox) -> tuple[str, list[str]]:
        return ("10", ["1"]) if mailbox.name == "INBOX" else ("20", ["2"])

    def fetch(mailbox: Mailbox, uid_validity: str, uid: str) -> SourceMessage:
        return SourceMessage(mailbox.name, uid_validity, uid, frozenset(), raw)

    source.select = select
    source.fetch = fetch
    gmail = FakeGmail()

    with SyncState(tmp_path / "state.sqlite3") as state:
        result = sync_mail(source, state, gmail, apply=True)

    assert result.inserted == 1
    assert result.relabeled == 1
    assert len(gmail.inserted) == 1
    assert gmail.relabeled == ["gmail-1"]
