# mini-OpenClaw 实验框架分析

> 本文档对当前仓库进行完整分析，涵盖整体架构、模块职责、数据流与每份代码的用途。

---

## 一、项目定位

mini-OpenClaw 是一个**教学用 CLI Agent 骨架项目**，模仿 Claude Code 的架构，让学生用 10 天逐步实现一个完整的**命令行智能体（Agent）**。其核心模式是 **ReAct 循环**：接收用户自然语言指令 → 调用大模型后端 → 模型输出工具调用 → 主循环执行工具 → 结果反馈回模型 → 直至任务完成。

**技术栈：**
- **后端大脑**：DeepSeek API（OpenAI 兼容协议），非流式调用
- **语言**：纯 Python 3.11，无 ML 框架依赖（无 torch/vllm/peft）
- **工具复用**：httpx（API 调用）、pydantic（校验）、markdownify（HTML→Markdown）
- **系统工具**：ripgrep（grep 搜索）

---

## 二、目录全景

```
mini-openclaw/
├── agent/           # 主循环、系统提示、上下文管理、domain模型
│   ├── cli.py           # 命令行入口
│   ├── loop.py          # ReAct 主循环（核心引擎）
│   ├── prompts.py       # 系统提示词
│   ├── context.py       # 上下文压缩/截断（token 预算）
│   ├── planning.py      # Todo 清单 + 重试逻辑
│   ├── permissions.py   # 权限检查层
│   ├── memory.py        # 持久化记忆（读/写 MEMORY.md）
│   └── event_project.py # 活动策划领域 Pydantic 模型
│
├── backend/         # LLM 后端封装
│   ├── client.py        # DeepSeek API 官方客户端
│   ├── fake_backend.py  # 离线假后端（无 key 时打通管道）
│   ├── server.py        # （已弃用）本地部署占位
│   └── images.py        # 多模态图片预处理
│
├── prompt/          # 手动 prompt 渲染（本课程改用 API 原生 tools）
│   └── render.py        # render_prompt / parse_tool_calls
│
├── tools/           # 工具抽象与实现
│   ├── base.py          # Tool/ToolRegistry 核心抽象 + 默认注册表
│   ├── fs.py            # read / write
│   ├── shell.py         # bash（bwrap 沙箱 + 降级检查）
│   ├── more_tools.py    # edit / grep / glob / web_fetch
│   ├── planning.py      # todo_write / update_todo
│   ├── memory.py        # remember
│   ├── activity_budget.py    # calculate_budget
│   ├── activity_schedule.py  # build_schedule
│   ├── activity_validate.py  # validate_project
│   ├── security.py      # 外部数据安全标记工具
│   └── external.py      # 不可信内容包装器
│
├── mcp/             # MCP 客户端（可插拔外部工具）
│   ├── client.py        # 最小 MCP 客户端（stdio + JSON-RPC）
│   └── echo_server.py   # 自写 echo 测试 server
│
├── skills/          # 技能加载器
│   ├── loader.py        # SKILL.md 解析与扫描
│   └── example-skill/
│       └── SKILL.md     # CSV 快速报告 skill 示例
│
├── eval/            # 评测与消融
│   ├── tasks.py         # 任务定义 + 成功判据
│   ├── metrics.py       # 指标（成功率、步数、token、JSON 合法率）
│   ├── tracer.py        # 轨迹记录器（JSONL）
│   ├── judge.py         # LLM-as-judge 评分
│   ├── ablation.py      # 消融实验（有/无 system-prompt）
│   └── ablation_notes.md # 消融笔记
│
├── data/            # 活动策划领域产出
│   ├── event_project.json   # 项目 JSON 数据
│   ├── activity_plan.md     # 活动策划方案文档
│   └── previous-plan.md     # 往年策划案（继承参考）
│
├── tests/           # 单元测试
│   ├── test_activity_tools.py   # 预算/排期/校验工具测试
│   └── test_planning_tools.py   # Todo 工具测试
│
├── demo_m2.py       # M2 阶段演示脚本
├── CLAUDE.md        # Claude Code 配置指南
├── requirements.txt # Python 依赖
└── analysis.md      # 本文件
```

---

## 三、数据流架构

```
用户请求（自然语言）
      │
      ▼
┌─────────────────────────────────────────────────────┐
│  agent/cli.py                                       │
│    ┌─ 解析命令行参数                                │
│    └─ 装配环境：ToolRegistry + MCP + Skills + Memory │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  AgentLoop.run()                  agent/loop.py      │
│                                                      │
│  for _step in range(max_turns):                      │
│      ┌─ 注入 Todo 清单到 system message              │
│      ├─ backend.chat(messages, schemas)  ◄─────────────── 调用 DeepSeek
│      ├─ 将 assistant 回复追加到 messages             │
│      ├─ if 无 tool_calls → return content（结束）    │
│      ├─ for 每个 tool_call:                            │
│      │   ├─ permissions.check() → allow/confirm/deny │
│      │   ├─ tool.run(**args)        ◄── 执行真实操作  │
│      │   └─ 结果 + 进度检测追加回 messages            │
│      ├─ maybe_compact() → token 超预算时压缩          │
│      └─ 检测重复动作/无进展 → 注入 replan 提示        │
└─────────────────────────────────────────────────────┘
```

