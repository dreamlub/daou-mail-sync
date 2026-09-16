from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import keyring
import requests
from dotenv import load_dotenv
from keyring.errors import KeyringError

from .body import parse_overtime
from .client import DaouApprovalClient, DaouApprovalError
from .export import HEADERS, export_overtime, export_overtime_xlsx, overtime_rows
from .folders import ALL_FOLDER_KEYS, resolve_folders
from .sheets_client import SPREADSHEET_KEY, SheetsPublisher, authorize_sheets
from .store import ApprovalStore
from .sync import sync_documents

KEYRING_SERVICE = "daou-approval"
DEFAULT_TENANT = "waldlust.daouoffice.com"
DEFAULT_FORM = "초과근무명령서"
DEFAULT_SHEET_TITLE = "다우오피스 초과근무명령서"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect DaouOffice approval documents into a local SQLite database"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    credentials = subparsers.add_parser("save-password")
    credentials.add_argument("--login-id", default=os.environ.get("DAOU_LOGIN_ID"))
    credentials.add_argument("--tenant", default=os.environ.get("DAOU_TENANT", DEFAULT_TENANT))

    sync = subparsers.add_parser("sync")
    sync.add_argument("--login-id", default=os.environ.get("DAOU_LOGIN_ID"))
    sync.add_argument("--tenant", default=os.environ.get("DAOU_TENANT", DEFAULT_TENANT))
    sync.add_argument("--password-env")
    sync.add_argument("--db", type=Path, default=Path("data/approval.sqlite3"))
    sync.add_argument("--form", default=DEFAULT_FORM, help="substring match on 결재양식")
    sync.add_argument("--all-forms", action="store_true", help="collect every form, not just --form")
    sync.add_argument("--folder", action="append", default=[], choices=list(ALL_FOLDER_KEYS))
    sync.add_argument("--since", help="skip documents drafted before YYYY-MM-DD")
    sync.add_argument("--limit", type=int)
    sync.add_argument("--dry-run", action="store_true")

    reparse = subparsers.add_parser("reparse")
    reparse.add_argument("--db", type=Path, default=Path("data/approval.sqlite3"))

    auth = subparsers.add_parser("auth-sheets")
    auth.add_argument("--client-secret", required=True, type=Path)
    auth.add_argument("--token-file", type=Path, default=Path("data/sheets-token.json"))

    sheets = subparsers.add_parser("push-sheets")
    sheets.add_argument("--db", type=Path, default=Path("data/approval.sqlite3"))
    sheets.add_argument("--token-file", type=Path, default=Path("data/sheets-token.json"))
    sheets.add_argument("--title", default=DEFAULT_SHEET_TITLE)
    sheets.add_argument("--spreadsheet-id", help="publish into this sheet instead of the saved one")

    export = subparsers.add_parser("export")
    export.add_argument("--db", type=Path, default=Path("data/approval.sqlite3"))
    export.add_argument("--out", type=Path, default=Path("data/overtime.csv"))
    return parser


def _required(value: str | None, name: str) -> str:
    if value is None or not value.strip():
        raise ValueError(f"{name} is required")
    return value


def _password(args: argparse.Namespace, login_id: str) -> str:
    if getattr(args, "password_env", None):
        return _required(os.environ.get(args.password_env), args.password_env)
    stored = keyring.get_password(KEYRING_SERVICE, login_id)
    if stored is None:
        raise RuntimeError("DaouOffice web password is not saved; run save-password first")
    return stored


def _save_password(args: argparse.Namespace) -> int:
    login_id = _required(args.login_id, "DAOU_LOGIN_ID")
    password = getpass.getpass("DaouOffice web password (validated before saving): ")
    if not password:
        raise ValueError("password must not be empty")
    with DaouApprovalClient(args.tenant) as client:
        client.login(login_id, password)
        client.verify_session()
    keyring.set_password(KEYRING_SERVICE, login_id, password)
    print(f"validated and saved DaouOffice web password for {login_id}")
    return 0


def _sync(args: argparse.Namespace) -> int:
    if args.limit is not None and args.limit < 1:
        raise ValueError("--limit must be positive")
    login_id = _required(args.login_id, "DAOU_LOGIN_ID")
    password = _password(args, login_id)
    form_filter = None if args.all_forms else args.form
    with (
        DaouApprovalClient(args.tenant) as client,
        ApprovalStore(args.db) as store,
    ):
        client.login(login_id, password)
        folders = resolve_folders(client.department_ids(), args.folder or None)
        result = sync_documents(
            client,
            store,
            folders,
            form_filter=form_filter,
            since=args.since,
            limit=args.limit,
            dry_run=args.dry_run,
            progress=lambda done, total: print(f"progress fetched={done}/{total}", flush=True),
        )
        documents, overtime, withheld = store.counts()
    print(
        f"folders={result.folders} listed={result.listed} matched={result.matched} "
        f"fetched={result.fetched} unchanged={result.skipped} "
        f"withheld={result.withheld} stored_documents={documents} "
        f"stored_overtime={overtime} stored_without_body={withheld}"
    )
    if args.dry_run:
        print("DRY-RUN: no document bodies were downloaded and nothing was written.")
    return 0


def _reparse(args: argparse.Namespace) -> int:
    """Re-run the body parser over documents already downloaded. No network."""
    with ApprovalStore(args.db) as store:
        updated = 0
        for document_id, form_name, body_html in store.stored_bodies():
            if "초과근무" not in form_name:
                continue
            fields, _ = parse_overtime(body_html)
            store.replace_overtime(document_id, fields)
            updated += 1
    print(f"reparsed {updated} stored bodies")
    return 0


def _push_sheets(args: argparse.Namespace) -> int:
    publisher = SheetsPublisher(args.token_file, args.title)
    with ApprovalStore(args.db) as store:
        rows = overtime_rows(store)
        wanted = args.spreadsheet_id or store.get_meta(SPREADSHEET_KEY)
        spreadsheet_id, created = publisher.ensure_spreadsheet(wanted)
        written = publisher.publish(spreadsheet_id, HEADERS, rows)
        store.set_meta(SPREADSHEET_KEY, spreadsheet_id)
    print(f"{'created' if created else 'updated'} sheet with {written} rows")
    print(publisher.url(spreadsheet_id))
    return 0


def _export(args: argparse.Namespace) -> int:
    """Format follows the filename: .xlsx gets an Excel table, anything else CSV."""
    writer = export_overtime_xlsx if args.out.suffix.lower() == ".xlsx" else export_overtime
    with ApprovalStore(args.db) as store:
        written = writer(store, args.out)
    print(f"wrote {written} rows to {args.out}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    args = _parser().parse_args(argv)
    try:
        if args.command == "save-password":
            return _save_password(args)
        if args.command == "sync":
            return _sync(args)
        if args.command == "auth-sheets":
            authorize_sheets(args.client_secret, args.token_file)
            print(f"saved Google Sheets token to {args.token_file}")
            return 0
        if args.command == "push-sheets":
            return _push_sheets(args)
        if args.command == "reparse":
            return _reparse(args)
        if args.command == "export":
            return _export(args)
        raise ValueError(f"unknown command: {args.command}")
    except (
        ValueError,
        RuntimeError,
        FileNotFoundError,
        DaouApprovalError,
        KeyringError,
        requests.RequestException,
        OSError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
