## 插件简介

群聊任务管家（GroupTaskBoard），用于在群聊中记录、查询、完成、删除、催办和导出任务清单。任务按群隔离存储，重启后不丢失。

## 安装方法

1. 将插件目录放入 `plugins/group_task_board`。
2. 复制 `config.json.template` 为 `config.json`（可选）。
3. 启动项目后，可在 `plugins/plugins.json` 中启用/禁用插件。

## 配置方法

`config.json` 配置示例：

```json
{
  "enabled": true,
  "auto_parse_group_task": false,
  "max_tasks_show": 10,
  "allow_private_chat": true,
  "export_format": "markdown",
  "timezone": "Asia/Shanghai"
}
```

## 使用命令

- 记录任务：张三今晚整理开源许可证部分，李四明天中午前写安全风险分析
- 任务列表 / 查看任务 / 待办列表 / 群任务 / 我的任务
- 完成任务 #1
- 删除任务 #2
- 催办任务
- 导出任务
- 任务帮助

## 示例对话

用户：记录任务：张三今晚整理开源许可证部分，李四明天中午前写安全风险分析
机器人：已创建 2 个群任务：

用户：任务列表
机器人：当前群任务：...

用户：完成任务 #1
机器人：已完成任务 #1：整理开源许可证部分

## 数据存储位置

- SQLite 数据库：`plugins/group_task_board/data/tasks.db`

## 注意事项

- 默认仅在明确命令触发时处理消息，避免误触发。
- 任务按群聊 `group_id` 隔离。
- 任务编号不存在时会提示确认编号。
