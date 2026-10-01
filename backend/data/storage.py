"""Zero-configuration SQLite persistence for investigator actions (M19)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ALLOWED_ACTIONS = frozenset(
    {
        "monitor",
        "investigate",
        "escalate",
        "dismiss",
        "mark_legitimate",
        "confirm_abuse",
    }
)


class InvestigationStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._memory: sqlite3.Connection | None = None
        if self.path == ":memory:":
            self._memory = sqlite3.connect(":memory:")
            self._memory.row_factory = sqlite3.Row
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._memory is not None:
            return self._memory
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS investigation_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ring_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.commit()
        finally:
            if connection is not self._memory:
                connection.close()

    def add(self, ring_id: str, action: str, note: str = "") -> dict[str, Any]:
        if action not in ALLOWED_ACTIONS:
            raise ValueError(f"unsupported investigator action: {action}")
        created_at = datetime.now(timezone.utc).isoformat()
        connection = self._connect()
        try:
            cursor = connection.execute(
                "INSERT INTO investigation_actions (ring_id, action, note, created_at) VALUES (?, ?, ?, ?)",
                (ring_id, action, note, created_at),
            )
            connection.commit()
            return {
                "id": int(cursor.lastrowid),
                "ring_id": ring_id,
                "action": action,
                "note": note,
                "created_at": created_at,
            }
        finally:
            if connection is not self._memory:
                connection.close()

    def list(self, ring_id: str | None = None) -> list[dict[str, Any]]:
        connection = self._connect()
        try:
            if ring_id is None:
                rows = connection.execute(
                    "SELECT * FROM investigation_actions ORDER BY id"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM investigation_actions WHERE ring_id = ? ORDER BY id",
                    (ring_id,),
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            if connection is not self._memory:
                connection.close()
