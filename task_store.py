# encoding:utf-8

import sqlite3
import threading
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

from common.log import logger


class TaskStore:
    def __init__(self, db_path: str, tz_name: str = "Asia/Shanghai"):
        self.db_path = db_path
        self.tz_name = tz_name
        self._lock = threading.RLock()
        self._init_db()

    def add_tasks(self, group_id: str, group_name: str, creator_id: str, creator_name: str, tasks: list, raw_message: str):
        now = self._now_iso()
        results = []
        if not tasks:
            return results, None
        try:
            with self._lock:
                conn = self._connect()
                try:
                    cursor = conn.cursor()
                    for task in tasks:
                        cursor.execute(
                            """
                            INSERT INTO tasks (
                                group_id, group_name, creator_id, creator_name,
                                assignee_id, assignee_name, content, due_text, due_at,
                                status, priority, raw_message, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                group_id,
                                group_name,
                                creator_id,
                                creator_name,
                                task.get("assignee_id"),
                                task.get("assignee_name"),
                                task.get("content"),
                                task.get("due_text"),
                                task.get("due_at"),
                                "pending",
                                task.get("priority", "normal"),
                                raw_message,
                                now,
                                now,
                            ),
                        )
                        task_id = cursor.lastrowid
                        results.append({
                            "id": task_id,
                            "assignee_id": task.get("assignee_id"),
                            "assignee_name": task.get("assignee_name"),
                            "content": task.get("content"),
                            "due_text": task.get("due_text"),
                            "due_at": task.get("due_at"),
                            "status": "pending",
                        })
                    conn.commit()
                finally:
                    conn.close()
            return results, None
        except Exception as e:
            logger.exception("[GroupTaskBoard] add_tasks failed")
            return None, str(e)

    def list_tasks(self, group_id: str, status: str = None, assignee_id: str = None, assignee_name: str = None, limit: int = None):
        try:
            with self._lock:
                conn = self._connect()
                try:
                    sql = "SELECT * FROM tasks WHERE group_id = ? AND deleted_at IS NULL"
                    params = [group_id]
                    if status:
                        sql += " AND status = ?"
                        params.append(status)
                    if assignee_id or assignee_name:
                        sql += " AND (assignee_id = ? OR assignee_name = ?)"
                        params.append(assignee_id)
                        params.append(assignee_name)
                    sql += " ORDER BY (due_at IS NULL) ASC, due_at ASC, id ASC"
                    if limit:
                        sql += " LIMIT ?"
                        params.append(limit)
                    rows = conn.execute(sql, params).fetchall()
                    return [self._row_to_dict(row) for row in rows], None
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("[GroupTaskBoard] list_tasks failed")
            return None, str(e)

    def get_task(self, task_id: int, group_id: str):
        try:
            with self._lock:
                conn = self._connect()
                try:
                    row = conn.execute(
                        "SELECT * FROM tasks WHERE id = ? AND group_id = ? AND deleted_at IS NULL",
                        (task_id, group_id),
                    ).fetchone()
                    return self._row_to_dict(row) if row else None, None
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("[GroupTaskBoard] get_task failed")
            return None, str(e)

    def complete_task(self, task_id: int, group_id: str):
        task, error = self.get_task(task_id, group_id)
        if error or not task:
            return None, error
        if task.get("status") == "completed":
            return task, None
        now = self._now_iso()
        try:
            with self._lock:
                conn = self._connect()
                try:
                    conn.execute(
                        """
                        UPDATE tasks
                        SET status = ?, completed_at = ?, updated_at = ?
                        WHERE id = ? AND group_id = ? AND deleted_at IS NULL
                        """,
                        ("completed", now, now, task_id, group_id),
                    )
                    conn.commit()
                finally:
                    conn.close()
            task["status"] = "completed"
            task["completed_at"] = now
            task["updated_at"] = now
            return task, None
        except Exception as e:
            logger.exception("[GroupTaskBoard] complete_task failed")
            return None, str(e)

    def delete_task(self, task_id: int, group_id: str):
        task, error = self.get_task(task_id, group_id)
        if error or not task:
            return None, error
        now = self._now_iso()
        try:
            with self._lock:
                conn = self._connect()
                try:
                    conn.execute(
                        """
                        UPDATE tasks
                        SET deleted_at = ?, updated_at = ?
                        WHERE id = ? AND group_id = ? AND deleted_at IS NULL
                        """,
                        (now, now, task_id, group_id),
                    )
                    conn.commit()
                finally:
                    conn.close()
            task["deleted_at"] = now
            task["updated_at"] = now
            return task, None
        except Exception as e:
            logger.exception("[GroupTaskBoard] delete_task failed")
            return None, str(e)

    def export_tasks(self, group_id: str):
        try:
            with self._lock:
                conn = self._connect()
                try:
                    rows = conn.execute(
                        "SELECT * FROM tasks WHERE group_id = ? AND deleted_at IS NULL ORDER BY id ASC",
                        (group_id,),
                    ).fetchall()
                    return [self._row_to_dict(row) for row in rows], None
                finally:
                    conn.close()
        except Exception as e:
            logger.exception("[GroupTaskBoard] export_tasks failed")
            return None, str(e)

    def _init_db(self):
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id TEXT NOT NULL,
                        group_name TEXT,
                        creator_id TEXT,
                        creator_name TEXT,
                        assignee_id TEXT,
                        assignee_name TEXT,
                        content TEXT NOT NULL,
                        due_text TEXT,
                        due_at TEXT,
                        status TEXT NOT NULL DEFAULT 'pending',
                        priority TEXT NOT NULL DEFAULT 'normal',
                        raw_message TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        completed_at TEXT,
                        deleted_at TEXT
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_group ON tasks(group_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_group_status ON tasks(group_id, status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(group_id, due_at)")
                conn.commit()
            finally:
                conn.close()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _row_to_dict(self, row):
        if not row:
            return None
        return dict(row)

    def _now_iso(self):
        tz = self._get_timezone()
        return datetime.now(tz).isoformat()

    def _get_timezone(self):
        if ZoneInfo:
            try:
                return ZoneInfo(self.tz_name)
            except Exception:
                pass
        return datetime.now().astimezone().tzinfo
