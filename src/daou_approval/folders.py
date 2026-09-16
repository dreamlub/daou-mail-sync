from __future__ import annotations

from .models import Folder

# Verified against the requests the DaouOffice approval SPA itself issues.
# Each box insists on its own sort property; sending the wrong one returns HTTP 500.
PERSONAL_FOLDERS: tuple[Folder, ...] = (
    Folder("draft", "개인 기안 문서함", "doclist/draft/all", "draftedAt"),
    Folder("approve", "개인 결재 문서함", "doclist/approve/all", "draftedAt"),
    Folder("viewer", "개인 참조/열람 문서함", "doclist/viewer/all", "document.draftedAt"),
    Folder("reception", "개인 수신 문서함", "doclist/reception/waiting", "receivedAt", False),
    Folder("send", "개인 발송 문서함", "doclist/send/all", "createdAt"),
    Folder("userofficial", "개인 공문 문서함", "doclist/userofficial/all", "document.completedAt"),
)

# `{dept_id}` is filled in from the departments reported by /gw/api/approval/side.
DEPARTMENT_FOLDERS: tuple[Folder, ...] = (
    Folder("dept-draft", "부서 기안 완료함", "deptfolder/draft/{dept_id}", "draftedAt"),
    Folder("dept-reference", "부서 참조함", "deptfolder/reference/{dept_id}", "document.draftedAt"),
    Folder(
        "dept-receive",
        "부서 수신함",
        "deptfolder/receive/{dept_id}/waiting",
        "receivedAt",
        False,
    ),
    Folder("dept-official", "부서 공문 발송함", "deptfolder/official/{dept_id}", "isEmergency", False),
)

# 임시 저장함 is deliberately absent: it holds drafts that were never submitted, so the
# rows carry no approval status and no document number.

ALL_FOLDER_KEYS: tuple[str, ...] = tuple(
    folder.key for folder in (*PERSONAL_FOLDERS, *DEPARTMENT_FOLDERS)
)


def resolve_folders(dept_ids: list[str], keys: list[str] | None = None) -> list[Folder]:
    """Expand the folder catalogue for the departments this account can see."""
    wanted = set(keys) if keys else None
    resolved: list[Folder] = [
        folder
        for folder in PERSONAL_FOLDERS
        if wanted is None or folder.key in wanted
    ]
    for dept_id in dept_ids:
        resolved.extend(
            folder.with_department(dept_id)
            for folder in DEPARTMENT_FOLDERS
            if wanted is None or folder.key in wanted
        )
    if wanted is not None:
        unknown = wanted - set(ALL_FOLDER_KEYS)
        if unknown:
            raise ValueError(f"unknown folder keys: {', '.join(sorted(unknown))}")
    return resolved
