from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Self


class SyncState:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                raw_hash TEXT PRIMARY KEY,
                gmail_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS source_copies (
                folder TEXT NOT NULL,
                uid_validity TEXT NOT NULL,
                uid TEXT NOT NULL,
                raw_hash TEXT NOT NULL,
                PRIMARY KEY (folder, uid_validity, uid),
                FOREIGN KEY (raw_hash) REFERENCES messages(raw_hash)
            );
            """
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.connection.close()

    def copied_uids(self, folder: str, uid_validity: str) -> set[str]:
        rows = self.connection.execute(
            "SELECT uid FROM source_copies WHERE folder = ? AND uid_validity = ?",
            (folder, uid_validity),
        )
        return {str(row[0]) for row in rows}

    def gmail_id_for_hash(self, raw_hash: str) -> str | None:
        row = self.connection.execute(
            "SELECT gmail_id FROM messages WHERE raw_hash = ?", (raw_hash,)
        ).fetchone()
        return str(row[0]) if row else None

    def record(
        self,
        *,
        folder: str,
        uid_validity: str,
        uid: str,
        raw_hash: str,
        gmail_id: str,
    ) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO messages(raw_hash, gmail_id) VALUES (?, ?)",
                (raw_hash, gmail_id),
            )
            self.connection.execute(
                """
                INSERT OR REPLACE INTO source_copies(folder, uid_validity, uid, raw_hash)
                VALUES (?, ?, ?, ?)
                """,
                (folder, uid_validity, uid, raw_hash),
            )
