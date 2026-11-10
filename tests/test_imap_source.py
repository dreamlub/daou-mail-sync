from daou_mail_sync.imap_source import DaouImapSource, decode_modified_utf7
from daou_mail_sync.models import Mailbox


class FakeImap:
    def list(self):
        return (
            "OK",
            [
                b'(\\HasNoChildren) "/" "INBOX"',
                b'(\\HasNoChildren) "/" "&0UzCpNK4-"',
                b'(\\Noselect) "/" "Archive"',
            ],
        )


class FakeAuthImap:
    def __init__(self) -> None:
        self.auth_bytes: bytes | None = None

    def authenticate(self, mechanism: str, callback):
        assert mechanism == "PLAIN"
        self.auth_bytes = callback(b"")
        return "OK", [b"authenticated"]

    def logout(self) -> None:
        pass


def test_decode_modified_utf7() -> None:
    assert decode_modified_utf7("&0UzCpNK4-") == "테스트"
    assert decode_modified_utf7("A&-B") == "A&B"


def test_lists_mailboxes_without_exposing_content() -> None:
    source = DaouImapSource("user@example.com", "password")
    source.client = FakeImap()

    mailboxes = source.mailboxes()

    assert [mailbox.name for mailbox in mailboxes] == ["INBOX", "테스트", "Archive"]
    assert mailboxes[-1].selectable is False


def test_non_ascii_password_uses_utf8_plain_authentication(monkeypatch) -> None:
    fake = FakeAuthImap()
    monkeypatch.setattr("imaplib.IMAP4_SSL", lambda *args, **kwargs: fake)

    with DaouImapSource("user@example.com", "한글-password"):
        pass

    assert fake.auth_bytes == b"\0user@example.com\0" + "한글-password".encode()


class FakeSelectImap:
    def __init__(self, exists: bytes) -> None:
        self.exists = exists
        self.fetches: list[tuple[str, str]] = []

    def select(self, mailbox: str, readonly: bool = False):
        assert readonly
        return "OK", [self.exists]

    def response(self, code: str):
        assert code == "UIDVALIDITY"
        return code, [b"42"]

    def uid(self, *args):
        raise AssertionError("DaouOffice SEARCH returns nothing; it must not be used")

    def fetch(self, message_set: str, parts: str):
        self.fetches.append((message_set, parts))
        return "OK", [b"1 (UID 659)", b"2 (UID 660 FLAGS (\\Seen))", (b"3 (UID 700", b"")]


def test_select_lists_uids_with_fetch_because_search_is_empty() -> None:
    source = DaouImapSource("user@example.com", "password")
    source.client = FakeSelectImap(b"3")

    uid_validity, uids = source.select(Mailbox("Sent", "Sent", frozenset({"\\Sent"})))

    assert uid_validity == "42"
    assert uids == ["659", "660", "700"]
    assert source.client.fetches == [("1:*", "(UID)")]


def test_select_empty_folder_skips_fetch() -> None:
    source = DaouImapSource("user@example.com", "password")
    source.client = FakeSelectImap(b"0")

    assert source.select(Mailbox("Drafts", "Drafts", frozenset())) == ("42", [])
    assert source.client.fetches == []
