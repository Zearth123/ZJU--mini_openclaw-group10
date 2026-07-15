# mini-OpenClaw（学生 starter 仓库）

> 你将在这 10 天里，把这个骨架填成一个能在命令行里干活的通用智能体。
> 每个模块里都有 `# TODO[DayN]` 标记，告诉你哪天该填哪里。

## 这是什么

mini-OpenClaw 是一个 Claude Code 式的命令行 Agent：
一个**主循环**反复调用**大模型后端**，模型输出**工具调用**（read/write/bash/…），
主循环执行工具、把结果喂回模型，直到任务完成。再叠加 **MCP**（可插拔外部工具）、
**Skills**（可加载领域能力）和**安全层**（权限/沙箱/注入防护）。

```
你的请求 ──► [主循环 loop.py] ──► [后端 server.py ──► 大模型]
                  ▲   │  模型输出 <tool_call>{...}</tool_call>
                  │   ▼
            tool result ◄── [工具分发：read/write/bash/edit/grep/...]
                              ├── 内置工具 (tools/)
                              ├── MCP 工具 (mcp/)
                              └── Skills (skills/)
```

## 目录结构与建设节奏

| 模块 | 你要做什么 | 哪天 |
|------|-----------|------|
| `backend/` | DeepSeek API 客户端（已给 `client.py`，配 key 即用）；Day2 连通后端 + 首个工具 schema | Day1–2 |
| `prompt/` | render_prompt(messages, tools) 对话模板渲染 + parse_tool_calls | Day3 |
| `agent/` | 系统提示词（Day2 起草，Day5 完善）、ReAct 主循环、上下文管理 | Day2, Day5, Day7 |
| `tools/` | read/write/bash → edit/grep/glob → web_fetch/task_list | Day5, Day6, Day7 |
| `mcp/` | 最小 MCP 客户端（stdio + JSON-RPC）| Day8 |
| `skills/` | Skills 加载器 + 你领域的 Skill | Day9 |
| `eval/` | 任务集 + 指标评测 + 消融 | Day7, Day10 |

> 逐日构建目标详见各 `course/dayNN/lab-guide.md`；`grep -rn "TODO\[Day" .` 可看全部施工点。
> 里程碑：**v1（Day6）** 端到端可用 · **v3（Day9）** 可扩展 · **终版（Day10）** 含安全层，Demo Day 展示（占总评 95%）。

## 快速开始

```bash
# 1. Python 环境（agent 侧不吃显存）
conda create -n openclaw python=3.11 && conda activate openclaw
pip install -r requirements.txt

# 2. 先跑通骨架的"假后端"自检（Day1 就能跑）
python -m agent.cli --selfcheck

# 3. 之后每天填对应模块，重跑相关入口
```

## 里程碑

- **v1（Day6）**：`python -m agent.cli "创建 hello.py 并运行输出当前时间"` 能完成。
- **v3（Day9）**：能加载 MCP server 工具 + 自定义 Skill。
- **终版（Day10）**：含安全层，Demo Day 现场任务。

## 约定

- 全程一个 git 仓库，**按 day 打 tag**（`v1`, `v3`, `final`）。
- 每个模块自带一个 `README.md`，记录你的设计决策（技术文档分数来源）。

## 活动策划领域接口

默认注册表包含三个确定性领域工具：

- `calculate_budget`：计算单项小计、备用金、总额、余额和超预算金额。
- `build_schedule`：按依赖排序活动环节，计算起止时间并检查时间窗口。
- `validate_project`：校验 `EventProject v1.0` 的需求、方案、预算、排期、人员和宣传字段。

活动策划不强制创建 Todo。主 Agent 直接按需求、方案、预算、排期、校验和修订流程推进；Todo 仅作为可选的长任务辅助能力。最终项目文件固定为 `event_project.json` 和 `activity_plan.md`。

```bash
# 领域工具和主框架自检
python -m agent.cli --selfcheck

# 记录并回放一次真实运行轨迹
python -m agent.cli "设计书画社春季活动，40人，3小时，预算1000元内" --trace traces/demo.jsonl
python -m agent.cli --replay-trace traces/demo.jsonl

# 运行回归测试
python -m pytest -q
```

写文件、执行命令和外部访问会请求确认；`--auto-approve` 仅用于受控演示，路径越界和危险命令仍会被拒绝。


## Web console

Build and start the local React/FastAPI console:

```bash
cd web
npm install
npm run build
cd ..

export MINIOPENCLAW_ACCESS_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export DEEPSEEK_API_KEY="your-key"  # optional; FakeBackend is used when absent
python3 -m backend.web_server
```

Open `http://127.0.0.1:8000` and enter the access token. The server binds
`0.0.0.0` by default for LAN use; set `MINIOPENCLAW_HOST=127.0.0.1` when
LAN access is not needed. Never expose this service to the public internet.


## Per-run outputs

Every Agent run writes planning artifacts into an isolated directory:

- CLI: output/YYYYMMDD-HHMMSS-<id>/
- Web: output/<run-id>/

The canonical files remain event_project.json and activity_plan.md inside
that directory. The output directory is ignored by Git. When WECHAT_APPID and
WECHAT_APPSECRET are configured, both CLI and Web runs register the WeChat
MCP tools; publish_markdown can create a draft or publish the Markdown file
from the current run directory.
