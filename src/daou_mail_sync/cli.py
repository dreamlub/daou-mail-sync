from __future__ import annotations

import argparse
import getpass
import imaplib
import os
import poplib
import sys
from collections.abc import Sequence
from pathlib import Path

import keyring
from dotenv import load_dotenv
from googleapiclient.errors import HttpError
from keyring.errors import KeyringError

from .gmail_client import GmailClient, authorize
from .imap_source import DaouImapSource
from .pop3_source import DaouPop3Source
from .state import SyncState
from .sync import sync_mail

DEFAULT_ACCOUNT = "tony.waldlust@gmail.com"
KEYRING_SERVICE = "daou-mail-sync"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Copy DaouOffice IMAP mail to personal Gmail")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth = subparsers.add_parser("auth-google")
    auth.add_argument("--client-secret", required=True, type=Path)
    auth.add_argument("--token-file", type=Path, default=Path("data/google-token.json"))
    auth.add_argument("--account", default=DEFAULT_ACCOUNT)

    credentials = subparsers.add_parser("save-daou-password")
    credentials.add_argument("--username", default=os.environ.get("DAOU_IMAP_USER"))
    credentials.add_argument("--source", choices=("pop3", "imap"), default="pop3")
    credentials.add_argument("--host")

    sync = subparsers.add_parser("sync")
    sync.add_argument("--username", default=os.environ.get("DAOU_IMAP_USER"))
    sync.add_argument("--source", choices=("pop3", "imap"), default="pop3")
    sync.add_argument("--host")
    sync.add_argument("--pop-mark-unread", action="store_true")
    sync.add_argument("--password-env")
    sync.add_argument("--token-file", type=Path, default=Path("data/google-token.json"))
    sync.add_argument("--state-db", type=Path, default=Path("data/sync-state.sqlite3"))
    sync.add_argument("--account", default=DEFAULT_ACCOUNT)
    sync.add_argument("--folder", action="append", default=[])
    sync.add_argument("--include-spam-trash", action="store_true")
    sync.add_argument("--apply", action="store_true")
    sync.add_argument("--yes", action="store_true")
    sync.add_argument("--limit", type=int)
    return parser


def _required(value: str | None, name: str) -> str:
    if value is None or not value.strip():
        raise ValueError(f"{name} is required")
    return value


def _mail_source(
    args: argparse.Namespace, username: str, password: str
) -> DaouPop3Source | DaouImapSource:
    if args.source == "pop3":
        host = args.host or os.environ.get("DAOU_POP3_HOST", "pop3.daouoffice.com")
        return DaouPop3Source(
            username=username,
            password=password,
            host=host,
            mark_unread=getattr(args, "pop_mark_unread", False),
        )
    host = args.host or os.environ.get("DAOU_IMAP_HOST", "imap.daouoffice.com")
    return DaouImapSource(username=username, password=password, host=host)


def _sync(args: argparse.Namespace) -> int:
    if args.apply and not args.yes:
        raise ValueError("--apply requires --yes after reviewing a dry-run")
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit must be positive")
    username = _required(args.username, "DAOU_IMAP_USER")
    if args.password_env:
        password = _required(os.environ.get(args.password_env), args.password_env)
    else:
        password = keyring.get_password(KEYRING_SERVICE, username)
        if password is None:
            raise RuntimeError("DaouOffice password is not saved; run save-daou-password first")
    gmail = GmailClient(args.token_file, args.account) if args.apply else None
    with (
        _mail_source(args, username, password) as source,
        SyncState(args.state_db) as state,
    ):
        result = sync_mail(
            source,
            state,
            gmail,
            apply=args.apply,
            requested_folders=args.folder,
            include_spam_trash=args.include_spam_trash,
            limit=args.limit,
            progress=lambda writes: print(f"progress copied={writes}", flush=True),
        )
    print(
        f"folders={result.folders} discovered={result.discovered} pending={result.pending} "
        f"inserted={result.inserted} relabeled={result.relabeled}"
    )
    if not args.apply:
        print("DRY-RUN: no Gmail messages were created or changed.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    args = _parser().parse_args(argv)
    try:
        if args.command == "auth-google":
            account = authorize(args.client_secret, args.token_file, args.account)
            print(f"authorized Gmail account: {account}")
            return 0
        if args.command == "save-daou-password":
            username = _required(args.username, "DAOU_IMAP_USER")
            password = getpass.getpass("DaouOffice mail password (validated before saving): ")
            if not password:
                raise ValueError("password must not be empty")
            with _mail_source(args, username, password):
                pass
            keyring.set_password(KEYRING_SERVICE, username, password)
            print(
                f"validated and saved DaouOffice password for {username} "
                "in Windows credential storage"
            )
            return 0
        if args.command == "sync":
            return _sync(args)
        raise ValueError(f"unknown command: {args.command}")
    except (
        ValueError,
        RuntimeError,
        FileNotFoundError,
        imaplib.IMAP4.error,
        poplib.error_proto,
        KeyringError,
        HttpError,
        OSError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
