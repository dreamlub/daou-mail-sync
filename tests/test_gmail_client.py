from daou_mail_sync.gmail_client import GmailClient, message_id_from_raw


def test_extracts_safe_message_id_for_gmail_search() -> None:
    assert message_id_from_raw(b"Message-ID: <abc@example.com>\r\n\r\nbody") == "abc@example.com"
    assert message_id_from_raw(b"Subject: no id\r\n\r\nbody") is None
    assert message_id_from_raw(b"Message-ID: invalid id\r\n\r\nbody") is None


def test_labels_preserve_inbox_unread_and_starred() -> None:
    client = GmailClient.__new__(GmailClient)
    labels = {"DaouOffice": "label-root"}
    client.ensure_label = lambda name: labels[name]

    result = client.labels_for("INBOX", frozenset({"\\Flagged"}))

    assert result == ["label-root", "INBOX", "UNREAD", "STARRED"]


def test_non_inbox_folder_gets_safe_source_label() -> None:
    client = GmailClient.__new__(GmailClient)
    requested: list[str] = []

    def ensure_label(name: str) -> str:
        requested.append(name)
        return f"id-{len(requested)}"

    client.ensure_label = ensure_label

    result = client.labels_for("Projects/2026", frozenset({"\\Seen"}))

    assert requested == ["DaouOffice", "DaouOffice/Projects_2026"]
    assert result == ["id-1", "id-2"]
