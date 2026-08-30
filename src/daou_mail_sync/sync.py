from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from .gmail_client import GmailClient
from .imap_source import DaouImapSource
from .models import Mailbox
from .state import SyncState


@dataclass(frozen=True, slots=True)
class SyncSummary:
    folders: int = 0
    discovered: int = 0
    pending: int = 0
    inserted: int = 0
    relabeled: int = 0


def _selected_mailboxes(
    mailboxes: list[Mailbox], requested_names: list[str], include_spam_trash: bool
) -> list[Mailbox]:
    selectable = [mailbox for mailbox in mailboxes if mailbox.selectable]
    if requested_names:
        by_name = {mailbox.name: mailbox for mailbox in selectable}
        unknown = sorted(set(requested_names) - set(by_name))
        if unknown:
            raise ValueError(f"unknown IMAP folders: {unknown}")
        return [by_name[name] for name in requested_names]
    if include_spam_trash:
        return selectable
    return [mailbox for mailbox in selectable if not mailbox.excluded_by_default]


def sync_mail(
    source: DaouImapSource,
    state: SyncState,
    gmail: GmailClient | None,
    *,
    apply: bool,
    requested_folders: list[str] | None = None,
    include_spam_trash: bool = False,
    limit: int | None = None,
    progress: Callable[[int], None] | None = None,
) -> SyncSummary:
    if apply and gmail is None:
        raise ValueError("Gmail client is required when apply is enabled")
    mailboxes = _selected_mailboxes(
        source.mailboxes(), requested_folders or [], include_spam_trash
    )
    discovered = 0
    pending = 0
    inserted = 0
    relabeled = 0
    writes = 0
    for mailbox in mailboxes:
        uid_validity, uids = source.select(mailbox)
        discovered += len(uids)
        copied = state.copied_uids(mailbox.name, uid_validity)
        pending_uids = [uid for uid in uids if uid not in copied]
        pending += len(pending_uids)
        if not apply:
            continue
        assert gmail is not None
        for uid in pending_uids:
            if limit is not None and writes >= limit:
                continue
            message = source.fetch(mailbox, uid_validity, uid)
            raw_hash = hashlib.sha256(message.raw).hexdigest()
            label_ids = gmail.labels_for(message.folder, message.flags)
            gmail_id = state.gmail_id_for_hash(raw_hash)
            if gmail_id is None:
                gmail_id = gmail.find_existing(message.raw)
                if gmail_id is None:
                    gmail_id = gmail.insert(message.raw, label_ids)
                    inserted += 1
                else:
                    gmail.add_labels(gmail_id, label_ids)
                    relabeled += 1
            else:
                gmail.add_labels(gmail_id, label_ids)
                relabeled += 1
            state.record(
                folder=message.folder,
                uid_validity=message.uid_validity,
                uid=message.uid,
                raw_hash=raw_hash,
                gmail_id=gmail_id,
            )
            writes += 1
            if progress is not None and writes % 25 == 0:
                progress(writes)
    return SyncSummary(
        folders=len(mailboxes),
        discovered=discovered,
        pending=pending,
        inserted=inserted,
        relabeled=relabeled,
    )
