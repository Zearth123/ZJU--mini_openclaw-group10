# 项目记忆

## 约定

- 时间戳一律使用 UTC / ISO-8601
- 包管理器使用 pnpm，不要使用 npm
- Python 代码使用 4 空格缩进

## 常用命令

- 自检：`python -m agent.cli --selfcheck`
- 测试：`python -m pytest -q`
- 运行任务：`python -m agent.cli "任务描述"`

## 踩过的坑

- Windows 工作区与 Linux 虚拟机是两份代码，修改后需要同步对应文件
- 必须从项目根目录运行，确保 Python 能导入本地 `agent` 包

## 安全

- 不在记忆中保存 API Key、密码、访问令牌或个人隐私
