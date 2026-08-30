from __future__ import annotations

import base64
import imaplib
import re
from dataclasses import dataclass
from typing import Any, Self

from .models import Mailbox, SourceMessage

_LIST_PATTERN = re.compile(
    rb"^\((?P<flags>[^)]*)\)\s+(?P<delimiter>NIL|\"(?:[^\"\\]|\\.)*\")\s+(?P<name>.+)$"
)
_UID_PATTERN = re.compile(rb"\bUID\s+(\d+)\b")
_FLAGS_PATTERN = re.compile(rb"\bFLAGS\s+\(([^)]*)\)")


def decode_modified_utf7(value: str) -> str:
    output: list[str] = []
    cursor = 0
    while cursor < len(value):
        ampersand = value.find("&", cursor)
        if ampersand < 0:
            output.append(value[cursor:])
            break
        output.append(value[cursor:ampersand])
        dash = value.find("-", ampersand)
        if dash < 0:
            output.append(value[ampersand:])
            break
        encoded = value[ampersand + 1 : dash]
        if not encoded:
            output.append("&")
        else:
            encoded = encoded.replace(",", "/")
            encoded += "=" * ((4 - len(encoded) % 4) % 4)
            output.append(base64.b64decode(encoded).decode("utf-16-be"))
        cursor = dash + 1
    return "".join(output)


def _unquote(value: bytes) -> bytes:
    if value.startswith(b'"') and value.endswith(b'"'):
        return value[1:-1].replace(rb"\\\"", b'"').replace(rb"\\\\", b"\\")
    return value


@dataclass(slots=True)
class DaouImapSource:
    username: str
    password: str
    host: str = "imap.daouoffice.com"
    port: int = 993
    timeout_seconds: int = 30
    client: Any | None = None

    def __post_init__(self) -> None:
        if not self.username.strip() or not self.password:
            raise ValueError("DaouOffice IMAP username and password are required")
        if not self.host.strip() or "://" in self.host or any(char.isspace() for char in self.host):
            raise ValueError("IMAP host must be a hostname")

    def __enter__(self) -> Self:
        self.client = imaplib.IMAP4_SSL(
            self.host,
            self.port,
            timeout=self.timeout_seconds,
        )
        try:
            self.password.encode("ascii")
        except UnicodeEncodeError:
            auth_bytes = (
                b"\0" + self.username.encode("utf-8") + b"\0" + self.password.encode("utf-8")
            )
            status, _ = self.client.authenticate("PLAIN", lambda _: auth_bytes)
        else:
            status, _ = self.client.login(self.username, self.password)
        if status != "OK":
            raise RuntimeError("DaouOffice IMAP authentication failed")
        return self

    def __exit__(self, *args: object) -> None:
        if self.client is not None:
            try:
                self.client.logout()
            except imaplib.IMAP4.error:
                pass
            self.client = None

    def _require_client(self) -> Any:
        if self.client is None:
            raise RuntimeError("IMAP source is not connected")
        return self.client

    def mailboxes(self) -> list[Mailbox]:
        client = self._require_client()
        status, rows = client.list()
        if status != "OK":
            raise RuntimeError("DaouOffice IMAP folder listing failed")
        mailboxes: list[Mailbox] = []
        for row in rows or []:
            if not isinstance(row, bytes):
                continue
            match = _LIST_PATTERN.match(row)
            if match is None:
                continue
            wire_bytes = _unquote(match.group("name"))
            wire_name = wire_bytes.decode("ascii")
            flags = frozenset(match.group("flags").decode("ascii").split())
            mailboxes.append(
                Mailbox(
                    wire_name=wire_name,
                    name=decode_modified_utf7(wire_name),
                    flags=flags,
                )
            )
        if not mailboxes:
            raise RuntimeError("DaouOffice IMAP returned no readable folders")
        return mailboxes

    def select(self, mailbox: Mailbox) -> tuple[str, list[str]]:
        client = self._require_client()
        escaped_name = mailbox.wire_name.replace("\\", "\\\\").replace('"', '\\"')
        status, _ = client.select(f'"{escaped_name}"', readonly=True)
        if status != "OK":
            raise RuntimeError(f"cannot select IMAP folder: {mailbox.name}")
        uid_validity_response = client.response("UIDVALIDITY")[1]
        if not uid_validity_response:
            raise RuntimeError(f"IMAP folder has no UIDVALIDITY: {mailbox.name}")
        uid_validity = uid_validity_response[0].decode("ascii")
        status, data = client.uid("SEARCH", None, "ALL")
        if status != "OK":
            raise RuntimeError(f"cannot search IMAP folder: {mailbox.name}")
        raw_uids = data[0] if data else b""
        return uid_validity, raw_uids.decode("ascii").split()

    def fetch(self, mailbox: Mailbox, uid_validity: str, uid: str) -> SourceMessage:
        client = self._require_client()
        status, data = client.uid("FETCH", uid, "(UID FLAGS BODY.PEEK[])")
        if status != "OK":
            raise RuntimeError(f"cannot fetch IMAP message UID {uid} from {mailbox.name}")
        for item in data or []:
            if not isinstance(item, tuple) or len(item) != 2:
                continue
            metadata, raw = item
            if not isinstance(metadata, bytes) or not isinstance(raw, bytes):
                continue
            uid_match = _UID_PATTERN.search(metadata)
            if uid_match is None or uid_match.group(1).decode("ascii") != uid:
                continue
            flags_match = _FLAGS_PATTERN.search(metadata)
            flags = (
                frozenset(flags_match.group(1).decode("ascii").split())
                if flags_match
                else frozenset()
            )
            return SourceMessage(
                folder=mailbox.name,
                uid_validity=uid_validity,
                uid=uid,
                flags=flags,
                raw=raw,
            )
        raise RuntimeError(f"IMAP message body was not returned for UID {uid}")
