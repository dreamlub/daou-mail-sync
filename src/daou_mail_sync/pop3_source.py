from __future__ import annotations

import imaplib
import poplib
from dataclasses import dataclass, field
from typing import Any, Self

from .gmail_client import message_id_from_raw
from .models import Mailbox, SourceMessage


@dataclass(slots=True)
class DaouPop3Source:
    username: str
    password: str
    host: str = "pop3.daouoffice.com"
    port: int = 995
    timeout_seconds: int = 30
    mark_unread: bool = False
    imap_host: str = "imap.daouoffice.com"
    imap_port: int = 993
    client: Any | None = None
    _message_numbers: dict[str, int] = field(default_factory=dict, init=False)
    _unread_client: Any | None = field(default=None, init=False)

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
        if self._unread_client is not None:
            try:
                self._unread_client.logout()
            except (OSError, imaplib.IMAP4.error):
                pass
            self._unread_client = None
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

    def _client_for_unread_restore(self) -> Any:
        if self._unread_client is None:
            client = imaplib.IMAP4_SSL(
                self.imap_host,
                self.imap_port,
                timeout=self.timeout_seconds,
            )
            client.login(self.username, self.password)
            status, _ = client.select("Inbox", readonly=False)
            if status != "OK":
                client.logout()
                raise RuntimeError("could not open DaouOffice Inbox for unread restore")
            self._unread_client = client
        return self._unread_client

    def restore_unread(self, message: SourceMessage) -> bool:
        """Remove \\Seen only after verifying POP3 and IMAP refer to the same message."""
        if not self.mark_unread:
            return False
        try:
            message_number = self._message_numbers[message.uid]
        except KeyError as error:
            raise RuntimeError(f"POP3 message UID is no longer available: {message.uid}") from error

        source_message_id = message_id_from_raw(message.raw)
        if source_message_id is None:
            raise RuntimeError("cannot safely restore unread without a Message-ID")

        client = self._client_for_unread_restore()
        status, parts = client.fetch(
            str(message_number),
            "(UID FLAGS BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])",
        )
        if status != "OK":
            raise RuntimeError("could not verify DaouOffice message before unread restore")
        metadata = b" ".join(
            part[0] for part in parts if isinstance(part, tuple) and isinstance(part[0], bytes)
        )
        header = b"".join(
            part[1] for part in parts if isinstance(part, tuple) and isinstance(part[1], bytes)
        )
        if message_id_from_raw(header) != source_message_id:
            raise RuntimeError("POP3 and IMAP messages did not match; unread restore was skipped")
        if b"\\SEEN" not in metadata.upper():
            return False

        status, _ = client.store(str(message_number), "-FLAGS.SILENT", "(\\Seen)")
        if status != "OK":
            raise RuntimeError("could not restore DaouOffice message to unread")
        status, flags = client.fetch(str(message_number), "(FLAGS)")
        flag_data = b" ".join(item for item in flags if isinstance(item, bytes))
        if status != "OK" or b"\\SEEN" in flag_data.upper():
            raise RuntimeError("DaouOffice message remained read after unread restore")
        return True
