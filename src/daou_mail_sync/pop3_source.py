from __future__ import annotations

import poplib
from dataclasses import dataclass, field
from typing import Any, Self

from .models import Mailbox, SourceMessage


@dataclass(slots=True)
class DaouPop3Source:
    username: str
    password: str
    host: str = "pop3.daouoffice.com"
    port: int = 995
    timeout_seconds: int = 30
    mark_unread: bool = False
    client: Any | None = None
    _message_numbers: dict[str, int] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if not self.username.strip() or not self.password:
            raise ValueError("DaouOffice POP3 username and password are required")
        if not self.host.strip() or "://" in self.host or any(char.isspace() for char in self.host):
            raise ValueError("POP3 host must be a hostname")

    def __enter__(self) -> Self:
        self.client = poplib.POP3_SSL(self.host, self.port, timeout=self.timeout_seconds)
        self.client.user(self.username)
        self.client.pass_(self.password)
        return self

    def __exit__(self, *args: object) -> None:
        if self.client is not None:
            try:
                self.client.quit()
            except (OSError, poplib.error_proto):
                try:
                    self.client.close()
                except OSError:
                    pass
            self.client = None

    def _require_client(self) -> Any:
        if self.client is None:
            raise RuntimeError("POP3 source is not connected")
        return self.client

    def mailboxes(self) -> list[Mailbox]:
        return [Mailbox(wire_name="INBOX", name="INBOX", flags=frozenset())]

    def select(self, mailbox: Mailbox) -> tuple[str, list[str]]:
        if mailbox.name != "INBOX":
            raise ValueError(f"POP3 only supports INBOX, not {mailbox.name}")
        client = self._require_client()
        _, lines, _ = client.uidl()
        message_numbers: dict[str, int] = {}
        for line in lines:
            number_bytes, uid_bytes = line.split(maxsplit=1)
            message_numbers[uid_bytes.decode("ascii")] = int(number_bytes)
        self._message_numbers = message_numbers
        # Newest first makes limited verification and incremental runs surface recent mail first.
        uids = list(reversed(message_numbers))
        return "POP3-UIDL-v1", uids

    def fetch(self, mailbox: Mailbox, uid_validity: str, uid: str) -> SourceMessage:
        client = self._require_client()
        if uid_validity != "POP3-UIDL-v1":
            raise ValueError(f"unexpected POP3 UID namespace: {uid_validity}")
        try:
            message_number = self._message_numbers[uid]
        except KeyError as error:
            raise RuntimeError(f"POP3 message UID is no longer available: {uid}") from error
        _, lines, _ = client.retr(message_number)
        raw = b"\r\n".join(lines) + b"\r\n"
        flags = frozenset() if self.mark_unread else frozenset({"\\Seen"})
        return SourceMessage(
            folder=mailbox.name,
            uid_validity=uid_validity,
            uid=uid,
            flags=flags,
            raw=raw,
        )
