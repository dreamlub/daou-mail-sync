from daou_approval.models import ApprovalDocument, DocumentSummary, Folder, OvertimeFields
from daou_approval.store import ApprovalStore
from daou_approval.sync import sync_documents


def summary(document_id: str, **overrides) -> DocumentSummary:
    values = {
        "document_id": document_id,
        "doc_num": f"발트루스트-2026-DX-{document_id}",
        "form_name": "초과근무명령서",
        "title": "야간 작업",
        "drafter_name": "홍길동",
        "drafter_dept_name": "DX담당",
        "drafted_at": "2026-09-16T10:00:00.000+09:00",
        "completed_at": None,
        "doc_status": "COMPLETE",
        "doc_status_name": "완료",
        "attach_count": 0,
        "readable": True,
        "folder_key": "approve",
    }
    values.update(overrides)
    return DocumentSummary(**values)


class FakeClient:
    def __init__(self, listings: dict[str, list[DocumentSummary]]) -> None:
        self.listings = listings
        self.fetched: list[str] = []

    def list_folder(self, folder: Folder):
        return iter(self.listings.get(folder.key, []))

    def fetch_document(self, item: DocumentSummary, *, overtime: bool) -> ApprovalDocument:
        if not item.readable:
            return ApprovalDocument(
                summary=item, body_html="", body_text="", steps=(), overtime=None,
                body_available=False,
            )
        self.fetched.append(item.document_id)
        return ApprovalDocument(
            summary=item,
            body_html="<table></table>",
            body_text="",
            steps=(),
            overtime=OvertimeFields(target_name="홍길동") if overtime else None,
        )


FOLDERS = [
    Folder("approve", "개인 결재 문서함", "doclist/approve/all", "draftedAt"),
    Folder("dept-draft", "부서 기안 완료함", "deptfolder/draft/1", "draftedAt"),
]


def test_document_in_two_boxes_is_fetched_once_and_both_boxes_are_recorded(tmp_path):
    client = FakeClient({"approve": [summary("1")], "dept-draft": [summary("1", folder_key="dept-draft")]})

    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        result = sync_documents(client, store, FOLDERS, form_filter="초과근무명령서")
        keys = store.connection.execute(
            "SELECT folder_key FROM document_folders WHERE document_id = '1' ORDER BY folder_key"
        ).fetchall()

    assert client.fetched == ["1"]
    assert result.listed == 2
    assert result.matched == 1
    assert [row[0] for row in keys] == ["approve", "dept-draft"]


def test_other_forms_are_left_alone(tmp_path):
    client = FakeClient({"approve": [summary("1"), summary("2", form_name="업무기안")]})

    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        result = sync_documents(client, store, FOLDERS, form_filter="초과근무명령서")

    assert client.fetched == ["1"]
    assert result.matched == 1


def test_all_forms_collects_everything(tmp_path):
    client = FakeClient({"approve": [summary("1"), summary("2", form_name="업무기안")]})

    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        sync_documents(client, store, FOLDERS, form_filter=None)

    assert sorted(client.fetched) == ["1", "2"]


def test_since_skips_older_documents(tmp_path):
    client = FakeClient(
        {"approve": [summary("1"), summary("2", drafted_at="2025-01-05T09:00:00.000+09:00")]}
    )

    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        sync_documents(client, store, FOLDERS, form_filter=None, since="2026-01-01")

    assert client.fetched == ["1"]


def test_unchanged_documents_are_not_refetched_but_status_changes_are(tmp_path):
    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        first = FakeClient({"approve": [summary("1", doc_status="PROCEED")]})
        sync_documents(first, store, FOLDERS, form_filter=None)

        again = FakeClient({"approve": [summary("1", doc_status="PROCEED")]})
        unchanged = sync_documents(again, store, FOLDERS, form_filter=None)

        moved = FakeClient({"approve": [summary("1", doc_status="COMPLETE")]})
        changed = sync_documents(moved, store, FOLDERS, form_filter=None)

    assert again.fetched == []
    assert unchanged.skipped == 1
    assert moved.fetched == ["1"]
    assert changed.fetched == 1


def test_limit_caps_the_number_of_bodies_downloaded(tmp_path):
    client = FakeClient({"approve": [summary(str(index)) for index in range(5)]})

    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        result = sync_documents(client, store, FOLDERS, form_filter=None, limit=2)

    assert len(client.fetched) == 2
    assert result.matched == 5


def test_dry_run_downloads_nothing(tmp_path):
    client = FakeClient({"approve": [summary("1")]})

    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        result = sync_documents(client, store, FOLDERS, form_filter=None, dry_run=True)
        documents, _, _ = store.counts()

    assert client.fetched == []
    assert result.fetched == 1
    assert documents == 0


def test_unreadable_documents_are_stored_without_a_body(tmp_path):
    client = FakeClient({"approve": [summary("1", readable=False), summary("2")]})

    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        result = sync_documents(client, store, FOLDERS, form_filter=None)
        documents, overtime, without_body = store.counts()
        titles = store.connection.execute(
            "SELECT document_id FROM documents WHERE body_available = 0"
        ).fetchall()

    assert result.withheld == 1
    assert (documents, overtime, without_body) == (2, 1, 1)
    assert [row[0] for row in titles] == ["1"]


def test_a_readable_listing_wins_over_a_withheld_one(tmp_path):
    client = FakeClient(
        {
            "approve": [summary("1", readable=False)],
            "dept-draft": [summary("1", readable=True, folder_key="dept-draft")],
        }
    )

    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        result = sync_documents(client, store, FOLDERS, form_filter=None)

    assert result.withheld == 0
    assert client.fetched == ["1"]


def test_dry_run_reports_how_many_bodies_will_be_withheld(tmp_path):
    client = FakeClient({"approve": [summary("1", readable=False), summary("2")]})

    with ApprovalStore(tmp_path / "db.sqlite3") as store:
        result = sync_documents(client, store, FOLDERS, form_filter=None, dry_run=True)

    assert result.matched == 2
    assert result.withheld == 1
