# encoding:utf-8

import os
import tempfile
import unittest
from datetime import datetime

from plugins import PluginManager

PluginManager().current_plugin_path = os.path.join("plugins", "group_task_board")

from plugins.group_task_board.task_parser import TaskParser
from plugins.group_task_board.task_store import TaskStore
from plugins.group_task_board.time_parser import parse_due_text

PluginManager().current_plugin_path = None


class GroupTaskBoardCoreTest(unittest.TestCase):
    def test_parse_multiple_tasks(self):
        parser = TaskParser("Asia/Shanghai")
        tasks = parser.parse_tasks(
            "张三今晚整理开源许可证部分，李四明天中午前写安全风险分析，我负责最后汇总",
            creator_id="u1",
            creator_name="测试用户",
        )

        self.assertEqual(len(tasks), 3)
        self.assertEqual(tasks[0]["assignee_name"], "张三")
        self.assertEqual(tasks[0]["due_text"], "今晚")
        self.assertIn("整理开源许可证", tasks[0]["content"])
        self.assertEqual(tasks[1]["assignee_name"], "李四")
        self.assertEqual(tasks[1]["due_text"], "明天中午前")
        self.assertEqual(tasks[2]["assignee_id"], "u1")

    def test_time_parser(self):
        now = datetime(2026, 5, 30, 10, 0)
        due_text, due_at, _, _ = parse_due_text("张三今晚整理材料", now=now)
        self.assertEqual(due_text, "今晚")
        self.assertIn("20:00:00", due_at)

        due_text, due_at, _, _ = parse_due_text("李四明天中午前写报告", now=now)
        self.assertEqual(due_text, "明天中午前")
        self.assertIn("12:00:00", due_at)

        due_text, due_at, _, _ = parse_due_text("王五5月10日前完成PPT", now=now)
        self.assertEqual(due_text, "5月10日前")
        self.assertIn("2027-05-10", due_at)

    def test_store_lifecycle_and_session_isolation(self):
        temp_root = os.path.join(os.getcwd(), "plugins", "group_task_board", "data")
        with tempfile.TemporaryDirectory(dir=temp_root) as tmpdir:
            store = TaskStore(os.path.join(tmpdir, "tasks.db"), "Asia/Shanghai")
            scope_a = {
                "session_id": "group-a",
                "group_id": "group-a",
                "group_name": "A群",
                "creator_id": "u1",
                "creator_name": "张三",
                "channel": "test",
            }
            scope_b = dict(scope_a, session_id="group-b", group_id="group-b")
            task = {
                "assignee_id": None,
                "assignee_name": "张三",
                "content": "写 README",
                "due_text": "今晚",
                "due_at": None,
                "priority": "normal",
            }

            created, error = store.add_tasks(scope_a, [task], "raw")
            self.assertIsNone(error)
            self.assertEqual(len(created), 1)

            tasks_a, error = store.list_tasks("group-a", status="pending")
            self.assertIsNone(error)
            self.assertEqual(len(tasks_a), 1)

            tasks_b, error = store.list_tasks("group-b", status="pending")
            self.assertIsNone(error)
            self.assertEqual(tasks_b, [])

            completed, error = store.complete_task(created[0]["id"], "group-a")
            self.assertIsNone(error)
            self.assertEqual(completed["status"], "completed")

            pending, _ = store.list_tasks("group-a", status="pending")
            self.assertEqual(pending, [])

            deleted, error = store.delete_task(created[0]["id"], "group-a")
            self.assertIsNone(error)
            self.assertIsNotNone(deleted["deleted_at"])

            exported, _ = store.export_tasks("group-a")
            self.assertEqual(exported, [])


if __name__ == "__main__":
    unittest.main()
