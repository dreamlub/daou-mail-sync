from daou_mail_sync.models import Mailbox, SourceMessage
from daou_mail_sync.pop3_source import DaouPop3Source


class FakePop3:
    def uidl(self):
        return b"+OK", [b"1 uid-old", b"2 uid-new"], 24

    def retr(self, number: int):
        return b"+OK", [b"Message-ID: <2>", b"", b"body"], 30


class FakeImap:
    def __init__(self, flags: bytes = b"\\Seen") -> None:
        self.flags = flags
        self.stores: list[tuple[str, str, str]] = []

    def fetch(self, number: str, fields: str):
        if fields == "(FLAGS)":
            return "OK", [b"2 (FLAGS ())"]
        return "OK", [
            (
                b"2 (UID 99 FLAGS (" + self.flags + b") BODY[HEADER.FIELDS (MESSAGE-ID)] {19}",
                b"Message-ID: <2>\r\n\r\n",
            ),
            b")",
        ]

    def store(self, number: str, operation: str, flags: str):
        self.stores.append((number, operation, flags))
        return "OK", [b""]


def test_pop3_uses_uidl_newest_first_and_never_deletes() -> None:
    source = DaouPop3Source("user@example.com", "password")
    source.client = FakePop3()
    mailbox = Mailbox("INBOX", "INBOX", frozenset())

    uid_validity, uids = source.select(mailbox)
    message = source.fetch(mailbox, uid_validity, "uid-new")

    assert uid_validity == "POP3-UIDL-v1"
    assert uids == ["uid-new", "uid-old"]
    assert message.raw == b"Message-ID: <2>\r\n\r\nbody\r\n"
    assert message.flags == frozenset({"\\Seen"})


def test_pop3_can_mark_incremental_mail_unread() -> None:
    source = DaouPop3Source("user@example.com", "password", mark_unread=True)
    source.client = FakePop3()
    mailbox = Mailbox("INBOX", "INBOX", frozenset())

    uid_validity, _ = source.select(mailbox)
    message = source.fetch(mailbox, uid_validity, "uid-new")

    assert message.flags == frozenset()


def test_pop3_restores_matching_source_message_to_unread() -> None:
    source = DaouPop3Source("user@example.com", "password", mark_unread=True)
    source.client = FakePop3()
    source._unread_client = FakeImap()
    mailbox = Mailbox("INBOX", "INBOX", frozenset())

    uid_validity, _ = source.select(mailbox)
    message = source.fetch(mailbox, uid_validity, "uid-new")

    assert source.restore_unread(message) is True
    assert source._unread_client.stores == [("2", "-FLAGS.SILENT", "(\\Seen)")]


def test_pop3_skips_unread_restore_without_message_id() -> None:
    source = DaouPop3Source("user@example.com", "password", mark_unread=True)
    source.client = FakePop3()
    source._unread_client = FakeImap()
    source.select(Mailbox("INBOX", "INBOX", frozenset()))
    message = SourceMessage(
        "INBOX", "POP3-UIDL-v1", "uid-new", frozenset(), b"Subject: x\r\n\r\nbody"
    )

    assert source.restore_unread(message) is False
    assert source._unread_client.stores == []


def test_pop3_does_not_change_different_imap_message() -> None:
    source = DaouPop3Source("user@example.com", "password", mark_unread=True)
    source.client = FakePop3()
    source._unread_client = FakeImap()
    source._unread_client.fetch = lambda number, fields: (
        "OK",
        [
            (
                b"2 (UID 99 FLAGS (\\Seen) BODY[HEADER.FIELDS (MESSAGE-ID)] {27}",
                b"Message-ID: <different>\r\n\r\n",
            )
        ],
    )
    mailbox = Mailbox("INBOX", "INBOX", frozenset())

    uid_validity, _ = source.select(mailbox)
    message = source.fetch(mailbox, uid_validity, "uid-new")

    try:
        source.restore_unread(message)
    except RuntimeError as error:
        assert "did not match" in str(error)
    else:
        raise AssertionError("mismatched messages must not be modified")
    assert source._unread_client.stores == []