**关键设计点：**
1. **模型从不直接调用函数**——它只生成 `<tool_call>{"name":..., "arguments":{...}}</tool_call>` 文本
2. **主循环（AgentLoop）** 负责解析这个文本、查注册表找到对应 Tool、执行 run()、把结果（observation）注入下一轮消息
3. **权限层**在工具执行前介入：越界写入 → deny，危险操作 → confirm，安全操作 → allow

---

## 四、模块详解

### 1. `agent/` — 智能体的"身体"

#### `cli.py` — 命令行入口
- **作用**：解析 `--selfcheck`（自检）、`--trace`（记录轨迹）、`--replay-trace`（回放轨迹）、`--auto-approve`（自动批准）、`--verbose`（详细输出）等参数
- **初始化流程**：建 ToolRegistry → 启动 MCP 客户端 → 加载 Skills → 读取 Memory → 构建 AgentLoop → 执行任务
- **关键设计**：自动降级——优先使用 `DeepSeekBackend`，无 API Key 时回退 `FakeBackend`

#### `loop.py` — ReAct 主循环（核心）
- **AgentLoop.run()**：40 步上限，每步：
  1. 注入 Todo 状态到 system message
  2. 调用 `backend.chat(messages, tools=schemas)`
  3. 解析模型输出，检测重复动作（≥3 次相同调用 → 注入 replan 提示）
  4. 遍历每个 tool_call：权限检查 → 执行 → 结果截断 → 追加到 messages
  5. Todo 进度检测（无进展 ≥4 步 → 注入 replan 提示，新完成子任务 → 注入反思提示）
  6. `maybe_compact()` 控制上下文预算
- **领域观察者（_domain_observation）**：对预算/排期/校验三个领域工具做特殊处理，自动更新 `EventProject` 状态
- **Todo 阻塞检测**：同一子任务失败 3 次 → 自动标记 blocked

#### `prompts.py` — 系统提示词
- 定义 Agent 的角色、工具用法规则、活动策划领域约束
- 硬性约束：交付文件必须为 `event_project.json` 和 `activity_plan.md`（根目录），三次校验上限等

#### `context.py` — 上下文管理
- `estimate_tokens()`：按字符数/4 估算 token
- `maybe_compact()`：超预算（默认 6000 token）时用 LLM 对较早对话做摘要，保留最近 K 轮完整原文
- `truncate_observation()`：工具结果 >4000 字符时截断

#### `planning.py` — Todo 规划
- `TodoList`：待办清单的增/删/改/查/渲染，支持 pending/in_progress/completed/blocked 四种状态
- `with_retry()`：指数退避重试（最多 3 次），处理瞬时错误

#### `permissions.py` — 权限检查
- 基于工具的粒度分类：READONLY（自动允许）、WRITE/EXEC（需确认或拒绝）
- `_inside()` 检查路径是否在工作目录内（防止路径穿越）
- MCP 工具以 `mcp__` 为前缀，按操作类型（read/list → allow，其余 → confirm）

#### `memory.py` — 持久化记忆
- `Memory`：追加写入 `MEMORY.md`，全量读取
- `KVMemory`：JSON 文件 + key-value 结构，支持覆盖/删除

#### `event_project.py` — 活动策划 Pydantic 模型
- `EventBrief`、`EventPlan`、`PlanStage`、`EventProject` 完整领域模型
- 带默认值设计（如 `activity_type="待确定活动"`，`venue="校内教室"`），允许宽松初始化

---

### 2. `backend/` — LLM 后端

#### `client.py` — DeepSeek API 客户端
- `DeepSeekBackend.chat(messages, tools)` → 归一化的 `{role, content, tool_calls}`
- 兼容 OpenAI 协议：`_to_openai_messages()` 将内部格式转为 API 标准
- 支持多模态：`_to_openai_content()` 将 Anthropic 风格图片块转为 OpenAI `image_url`
- `_normalize()` 将 API 返回归一化为内部 `tool_calls` 格式（name + arguments）

#### `fake_backend.py` — 离线假后端
- 规则驱动：遇到工具结果 → 返回最终答复；遇到含关键词的用户输入 → 假装调一个工具
- 用于：未配 API Key 时离线跑通骨架、CI 环境测试

