from pathlib import Path

from daou_mail_sync.state import SyncState


def test_records_source_uid_and_deduplicates_raw_message(tmp_path: Path) -> None:
    with SyncState(tmp_path / "state.sqlite3") as state:
        state.record(
            folder="INBOX",
            uid_validity="10",
            uid="1",
            raw_hash="abc",
            gmail_id="gmail-1",
        )

        assert state.copied_uids("INBOX", "10") == {"1"}
        assert state.copied_uids("INBOX", "11") == set()
        assert state.gmail_id_for_hash("abc") == "gmail-1"

