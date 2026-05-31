# encoding:utf-8

import re

from .time_parser import parse_due_text

_SPLIT_PATTERN = re.compile(r"[，,;；、\n]+")

_TIME_PREFIX_PATTERN = re.compile(
    r"^\s*(今天|明天|后天|周[一二三四五六日天]|\d{1,2}月\d{1,2}日|\d{1,2}[:：]\d{2}|\d{1,2}点半|\d{1,2}点|今晚|今夜|上午|中午|下午|晚上)"
)

_VERB_PREFIXES = (
    "负责",
    "整理",
    "完成",
    "写",
    "做",
    "提交",
    "跟进",
    "处理",
    "修复",
    "优化",
    "设计",
    "测试",
    "准备",
    "汇总",
    "更新",
    "修改",
)


class TaskParser:
    def __init__(self, tz_name: str = "Asia/Shanghai"):
        self.tz_name = tz_name

    def parse_tasks(self, text: str, creator_id: str = None, creator_name: str = None):
        tasks = []
        for part in self._split_tasks(text):
            task = self._parse_single(part, creator_id, creator_name)
            if task:
                tasks.append(task)
        return tasks

    def _split_tasks(self, text: str):
        if not text:
            return []
        parts = _SPLIT_PATTERN.split(text)
        return [p.strip() for p in parts if p and p.strip()]

    def _parse_single(self, text: str, creator_id: str, creator_name: str):
        raw = text.strip()
        if not raw:
            return None

        due_text, due_at, start, end = parse_due_text(raw, self.tz_name)
        content_base = raw
        if due_text:
            content_base = (raw[:start] + raw[end:]).strip()

        assignee_name = None
        assignee_id = None
        content = content_base

        self_match = re.match(r"^\s*(我|本人|我来负责|我负责|我来)\s*", content_base)
        if self_match:
            assignee_name = creator_name or "我"
            assignee_id = creator_id
            content = content_base[self_match.end():].strip()
        else:
            if not _TIME_PREFIX_PATTERN.match(content_base):
                name_match = re.match(r"^\s*([A-Za-z0-9_\u4e00-\u9fa5]{1,12})\s*[:：]\s*(.*)$", content_base)
                if name_match:
                    assignee_name = name_match.group(1)
                    content = name_match.group(2).strip()
                else:
                    name_match = re.match(r"^\s*([A-Za-z0-9_\u4e00-\u9fa5]{1,12})\s*(.*)$", content_base)
                    if name_match:
                        name = name_match.group(1)
                        rest = name_match.group(2).strip()
                        rest_check = re.sub(r"^(前|之前)\s*", "", rest)
                        if self._looks_like_task_body(rest_check):
                            assignee_name = name
                            content = rest_check

        content = re.sub(r"^(前|之前)\s*", "", content).strip()
        content = content.strip(" ,，;；、")

        if assignee_name and creator_name and assignee_name == creator_name:
            assignee_id = creator_id

        if not content:
            content = raw

        return {
            "assignee_id": assignee_id,
            "assignee_name": assignee_name,
            "content": content,
            "due_text": due_text,
            "due_at": due_at,
        }

    def _looks_like_task_body(self, text: str):
        if not text:
            return False
        stripped = text.strip()
        if _TIME_PREFIX_PATTERN.match(stripped):
            return True
        if stripped.startswith(_VERB_PREFIXES):
            return True
        if stripped.lower().startswith("review"):
            return True
        return False