#### `images.py` — 图片预处理
- `image_block()`：读取图片 → EXIF 转正 → 超过 1568px 时缩略 → base64 编码
- `user_content()`：构建文本+图片的多模态 content block

---

### 3. `prompt/` — （本课程已弃用）

#### `render.py` — 手动 Prompt 渲染
> ⚠️ 本课程改为直接使用 DeepSeek 的工具调用 API，不再手动拼接 prompt
- `render_prompt()`：将 messages + tools 渲染成一段纯文本
- `parse_tool_calls()`：从模型输出中正则提取 `<tool_call>` 并解析 JSON

---

### 4. `tools/` — 工具系统

#### `base.py` — 核心抽象
- `Tool`：dataclass，含 `name`、`description`、`parameters`（JSON Schema）、`run()`
- `ToolRegistry`：多工具注册、查寻、生成 OpenAI-compatible schemas
- `build_default_registry()`：装配全部内置工具（13 个）

#### `fs.py` — 文件读写
- `read`：读取文件 + 行号 + 自动截断（100KB 上限）
- `write`：覆盖写入（后续由权限层做安全边界检查）

#### `shell.py` — Shell 执行
- `bash`：`bwrap` 沙箱隔离（只读系统 + 命名空间隔离 + 网络隔离），无 bwrap 时降级为黑名单拦截 + 路径穿越检查
- 黑名单：`rm -rf /`、`mkfs`、`dd if=` 等
- 超时控制（默认 30s），WSL 内核兼容（bwrap 不可用时静默降级）

#### `more_tools.py` — 扩展工具
- `edit`：search-replace 编辑（要求 old 片段在文件中唯一出现，防误改）
- `grep`：基于 ripgrep 的内容搜索
- `glob`：文件名通配匹配（递归查找）
- `web_fetch`：URL→Markdown（白名单域名、手动处理重定向防 SSRF）

#### `planning.py` & `memory.py` — Todo 和记忆工具
- `todo_write`：创建子任务清单
- `update_todo`：更新任务状态（pending/in_progress/completed/blocked）
- `remember`：写入持久化 MEMORY.md

#### `activity_budget.py` — 预算计算
- 严格的确定性计算：单价×数量→小计→分类汇总→备用金→总计→余额
- Decimal 精度控制（两位小数）
- 输入校验：非负、有限、合法数字

#### `activity_schedule.py` — 排期生成
- 拓扑排序（依赖关系解析），检测循环依赖
- 支持跨午夜（结束时间≤开始时间时自动+24h）
- 冲突检测：环节总长超过时间窗口 → warnings

#### `activity_validate.py` — 统一校验
- 校验维度：需求 brief、方案 plan、预算 budget、排期 schedule、人员 staffing、宣传 publicity、输出 outputs
- 78 个独立检查点（violations），按 severity=error/warning 分类
- 预算交叉校验：subtotal=Σ(单价×数量)、total=subtotal+reserve、remaining=limit-total

#### `external.py` — 外部内容安全包装
- `wrap_external()`：在文件/网页内容外包 `<external>` 标签，注入安全提示，防御 prompt injection

---

### 5. `mcp/` — MCP 可插拔工具

#### `client.py` — MCP 客户端
> ⚠️ 当前为骨架，`raise NotImplementedError`
- 设计目标：stdio transport → initialize 握手 → tools/list → tools/call → 透明合并到 ToolRegistry
- `register_mcp_tools()`：MCP 工具以 `mcp__` 前缀注册，避免与内置工具重名

#### `echo_server.py` — 测试 server
- 完整实现的最小 MCP server（echo 工具），用于先打通握手协议
- 支持：initialize、tools/list、tools/call

---

### 6. `skills/` — 技能系统

#### `loader.py` — 技能加载器
> ⚠️ `parse_skill_md()` 当前为骨架，`raise NotImplementedError`
- Skill 定义：dataclass 含 name/description/body/path
- `load_skills()`：扫描 `skills/` 下所有 `*/SKILL.md`
- `skills_catalog()`：生成模型可见的 skill 清单（name + description）
- Skill vs Tool 区别：Tool 是单次函数调用，Skill 是一包领域知识 + 操作流程（注入系统提示词）

#### `example-skill/SKILL.md` — CSV 快速报告示例
- YAML frontmatter（name/description）+ markdown 正文（步骤/注意事项/可用脚本）

---

### 7. `eval/` — 评测系统

#### `tasks.py` — 任务定义
- `Task`：含 name、instruction、check 函数（程序化成功判据）
- 三个示例任务：read-config、list-dir、activity-design（领域任务）
- 领域判据检查最终回复是否覆盖 6 大模块中 ≥3 个，且预算额 ≤ 1000

#### `metrics.py` — 指标计算
- `success_rate()`：成功率（check 通过的轨迹比例）
- `step_count()` / `token_count()`：步数和 token 消耗
- `json_valid_rate()`：JSON 解析合法率（衡量模型输出质量）

