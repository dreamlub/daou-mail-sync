from daou_mail_sync import cli


class FakeSource:
    entered = False

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def __enter__(self):
        FakeSource.entered = True
        return self

    def __exit__(self, *args: object) -> None:
        pass


def test_password_is_validated_before_keyring_save(monkeypatch) -> None:
    saved: list[tuple[str, str, str]] = []
    FakeSource.entered = False
    monkeypatch.setattr(cli, "DaouImapSource", FakeSource)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: "secret")
    monkeypatch.setattr(cli.keyring, "set_password", lambda *args: saved.append(args))

    result = cli.main(["save-daou-password", "--username", "user@example.com"])

    assert result == 0
    assert FakeSource.entered is True
    assert saved == [("daou-mail-sync", "user@example.com", "secret")]


def test_invalid_password_is_not_saved(monkeypatch) -> None:
    class RejectingSource(FakeSource):
        def __enter__(self):
            raise RuntimeError("invalid user or password")

    saved: list[tuple[str, str, str]] = []
    monkeypatch.setattr(cli, "DaouImapSource", RejectingSource)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: "wrong")
    monkeypatch.setattr(cli.keyring, "set_password", lambda *args: saved.append(args))

    result = cli.main(["save-daou-password", "--username", "user@example.com"])

    assert result == 2
    assert saved == []
