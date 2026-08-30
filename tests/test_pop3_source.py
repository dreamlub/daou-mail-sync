from daou_mail_sync.models import Mailbox
from daou_mail_sync.pop3_source import DaouPop3Source


class FakePop3:
    def uidl(self):
        return b"+OK", [b"1 uid-old", b"2 uid-new"], 24

    def retr(self, number: int):
        return b"+OK", [b"Message-ID: <2>", b"", b"body"], 30


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