#### `tracer.py` — 轨迹记录
- `Tracer`：每步记录 timestamp、step 数、tool_calls、token 计数 → 写入 JSONL
- `replay()`：逐帧回放轨迹

#### `judge.py` — LLM-as-judge
- 使用 DeepSeek 作为评审，按 1-5 分给回答打分
- 评分维度：正确性 + 命中程度（忽略长度和辞藻）
- 输出格式：先理由，后 `分数: X`

#### `ablation.py` — 消融实验
- 简单 A/B：有 system-prompt vs 无 system-prompt
- 当前为构造样本（各 2 条），计划 Day4 后用真实轨迹

---

### 8. `data/` — 活动策划领域数据

| 文件 | 说明 |
|------|------|
| `event_project.json` | 书画社春季交流活动完整 JSON 数据（含 brief/plan/budget/schedule/staffing/publicity） |
| `activity_plan.md` | 对应的人可读 Markdown 策划方案（9 大章节） |
| `previous-plan.md` | 往年编程社方案，作为"继承"参考 |

#### 领域检查要点
- **继承分析**：从编程社方案继承框架，到书画社场景做 11 项调整
- **预算验证**：总支出 892 + 备用金 89.2 = 981.2 ≤ 1000，余额 18.8
- **排期验证**：14:00–17:00 共 180 分钟，核心 5 环节 + 签到和撤场
- **校验器**：通过 calculate_budget → build_schedule → validate_project 三工具联动

---

### 9. `tests/` — 单元测试

#### `test_activity_tools.py`（61 个断言，9 个测试用例）
- **BudgetTests**：含备用金计算、超预算、负价格拒绝
- **ScheduleTests**：依赖排序、循环依赖检测、跨午夜支持
- **ValidationTests**：完整项目校验通过、人员超限拦截、缺少风险不失败、时间窗口不匹配
- **IntegrationTests**：工具注册 + JSON 协议确认（budget/schedule/validate 三工具的输入输出格式）

#### `test_planning_tools.py`（7 个测试用例）
- Todo 的 CRUD：写入、更新状态（in_progress/completed/blocked）、重置、无效状态拒绝、不存在的 ID 拒绝

---

## 五、领域特色：活动策划 Agent

项目在通用 Agent 基础上引入了**活动策划领域**，表现为：

1. **确定性计算工具**：`calculate_budget`（预算）、`build_schedule`（排期）、`validate_project`（校验），都不是"AI 生成"而是纯算法
2. **严格协议**：Agent 必须原样保留工具的计算结果（不得重命名字段、不得自己重新计算）
3. **三次校验上限**：validate_project 最多调用 3 次，超限后强制报告未通过
4. **EventProject 状态机**：AgentLoop 内部维护 `EventProject` 对象，自动同步 budget/schedule 计算结果
5. **交付物路径约束**：必须写入当前目录根部的 `event_project.json` 和 `activity_plan.md`

---

## 六、构建节奏（10 天对照）

| Day | 模块 | 交付物 | 里程碑 |
|:---:|------|--------|:------:|
| 1–2 | `backend/` | DeepSeek API 连通 + Tool schema | 跑通 `--selfcheck` |
| 3 | `prompt/` | （已弃用，改用 API tools） | |
| 4–5 | `tools/fs.py`、`tools/shell.py` | read/write/bash | **v0.5** |
| 6 | `tools/more_tools.py`、`mcp/` | edit/grep/glob + MCP 客户端 | **v1** |
| 7 | `agent/context.py`、`tools/memory.py` | 上下文压缩、记忆持久化 | v2 |
| 8 | `mcp/client.py`（完整实现） | MCP 真实工具集成 | **v3** |
| 9 | `skills/` | Skill 加载 + 领域 Skill | 可扩展 |
| 10 | `agent/permissions.py`、`eval/` | 安全层 + 消融评测 | **final** |

---

## 七、关键设计决策总结

| 决策 | 选择 | 原因 |
|------|------|------|
| LLM 后端 | DeepSeek API（非本地） | 零 GPU 依赖，快速迭代 |
| 工具接口 | 文本协议（`<tool_call>`） | 不依赖特定厂商的函数调用能力 |
| 沙箱 | bwrap（优先）+ 黑名单降级 | 兼顾安全与兼容性（WSL/容器） |
| 权限模型 | 基于工具分类 + 路径检查 | 轻量、可扩展 |
| 上下文管理 | 自动摘要（LLM 压缩） | 延长有效记忆窗口 |
| 领域工具 | 确定性算法（非 AI 生成） | 保证预算/排期的精确可审计 |
| 轨迹记录 | JSONL 格式 | 可回放、可解析、适合批量评测 |
