# encoding:utf-8

import json
import os
import re
from datetime import datetime

import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from plugins import *

from .task_parser import TaskParser
from .task_store import TaskStore


@plugins.register(
    name="GroupTaskBoard",
    desire_priority=10,
    namecn="群聊任务管家",
    desc="群聊任务记录与管理",
    version="1.0",
    author="cowagent",
)
class GroupTaskBoard(Plugin):
    def __init__(self):
        super().__init__()
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        self.config = super().load_config()
        if not self.config:
            self.config = self._load_config_template()
        if not self.config:
            self.config = {}
        self.tz_name = self.config.get("timezone", "Asia/Shanghai")
        db_path = os.path.join(self.path, "data", "tasks.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.store = TaskStore(db_path, self.tz_name)
        self.parser = TaskParser(self.tz_name)
        logger.debug("[GroupTaskBoard] inited")

    def on_handle_context(self, e_context: EventContext):
        context = e_context["context"]
        if context.type != ContextType.TEXT:
            return

        content = (context.content or "").strip()
        if not content:
            return

        is_group = bool(context.get("isgroup", False))
        if not is_group and not self.config.get("allow_private_chat", True):
            return

        command = self._match_command(content)
        if not command:
            if is_group and self.config.get("auto_parse_group_task"):
                if self._looks_like_task_message(content):
                    self._handle_add(e_context, content, allow_raw=True)
            return

        if command == "help":
            self._set_reply(e_context, self.get_help_text())
            return
        if command == "add":
            self._handle_add(e_context, content)
            return
        if command == "list":
            self._handle_list(e_context, content)
            return
        if command == "complete":
            self._handle_complete(e_context, content)
            return
        if command == "delete":
            self._handle_delete(e_context, content)
            return
        if command == "remind":
            self._handle_remind(e_context)
            return
        if command == "export":
            self._handle_export(e_context)
            return

    def get_help_text(self, **kwargs):
        return (
            "群聊任务管家使用说明：\n"
            "记录任务：张三今晚整理开源许可证部分，李四明天中午前写安全风险分析\n"
            "任务列表 / 查看任务 / 待办列表 / 群任务 / 我的任务\n"
            "完成任务 #1\n"
            "删除任务 #1\n"
            "催办任务\n"
            "导出任务\n"
            "任务帮助"
        )

    def _handle_add(self, e_context: EventContext, content: str, allow_raw: bool = False):
        raw_message = content
        payload = self._strip_add_prefix(content)
        if payload is None:
            if allow_raw:
                payload = content.strip()
            else:
                self._set_reply(e_context, "请提供任务内容。")
                return

        creator_id, creator_name = self._get_creator_info(e_context)
        group_id, group_name = self._get_group_info(e_context)
        if not group_id:
            self._set_reply(e_context, "无法识别当前会话，请稍后再试。")
            return

        tasks = self.parser.parse_tasks(payload, creator_id, creator_name)
        if not tasks:
            self._set_reply(e_context, "未识别到有效任务，请检查格式。")
            return

        results, error = self.store.add_tasks(
            group_id,
            group_name,
            creator_id,
            creator_name,
            tasks,
            raw_message,
        )
        if error:
            self._set_reply(e_context, "任务保存失败，请稍后再试。")
            return

        lines = [f"已创建 {len(results)} 个群任务：", ""]
        for task in results:
            assignee = self._display_assignee(task, creator_id, creator_name, use_me=True)
            due_text = self._format_due(task)
            lines.extend([
                f"#{task['id']} {assignee}：{task['content']}",
                f"截止时间：{due_text}",
                "状态：未完成",
                "",
            ])
        reply_text = "\n".join(lines).strip()
        self._set_reply(e_context, reply_text)

    def _handle_list(self, e_context: EventContext, content: str):
        group_id, _ = self._get_group_info(e_context)
        if not group_id:
            self._set_reply(e_context, "无法识别当前会话，请稍后再试。")
            return

        assignee_id = None
        assignee_name = None
        if "我的任务" in content:
            assignee_id, assignee_name = self._get_creator_info(e_context)

        limit = self.config.get("max_tasks_show", 10)
        tasks, error = self.store.list_tasks(
            group_id,
            status="pending",
            assignee_id=assignee_id,
            assignee_name=assignee_name,
            limit=limit,
        )
        if error:
            self._set_reply(e_context, "任务查询失败，请稍后再试。")
            return
        if not tasks:
            self._set_reply(e_context, "当前没有未完成任务。")
            return

        title = "当前群任务：" if e_context["context"].get("isgroup", False) else "当前任务："
        lines = [title, ""]
        for task in tasks:
            assignee = self._display_assignee(task)
            status = "未完成" if task.get("status") != "completed" else "已完成"
            due_text = self._format_due(task)
            lines.extend([
                f"#{task['id']} {assignee}｜{status}｜{due_text}",
                f"{task['content']}",
                "",
            ])
        reply_text = "\n".join(lines).strip()
        self._set_reply(e_context, reply_text)

    def _handle_complete(self, e_context: EventContext, content: str):
        task_id = self._extract_task_id(content)
        if not task_id:
            self._set_reply(e_context, "请提供任务编号，例如：完成任务 #1")
            return

        group_id, _ = self._get_group_info(e_context)
        if not group_id:
            self._set_reply(e_context, "无法识别当前会话，请稍后再试。")
            return
        task, error = self.store.complete_task(task_id, group_id)
        if error:
            self._set_reply(e_context, "任务更新失败，请稍后再试。")
            return
        if not task:
            self._set_reply(e_context, f"没有找到任务 #{task_id}，请确认任务编号是否正确。")
            return

        self._set_reply(e_context, f"已完成任务 #{task_id}：{task.get('content')}")

    def _handle_delete(self, e_context: EventContext, content: str):
        task_id = self._extract_task_id(content)
        if not task_id:
            self._set_reply(e_context, "请提供任务编号，例如：删除任务 #1")
            return

        group_id, _ = self._get_group_info(e_context)
        if not group_id:
            self._set_reply(e_context, "无法识别当前会话，请稍后再试。")
            return
        task, error = self.store.delete_task(task_id, group_id)
        if error:
            self._set_reply(e_context, "任务删除失败，请稍后再试。")
            return
        if not task:
            self._set_reply(e_context, f"没有找到任务 #{task_id}，请确认任务编号是否正确。")
            return

        self._set_reply(e_context, f"已删除任务 #{task_id}：{task.get('content')}")

    def _handle_remind(self, e_context: EventContext):
        group_id, _ = self._get_group_info(e_context)
        if not group_id:
            self._set_reply(e_context, "无法识别当前会话，请稍后再试。")
            return

        limit = self.config.get("max_tasks_show", 10)
        tasks, error = self.store.list_tasks(group_id, status="pending", limit=limit)
        if error:
            self._set_reply(e_context, "任务查询失败，请稍后再试。")
            return
        if not tasks:
            self._set_reply(e_context, "当前没有需要催办的任务。")
            return

        now = self._now_in_timezone()
        urgent = []
        normal = []
        for task in tasks:
            due_at = self._parse_due_at(task.get("due_at"))
            if due_at and (due_at <= now or due_at.date() == now.date()):
                urgent.append(task)
            else:
                normal.append(task)

        lines = ["任务催办提醒：", ""]
        if urgent:
            lines.append("即将到期 / 已过期：")
            for task in urgent:
                assignee = self._display_assignee(task)
                due_text = self._format_due(task)
                lines.append(f"#{task['id']} {assignee}：{task['content']}｜截止：{due_text}")
            lines.append("")
        if normal:
            lines.append("其他未完成：")
            for task in normal:
                assignee = self._display_assignee(task)
                due_text = self._format_due(task)
                lines.append(f"#{task['id']} {assignee}：{task['content']}｜截止：{due_text}")
        reply_text = "\n".join(lines).strip()
        self._set_reply(e_context, reply_text)

    def _handle_export(self, e_context: EventContext):
        group_id, _ = self._get_group_info(e_context)
        if not group_id:
            self._set_reply(e_context, "无法识别当前会话，请稍后再试。")
            return

        tasks, error = self.store.export_tasks(group_id)
        if error:
            self._set_reply(e_context, "任务导出失败，请稍后再试。")
            return
        if not tasks:
            self._set_reply(e_context, "当前没有可导出的任务。")
            return

        header = "| 任务编号 | 负责人 | 任务内容 | 截止时间 | 状态 | 创建时间 | 完成时间 |"
        sep = "| --- | --- | --- | --- | --- | --- | --- |"
        rows = [header, sep]
        for task in tasks:
            assignee = self._display_assignee(task)
            due_text = self._format_due(task)
            status = "已完成" if task.get("status") == "completed" else "未完成"
            created_at = self._format_datetime(task.get("created_at"))
            completed_at = self._format_datetime(task.get("completed_at"))
            rows.append(
                f"| #{task['id']} | {assignee} | {task['content']} | {due_text} | {status} | {created_at} | {completed_at} |"
            )
        reply_text = "\n".join(rows)
        self._set_reply(e_context, reply_text)

    def _strip_add_prefix(self, content: str):
        text = content.strip()
        if text.startswith("记录任务"):
            return self._strip_colon(text[len("记录任务"):].strip())
        if text.startswith("添加任务"):
            return self._strip_colon(text[len("添加任务"):].strip())
        if text.startswith("任务："):
            return text.split("：", 1)[1].strip()
        if text.startswith("任务:"):
            return text.split(":", 1)[1].strip()
        return None

    def _strip_colon(self, text: str):
        if text.startswith("："):
            return text[1:].strip()
        if text.startswith(":"):
            return text[1:].strip()
        return text.strip()

    def _match_command(self, content: str):
        text = content.strip()
        lower = text.lower()

        if text in ("任务帮助",) or lower in ("group task help", "/task help"):
            return "help"
        if self._is_complete_command(text, lower):
            return "complete"
        if self._is_delete_command(text, lower):
            return "delete"
        if any(k in text for k in ("催办任务", "催一下未完成任务", "提醒未完成任务")):
            return "remind"
        if any(k in text for k in ("导出任务", "导出群任务", "导出任务表")):
            return "export"
        if text in ("任务列表", "查看任务", "待办列表", "群任务") or "我的任务" in text:
            return "list"
        if text.startswith("记录任务") or text.startswith("添加任务") or text.startswith("任务：") or text.startswith("任务:"):
            return "add"
        return None

    def _is_complete_command(self, text: str, lower: str):
        if re.search(r"\bdone\b", lower) and re.search(r"#?\d+", lower):
            return True
        if "完成" in text and re.search(r"#?\d+", text):
            return True
        if "完成任务" in text and re.search(r"#?\d+", text):
            return True
        return False

    def _is_delete_command(self, text: str, lower: str):
        if "删除任务" in text or "移除任务" in text or "delete" in lower:
            return bool(re.search(r"#?\d+", text))
        return False

    def _extract_task_id(self, content: str):
        match = re.search(r"#(\d+)", content)
        if match:
            return int(match.group(1))
        match = re.search(r"(完成|删除|移除|done|delete)\s*(\d+)", content, re.IGNORECASE)
        if match:
            return int(match.group(2))
        return None

    def _looks_like_task_message(self, content: str):
        if re.search(r"(今天|明天|后天|周[一二三四五六日天]|\d{1,2}月\d{1,2}日|\d{1,2}[:：]\d{2}|\d{1,2}点)", content):
            return True
        if re.search(r"(负责|整理|完成|写|做|提交|跟进|处理|修复|优化|设计|测试|汇总|修改)", content):
            return True
        return False

    def _get_creator_info(self, e_context: EventContext):
        context = e_context["context"]
        msg = context.get("msg")
        if context.get("isgroup", False):
            creator_id = getattr(msg, "actual_user_id", None) or getattr(msg, "from_user_id", None)
            creator_name = getattr(msg, "actual_user_nickname", None) or getattr(msg, "from_user_nickname", None)
        else:
            creator_id = getattr(msg, "from_user_id", None)
            creator_name = getattr(msg, "from_user_nickname", None)
        return creator_id, creator_name

    def _get_group_info(self, e_context: EventContext):
        context = e_context["context"]
        msg = context.get("msg")
        if context.get("isgroup", False):
            group_id = getattr(msg, "other_user_id", None) or context.get("session_id")
            group_name = getattr(msg, "other_user_nickname", None)
        else:
            group_id = getattr(msg, "from_user_id", None) or context.get("session_id")
            group_name = getattr(msg, "from_user_nickname", None)
        return group_id, group_name

    def _display_assignee(self, task: dict, creator_id: str = None, creator_name: str = None, use_me: bool = False):
        name = task.get("assignee_name") or "未指定"
        if use_me and creator_id and task.get("assignee_id") == creator_id:
            return "我"
        if creator_name and name == creator_name and use_me:
            return "我"
        return name

    def _format_due(self, task: dict):
        if task.get("due_text"):
            return task.get("due_text")
        due_at = self._parse_due_at(task.get("due_at"))
        if due_at:
            return due_at.strftime("%Y-%m-%d %H:%M")
        return "未指定"

    def _parse_due_at(self, value: str):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None

    def _format_datetime(self, value: str):
        if not value:
            return ""
        dt = self._parse_due_at(value)
        if not dt:
            return value
        return dt.strftime("%Y-%m-%d %H:%M")

    def _now_in_timezone(self):
        try:
            from zoneinfo import ZoneInfo

            return datetime.now(ZoneInfo(self.tz_name))
        except Exception:
            return datetime.now().astimezone()

    def _set_reply(self, e_context: EventContext, content: str):
        reply = Reply()
        reply.type = ReplyType.TEXT
        reply.content = content
        e_context["reply"] = reply
        e_context.action = EventAction.BREAK_PASS

    def _load_config_template(self):
        try:
            plugin_config_path = os.path.join(self.path, "config.json.template")
            if os.path.exists(plugin_config_path):
                with open(plugin_config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.exception(e)
        return None
