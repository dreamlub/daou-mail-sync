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


def test_decode_modified_utf7() -> None:
    assert decode_modified_utf7("&0UzCpNK4-") == "테스트"
    assert decode_modified_utf7("A&-B") == "A&B"


def test_lists_mailboxes_without_exposing_content() -> None:
    source = DaouImapSource("user@example.com", "password")
    source.client = FakeImap()

    mailboxes = source.mailboxes()

    assert [mailbox.name for mailbox in mailboxes] == ["INBOX", "테스트", "Archive"]
    assert mailboxes[-1].selectable is False
