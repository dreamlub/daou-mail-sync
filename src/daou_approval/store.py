from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

from .models import ApprovalDocument, DocumentSummary, OvertimeFields

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    doc_num TEXT NOT NULL,
    form_name TEXT NOT NULL,
    title TEXT NOT NULL,
    drafter_name TEXT NOT NULL,
    drafter_dept_name TEXT NOT NULL,
    drafted_at TEXT NOT NULL,
    completed_at TEXT,
    doc_status TEXT NOT NULL,
    doc_status_name TEXT NOT NULL,
    attach_count INTEGER NOT NULL,
    body_html TEXT NOT NULL,
    body_text TEXT NOT NULL,
    body_available INTEGER NOT NULL,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS document_folders (
    document_id TEXT NOT NULL,
    folder_key TEXT NOT NULL,
    PRIMARY KEY (document_id, folder_key),
    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS approval_steps (
    document_id TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    activity_type TEXT NOT NULL,
    actor_name TEXT NOT NULL,
    actor_position TEXT NOT NULL,
    actor_dept TEXT NOT NULL,
    status TEXT NOT NULL,
    acted_at TEXT,
    opinion TEXT NOT NULL,
    PRIMARY KEY (document_id, step_order),
    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS overtime_orders (
    document_id TEXT PRIMARY KEY,
    target_name TEXT NOT NULL,
    shift_hours TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    period_raw TEXT NOT NULL,
    extended_minutes INTEGER,
    night_minutes INTEGER,
    total_minutes INTEGER,
    reason TEXT NOT NULL,
    form_layout TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_form ON documents(form_name, drafted_at);
CREATE INDEX IF NOT EXISTS idx_overtime_start ON overtime_orders(start_date);
"""


class ApprovalStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SCHEMA)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.connection.close()

    def needs_fetch(self, summary: DocumentSummary) -> bool:
        """Re-fetch only when the document is new or its status has moved on."""
        row = self.connection.execute(
            "SELECT doc_status FROM documents WHERE document_id = ?",
            (summary.document_id,),
        ).fetchone()
        return row is None or str(row[0]) != summary.doc_status

    def note_folder(self, document_id: str, folder_key: str) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO document_folders(document_id, folder_key) VALUES (?, ?)",
                (document_id, folder_key),
            )

    def record(self, document: ApprovalDocument) -> None:
        summary = document.summary
        fetched_at = datetime.now(UTC).isoformat()
        with self.connection:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO documents(
                    document_id, doc_num, form_name, title, drafter_name, drafter_dept_name,
                    drafted_at, completed_at, doc_status, doc_status_name, attach_count,
                    body_html, body_text, body_available, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    summary.document_id,
                    summary.doc_num,
                    summary.form_name,
                    summary.title,
                    summary.drafter_name,
                    summary.drafter_dept_name,
                    summary.drafted_at,
                    summary.completed_at,
                    summary.doc_status,
                    summary.doc_status_name,
                    summary.attach_count,
                    document.body_html,
                    document.body_text,
                    int(document.body_available),
                    fetched_at,
                ),
            )
            self.connection.execute(
                "INSERT OR IGNORE INTO document_folders(document_id, folder_key) VALUES (?, ?)",
                (summary.document_id, summary.folder_key),
            )
            self.connection.execute(
                "DELETE FROM approval_steps WHERE document_id = ?", (summary.document_id,)
            )
            self.connection.executemany(
                """
                INSERT INTO approval_steps(
                    document_id, step_order, activity_type, actor_name, actor_position,
                    actor_dept, status, acted_at, opinion
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        summary.document_id,
                        step.order,
                        step.activity_type,
                        step.actor_name,
                        step.actor_position,
                        step.actor_dept,
                        step.status,
                        step.acted_at,
                        step.opinion,
                    )
                    for step in document.steps
                ],
            )
            if document.overtime is not None:
                fields = document.overtime
                self.connection.execute(
                    """
                    INSERT OR REPLACE INTO overtime_orders(
                        document_id, target_name, shift_hours, start_date, end_date,
                        start_time, end_time, period_raw, extended_minutes, night_minutes,
                        total_minutes, reason, form_layout
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        summary.document_id,
                        fields.target_name,
                        fields.shift_hours,
                        fields.start_date,
                        fields.end_date,
                        fields.start_time,
                        fields.end_time,
                        fields.overtime_period_raw,
                        fields.extended_minutes,
                        fields.night_minutes,
                        fields.total_minutes,
                        fields.reason,
                        fields.form_layout,
                    ),
                )

    def get_meta(self, key: str) -> str | None:
        row = self.connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, value)
            )

    def stored_bodies(self) -> list[tuple[str, str, str]]:
        """Every downloaded body, so an improved parser can be re-applied offline."""
        return [
            (str(row[0]), str(row[1]), str(row[2]))
            for row in self.connection.execute(
                "SELECT document_id, form_name, body_html FROM documents "
                "WHERE body_available = 1 AND body_html <> ''"
            )
        ]

    def replace_overtime(self, document_id: str, fields: OvertimeFields) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT OR REPLACE INTO overtime_orders(
                    document_id, target_name, shift_hours, start_date, end_date,
                    start_time, end_time, period_raw, extended_minutes, night_minutes,
                    total_minutes, reason, form_layout
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    fields.target_name,
                    fields.shift_hours,
                    fields.start_date,
                    fields.end_date,
                    fields.start_time,
                    fields.end_time,
                    fields.overtime_period_raw,
                    fields.extended_minutes,
                    fields.night_minutes,
                    fields.total_minutes,
                    fields.reason,
                    fields.form_layout,
                ),
            )

    def counts(self) -> tuple[int, int, int]:
        documents = self.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        overtime = self.connection.execute("SELECT COUNT(*) FROM overtime_orders").fetchone()[0]
        withheld = self.connection.execute(
            "SELECT COUNT(*) FROM documents WHERE body_available = 0"
        ).fetchone()[0]
        return int(documents), int(overtime), int(withheld)
