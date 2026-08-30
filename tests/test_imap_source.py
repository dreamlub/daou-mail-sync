from daou_mail_sync.imap_source import DaouImapSource, decode_modified_utf7


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
