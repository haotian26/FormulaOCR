"""Local, durable recognition history for FormulaOCR."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

try:  # The Tauri sidecar must also run without importing the Qt GUI layer.
    from PySide6.QtCore import QStandardPaths
except ImportError:  # pragma: no cover - exercised by sidecar environments
    QStandardPaths = None  # type: ignore[assignment,misc]


DEFAULT_HISTORY_LIMIT = 200


@dataclass(frozen=True)
class HistoryRecord:
    id: str
    created_at: float
    updated_at: float
    image_path: str
    local_raw_latex: str
    local_formatted_latex: str
    local_draft_latex: str
    local_render_error: str | None
    api_raw_latex: str | None
    api_formatted_latex: str | None
    api_draft_latex: str | None
    api_profile_name: str | None
    api_model: str | None
    api_render_error: str | None
    active_source: str
    recognition_mode: str

    @property
    def has_api(self) -> bool:
        return bool(self.api_draft_latex)


class HistoryStore:
    """SQLite metadata plus copied PNGs; all operations are local and synchronous."""

    def __init__(self, root: Path | None = None, limit: int = DEFAULT_HISTORY_LIMIT) -> None:
        if root is None:
            base = (
                QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
                if QStandardPaths is not None
                else str(Path.home() / "Library" / "Application Support" / "FormulaOCR")
            )
            root = Path(base) / "history" if base else Path.home() / "Library" / "Application Support" / "FormulaOCR" / "history"
        self.root = Path(root)
        self.images_dir = self.root / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.database_path = self.root / "history.sqlite3"
        self._limit = max(20, min(2000, int(limit)))
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(str(self.database_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    @property
    def limit(self) -> int:
        return self._limit

    def close(self) -> None:
        self._connection.close()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS history (
                id TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                image_path TEXT NOT NULL,
                local_raw_latex TEXT NOT NULL,
                local_formatted_latex TEXT NOT NULL DEFAULT '',
                local_draft_latex TEXT NOT NULL,
                local_render_error TEXT,
                api_raw_latex TEXT,
                api_formatted_latex TEXT,
                api_draft_latex TEXT,
                api_profile_name TEXT,
                api_model TEXT,
                api_render_error TEXT,
                active_source TEXT NOT NULL DEFAULT 'local',
                recognition_mode TEXT NOT NULL DEFAULT 'chemistry'
            );
            CREATE INDEX IF NOT EXISTS history_updated_idx ON history(updated_at DESC);
            """
        )
        existing = {
            str(row[1]) for row in self._connection.execute("PRAGMA table_info(history)").fetchall()
        }
        migrations = {
            "local_formatted_latex": "ALTER TABLE history ADD COLUMN local_formatted_latex TEXT NOT NULL DEFAULT ''",
            "api_formatted_latex": "ALTER TABLE history ADD COLUMN api_formatted_latex TEXT",
            "recognition_mode": "ALTER TABLE history ADD COLUMN recognition_mode TEXT NOT NULL DEFAULT 'chemistry'",
        }
        for column, statement in migrations.items():
            if column not in existing:
                self._connection.execute(statement)
        self._connection.execute(
            "UPDATE history SET local_formatted_latex=local_draft_latex WHERE local_formatted_latex=''"
        )
        self._connection.commit()

    @staticmethod
    def _record(row: sqlite3.Row) -> HistoryRecord:
        return HistoryRecord(**dict(row))

    def _write_image(self, record_id: str, image_png: bytes) -> Path:
        target = self.images_dir / f"{record_id}.png"
        fd, temporary = tempfile.mkstemp(prefix=f".{record_id}-", suffix=".png", dir=self.images_dir)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(image_png)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise
        return target

    def create_local(
        self,
        image_png: bytes,
        *,
        local_raw_latex: str,
        local_formatted_latex: str,
        local_draft_latex: str,
        local_render_error: str | None,
        recognition_mode: str = "chemistry",
    ) -> HistoryRecord:
        record_id = uuid.uuid4().hex
        now = time.time()
        image_path = self._write_image(record_id, image_png)
        try:
            self._connection.execute(
                """INSERT INTO history
                (id, created_at, updated_at, image_path, local_raw_latex, local_formatted_latex,
                 local_draft_latex, local_render_error, active_source, recognition_mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'local', ?)""",
                (record_id, now, now, str(image_path), local_raw_latex, local_formatted_latex,
                 local_draft_latex, local_render_error, recognition_mode),
            )
            self._connection.commit()
            self.prune()
        except Exception:
            self._connection.rollback()
            image_path.unlink(missing_ok=True)
            raise
        return self.get(record_id)  # type: ignore[return-value]

    def update_api(
        self,
        record_id: str,
        *,
        api_raw_latex: str,
        api_formatted_latex: str,
        api_draft_latex: str,
        api_profile_name: str,
        api_model: str,
        api_render_error: str | None,
    ) -> HistoryRecord | None:
        now = time.time()
        cursor = self._connection.execute(
            """UPDATE history SET updated_at=?, api_raw_latex=?, api_formatted_latex=?, api_draft_latex=?,
               api_profile_name=?, api_model=?, api_render_error=?, active_source='api'
               WHERE id=?""",
            (now, api_raw_latex, api_formatted_latex, api_draft_latex, api_profile_name,
             api_model, api_render_error, record_id),
        )
        self._connection.commit()
        return self.get(record_id) if cursor.rowcount else None

    def update_draft(self, record_id: str, source: str, draft_latex: str) -> None:
        if source not in {"local", "api"}:
            return
        column = "local_draft_latex" if source == "local" else "api_draft_latex"
        self._connection.execute(
            f"UPDATE history SET updated_at=?, {column}=? WHERE id=?",  # column is allow-listed above
            (time.time(), draft_latex, record_id),
        )
        self._connection.commit()

    def set_active_source(self, record_id: str, source: str) -> None:
        if source not in {"local", "api"}:
            return
        self._connection.execute(
            "UPDATE history SET updated_at=?, active_source=? WHERE id=?",
            (time.time(), source, record_id),
        )
        self._connection.commit()

    def set_recognition_mode(self, record_id: str, mode: str) -> None:
        if mode not in {"chemistry", "math"}:
            return
        self._connection.execute(
            "UPDATE history SET updated_at=?, recognition_mode=? WHERE id=?",
            (time.time(), mode, record_id),
        )
        self._connection.commit()

    def get(self, record_id: str) -> HistoryRecord | None:
        row = self._connection.execute("SELECT * FROM history WHERE id=?", (record_id,)).fetchone()
        return self._record(row) if row is not None else None

    def list_records(self) -> list[HistoryRecord]:
        rows = self._connection.execute("SELECT * FROM history ORDER BY updated_at DESC").fetchall()
        return [self._record(row) for row in rows]

    def delete(self, record_id: str) -> bool:
        record = self.get(record_id)
        if record is None:
            return False
        self._connection.execute("DELETE FROM history WHERE id=?", (record_id,))
        self._connection.commit()
        Path(record.image_path).unlink(missing_ok=True)
        return True

    def delete_many(self, record_ids: list[str]) -> int:
        removed = 0
        for record_id in dict.fromkeys(record_ids):
            removed += int(self.delete(record_id))
        return removed

    def delete_all(self) -> int:
        records = self.list_records()
        self._connection.execute("DELETE FROM history")
        self._connection.commit()
        for record in records:
            Path(record.image_path).unlink(missing_ok=True)
        return len(records)

    def set_limit(self, limit: int) -> int:
        self._limit = max(20, min(2000, int(limit)))
        self.prune()
        return self._limit

    def prune(self) -> int:
        rows = self._connection.execute(
            "SELECT id, image_path FROM history ORDER BY updated_at DESC LIMIT -1 OFFSET ?",
            (self._limit,),
        ).fetchall()
        if not rows:
            return 0
        ids = [str(row[0]) for row in rows]
        self._connection.executemany("DELETE FROM history WHERE id=?", [(record_id,) for record_id in ids])
        self._connection.commit()
        for row in rows:
            Path(str(row[1])).unlink(missing_ok=True)
        return len(rows)
