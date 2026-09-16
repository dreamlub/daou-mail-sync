from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Self

import requests

from .body import parse_cells, parse_overtime
from .models import ApprovalDocument, ApprovalStep, DocumentSummary, Folder

DEFAULT_PAGE_SIZE = 100
REQUEST_TIMEOUT = 30


class DaouApprovalError(RuntimeError):
    """The DaouOffice web API refused or could not satisfy a request."""


class DocumentNotReadable(DaouApprovalError):
    """This account may see the document in a list but not open it."""


class DaouApprovalClient:
    """Read-only client for the DaouOffice approval web API.

    It speaks the same JSON endpoints the approval SPA uses, so nothing is scraped
    beyond the document body, which DaouOffice only ever renders as HTML.
    """

    def __init__(self, tenant: str, *, session: requests.Session | None = None) -> None:
        host = tenant if "://" in tenant else f"https://{tenant}"
        self.base_url = host.rstrip("/")
        self.session = session or requests.Session()
        # The portal API works out which tenant is being asked from the Referer, not
        # from the Host header. Without it every call fails with PORTAL-0047.
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Referer": f"{self.base_url}/",
                "X-Referer-Info": self.base_url,
            }
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.session.close()

    # -- authentication ---------------------------------------------------

    def company_id(self) -> str:
        payload = self._get_json("/api/portal/public/auth/company")
        companies = (payload.get("data") or {}).get("companyList") or []
        if not companies:
            raise DaouApprovalError("DaouOffice returned no company for this tenant")
        return str(companies[0]["companyId"])

    def login(self, login_id: str, password: str, *, company_id: str | None = None) -> None:
        """Establish a session cookie. Never retries: repeated failures arm a captcha."""
        body = {
            "companyId": company_id or self.company_id(),
            "loginId": login_id,
            "password": password,
            "captcha": "",
            "locale": "ko",
        }
        response = self.session.post(
            f"{self.base_url}/api/portal/public/auth/login",
            json=body,
            headers={"Content-Type": "application/json", "X-Referer-Info": self.base_url},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code >= 400:
            raise DaouApprovalError(self._login_failure(response))
        payload = response.json()
        if str(payload.get("resultCode", "0")) not in {"0", "200"} and payload.get("code") not in (
            None,
            "200",
        ):
            raise DaouApprovalError(self._login_failure(response))
        self.session.get(f"{self.base_url}/gw/app/approval", timeout=REQUEST_TIMEOUT)

    @staticmethod
    def _login_failure(response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return f"DaouOffice login failed with HTTP {response.status_code}"
        code = str(payload.get("errorCode") or payload.get("code") or response.status_code)
        if "CAPTCHA" in code.upper() or payload.get("captchaRequired"):
            return (
                "DaouOffice is now demanding a captcha for this account. "
                "Sign in once in a browser to clear it, then retry."
            )
        return f"DaouOffice login failed ({code})"

    def verify_session(self) -> None:
        self._get_json("/gw/api/approval/side")

    # -- discovery --------------------------------------------------------

    def department_ids(self) -> list[str]:
        payload = self._get_json("/gw/api/approval/side")
        data = payload.get("data") or {}
        seen: list[str] = []
        for key in ("deptFolders", "drafterDeptFolders"):
            for entry in data.get(key) or []:
                dept_id = str(entry.get("deptId") or "")
                if dept_id and dept_id not in seen:
                    seen.append(dept_id)
        return seen

    # -- listing ----------------------------------------------------------

    def list_folder(
        self, folder: Folder, *, page_size: int = DEFAULT_PAGE_SIZE, max_pages: int = 200
    ) -> Iterator[DocumentSummary]:
        for page in range(max_pages):
            params: dict[str, Any] = {
                "page": page,
                "offset": page_size,
                "property": folder.sort_property,
                "direction": "desc",
                "searchtype": "",
                "keyword": "",
            }
            if folder.supports_duration:
                params |= {"fromDate": "", "toDate": "", "duration": "all"}
            payload = self._get_json(f"/gw/api/approval/{folder.path}", params=params)
            rows = payload.get("data") or []
            if not isinstance(rows, list) or not rows:
                return
            for row in rows:
                if row.get("documentId"):
                    yield DocumentSummary.from_payload(row, folder.key)
            if len(rows) < page_size:
                return

    # -- detail -----------------------------------------------------------

    def fetch_document(self, summary: DocumentSummary, *, overtime: bool) -> ApprovalDocument:
        """Fetch a body, or return a metadata-only record when access is withheld.

        Roughly one document in twenty is listed but not openable; the list row
        already flags it as `readable: false`, which has matched the server's 403
        exactly, so the request is skipped rather than spent.
        """
        if not summary.readable:
            return ApprovalDocument(
                summary=summary, body_html="", body_text="", steps=(), overtime=None,
                body_available=False,
            )
        try:
            payload = self._get_json(f"/gw/api/approval/document/{summary.document_id}")
        except DocumentNotReadable:
            return ApprovalDocument(
                summary=summary, body_html="", body_text="", steps=(), overtime=None,
                body_available=False,
            )
        data = payload.get("data") or {}
        document = data.get("document") or {}
        body_html = str(document.get("docBodyContent") or "")
        if overtime:
            fields, body_text = parse_overtime(body_html)
        else:
            fields, (_, body_text) = None, parse_cells(body_html)
        return ApprovalDocument(
            summary=summary,
            body_html=body_html,
            body_text=body_text,
            steps=tuple(_approval_steps(data)),
            overtime=fields,
        )

    # -- plumbing ---------------------------------------------------------

    def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict:
        response = self.session.get(
            f"{self.base_url}{path}", params=params, timeout=REQUEST_TIMEOUT
        )
        if response.status_code == 401:
            raise DaouApprovalError("DaouOffice session is not authenticated")
        if response.status_code == 403:
            raise DocumentNotReadable(f"GET {path} was refused: 사용 권한이 없습니다")
        if response.status_code >= 400:
            raise DaouApprovalError(f"GET {path} failed with HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as error:
            raise DaouApprovalError(f"GET {path} did not return JSON") from error
        if not isinstance(payload, dict):
            raise DaouApprovalError(f"GET {path} returned an unexpected payload")
        return payload


def _approval_steps(data: dict) -> Iterator[ApprovalStep]:
    groups = ((data.get("apprFlow") or {}).get("activityGroups")) or []
    order = 0
    for group in groups:
        for activity in group.get("activities") or []:
            yield ApprovalStep(
                order=order,
                activity_type=str(activity.get("type") or ""),
                actor_name=str(activity.get("userName") or ""),
                actor_position=str(activity.get("userPosition") or ""),
                actor_dept=str(activity.get("deptName") or ""),
                status=str(activity.get("statusName") or activity.get("status") or ""),
                acted_at=activity.get("completedAt") or None,
                opinion=str(activity.get("comment") or ""),
            )
            order += 1
