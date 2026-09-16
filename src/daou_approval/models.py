from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Folder:
    """One DaouOffice approval document box."""

    key: str
    name: str
    path: str
    sort_property: str
    supports_duration: bool = True

    def with_department(self, dept_id: str) -> Folder:
        return Folder(
            key=self.key,
            name=self.name,
            path=self.path.format(dept_id=dept_id),
            sort_property=self.sort_property,
            supports_duration=self.supports_duration,
        )


@dataclass(frozen=True, slots=True)
class DocumentSummary:
    """A row as returned by a doclist endpoint."""

    document_id: str
    doc_num: str
    form_name: str
    title: str
    drafter_name: str
    drafter_dept_name: str
    drafted_at: str
    completed_at: str | None
    doc_status: str
    doc_status_name: str
    attach_count: int
    readable: bool
    folder_key: str

    @classmethod
    def from_payload(cls, payload: dict, folder_key: str) -> DocumentSummary:
        return cls(
            document_id=str(payload["documentId"]),
            doc_num=str(payload.get("docNum") or ""),
            form_name=str(payload.get("formName") or ""),
            title=str(payload.get("title") or ""),
            drafter_name=str(payload.get("drafterName") or ""),
            drafter_dept_name=str(payload.get("drafterDeptName") or ""),
            drafted_at=str(payload.get("draftedAt") or ""),
            completed_at=payload.get("completedAt") or None,
            doc_status=str(payload.get("docStatus") or ""),
            doc_status_name=str(payload.get("docStatusName") or ""),
            attach_count=int(payload.get("attachCount") or 0),
            readable=payload.get("readable") is not False,
            folder_key=folder_key,
        )


@dataclass(frozen=True, slots=True)
class ApprovalStep:
    """One entry of the approval flow."""

    order: int
    activity_type: str
    actor_name: str
    actor_position: str
    actor_dept: str
    status: str
    acted_at: str | None
    opinion: str


@dataclass(frozen=True, slots=True)
class OvertimeFields:
    """Form values lifted out of an 초과근무명령서 body."""

    target_name: str = ""
    shift_hours: str = ""
    start_date: str = ""
    end_date: str = ""
    start_time: str = ""
    end_time: str = ""
    overtime_period_raw: str = ""
    extended_minutes: int | None = None
    night_minutes: int | None = None
    total_minutes: int | None = None
    reason: str = ""
    form_layout: str = ""


@dataclass(frozen=True, slots=True)
class ApprovalDocument:
    """A summary joined with everything the detail endpoint adds."""

    summary: DocumentSummary
    body_html: str
    body_text: str
    body_available: bool = True
    steps: tuple[ApprovalStep, ...] = field(default_factory=tuple)
    overtime: OvertimeFields | None = None
