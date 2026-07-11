# TODO 注释汇总

> 生成时间：自动扫描
> 范围：本项目所有 `.py` 文件

---

## `eval/tasks.py`

| 行号 | 注释 |
|------|------|
| 32 | `TODO[Day3] 再补一条"你组领域"的任务判据（下面 _check_domain）` |

## `prompt/render.py`

| 行号 | 注释 |
|------|------|
| 20 | `TODO[optional] 校对你所用模型的真实特殊标记！拼错一个 token，模型行为就会跑偏。` |
| 31 | `TODO[optional] 设计一个清晰的工具说明格式，并约定模型用` |
| 48 | `TODO[optional] 把 tools 说明并入 system 段` |
| 49 | `TODO[optional] 逐条 message 用 ROLE_TOKENS 包裹拼接` |
| 50 | `TODO[optional] 末尾以 assistant 起始标记结尾，提示模型开始生成` |
| 56 | `TODO[optional] 用正则/状态机提取所有 <tool_call>...</tool_call>，json.loads 出 name/arguments` |

## `skills/loader.py`

| 行号 | 注释 |
|------|------|
| 32 | `TODO[Day6] 解析 YAML frontmatter（name/description）+ 正文 body` |
| 46 | `TODO[Day6] 渲染成一段文本，放进系统提示词` |

## `tools/fs.py`

| 行号 | 注释 |
|------|------|
| 17 | `TODO[Day4] 读取文件，超长截断并提示；带行号更利于后续 edit 定位` |
| 25 | `TODO[Day4] 写文件；注意权限层（Day7）后续会拦截工作目录外的写入` |

## `tools/more_tools.py`

| 行号 | 注释 |
|------|------|
| 3 | `每个工具上午讲设计权衡，下午实现。这里只给签名与 TODO，便于你拆到独立文件。` |
| 24 | `TODO[Day4] 先实现最稳的 search-replace（old 在文件中唯一时替换为 new）` |
| 60 | `TODO[Day4] 调用系统 rg，返回匹配行（带文件名+行号）。与 glob 互补：grep 搜内容，glob 搜路径` |
| 72 | `TODO[Day4] 用 pathlib.Path().glob / rglob 找路径` |
| 78 | `TODO[Day4] httpx 抓取 -> markdownify 转 markdown -> 截断到预算内` |
| 84 | `TODO[Day4] 维护一个结构化待办（add/update/complete），作为模型的 scratchpad` |

## `tools/base.py`

| 行号 | 注释 |
|------|------|
| 62 | `TODO[Day4] 取消注释并实现：` |
| 68 | `TODO[Day4] 再加入完整工具集（→ v1 里程碑）：` |
| 73 | `TODO[Day4] 再加入：` |

## `tools/shell.py`

| 行号 | 注释 |
|------|------|
| 20 | `TODO[Day4] subprocess 执行，捕获 stdout/stderr/returncode，超时保护` |
| 21 | `TODO[Day7] 接入权限层 + 沙箱（bwrap/firejail/docker），危险命令需确认` |

## `mcp/client.py`

| 行号 | 注释 |
|------|------|
| 28 | `TODO[Day5] 启动子进程，stdin/stdout 接管，做 initialize 握手` |
| 32 | `TODO[Day5] 发一条 JSON-RPC 请求（带自增 id），读回对应响应` |
| 36 | `TODO[Day5] 调 tools/list，返回工具描述列表` |
| 40 | `TODO[Day5] 调 tools/call，返回结果文本` |

## `agent/prompts.py`

| 行号 | 注释 |
|------|------|
| 25 | `TODO[Day4] 在此补充：工具列表说明、正/负面示例、领域相关的行为约束。` |
| 26 | `TODO[Day4] 长任务时引导模型使用 task_list 维护待办。` |

## `agent/cli.py`

| 行号 | 注释 |
|------|------|
| 38 | `print("\n下一步：按 dayNN 的 lab-guide 填 # TODO 标记。")`（代码中的 TODO 提示） |

## `agent/loop.py`

| 行号 | 注释 |
|------|------|
| 43 | `TODO[Day4] 分发并执行工具，把每个结果作为 role="tool" 注入 messages：` |
| 49 | `TODO[Day4] 加错误恢复（try/except，把异常文本作为 observation，让模型自我修复）` |
| 54 | `TODO[Day4] 在这里做上下文管理：超出 token 预算时触发 compaction（见 agent/context.py）` |

## `agent/context.py`

| 行号 | 注释 |
|------|------|
| 15 | `TODO[Day4] 粗估即可（字符数/4 或用 tokenizer 精确数）` |
| 23 | `TODO[Day4] 实现 compaction：` |

---

## 统计

| 维度 | 数量 |
|------|------|
| 涉及文件数 | **12** |
| TODO 总数 | **30** |
| 主要集中阶段 | Day4（16 条）、Day5（4 条）、Day6（2 条）、Day7（1 条）、Optional（6 条） |
