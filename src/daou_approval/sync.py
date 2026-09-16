from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .client import DaouApprovalClient
from .models import DocumentSummary, Folder
from .store import ApprovalStore


@dataclass(frozen=True, slots=True)
class SyncResult:
    folders: int
    listed: int
    matched: int
    fetched: int
    skipped: int
    withheld: int


def sync_documents(
    client: DaouApprovalClient,
    store: ApprovalStore,
    folders: list[Folder],
    *,
    form_filter: str | None,
    since: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    progress: Callable[[int, int], None] | None = None,
) -> SyncResult:
    """Walk every folder, keep the documents that match, and store them once each.

    The same document shows up in several boxes — one I approved is also in my
    department's 기안 완료함 — so it is fetched once and every box it came from is
    recorded against it afterwards, never before the document row exists.
    """
    seen: dict[str, DocumentSummary] = {}
    sources: dict[str, list[str]] = {}
    listed = 0
    for folder in folders:
        for summary in client.list_folder(folder):
            listed += 1
            if not _matches(summary, form_filter, since):
                continue
            # The same document can be readable through one box and withheld in
            # another, so keep whichever listing grants access.
            known = seen.get(summary.document_id)
            if known is None or (summary.readable and not known.readable):
                seen[summary.document_id] = summary
            keys = sources.setdefault(summary.document_id, [])
            if folder.key not in keys:
                keys.append(folder.key)

    matched = len(seen)
    ordered = sorted(seen.values(), key=lambda item: item.drafted_at, reverse=True)
    fetched = 0
    skipped = 0
    withheld = 0
    for summary in ordered:
        if limit is not None and fetched >= limit:
            break
        stale = store.needs_fetch(summary)
        if dry_run:
            if stale:
                fetched += 1
                if not summary.readable:
                    withheld += 1
            else:
                skipped += 1
            continue
        if stale:
            document = client.fetch_document(summary, overtime=_is_overtime(summary))
            store.record(document)
            fetched += 1
            if not document.body_available:
                withheld += 1
            if progress is not None:
                progress(fetched, matched)
        else:
            skipped += 1
        for folder_key in sources[summary.document_id]:
            store.note_folder(summary.document_id, folder_key)
    return SyncResult(len(folders), listed, matched, fetched, skipped, withheld)


def _matches(summary: DocumentSummary, form_filter: str | None, since: str | None) -> bool:
    if form_filter and form_filter not in summary.form_name:
        return False
    return not since or summary.drafted_at[:10] >= since


def _is_overtime(summary: DocumentSummary) -> bool:
    return "초과근무" in summary.form_name
