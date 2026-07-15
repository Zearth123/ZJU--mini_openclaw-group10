---
name: activity-planning
description: 活动策划与项目管理技能。用于用户提出活动需求（如社团活动、校园活动、团建等），需要从零生成可执行、可校验、可落地的完整活动方案时使用。覆盖需求分析、历史参考、方案设计、预算计算、人员分工、时间排期、宣传文案、风险评估、文件输出和复盘框架。
---

# Activity Planning Skill

## Goal

根据用户提供的活动目标、预算、时间、人数和场地信息，生成可执行、可校验、可落地的完整活动项目方案，并输出结构化文件。

## 何时使用

- 用户说"帮我策划一个活动"、"设计一个方案"
- 用户说"参考去年的活动，设计今年的 xx 活动"
- 用户给出活动目标、预算、人数等约束条件
- 用户需要完整的策划书、预算表、分工表、排期表
- 用户需要活动回顾和复盘报告

## Required workflow

执行以下步骤，**必须严格按顺序**，每一步完成后才能进入下一步。

### Step 1：提取活动约束

从用户描述中提取关键信息，建立 `EventProject` 对象：

```json
{
  "event_id": "2026-activity-xxx",
  "title": "待定",
  "status": "DRAFT",
  "brief": {
    "goal": "",
    "target_audience": "",
    "participants": 0,
    "budget_limit": 0,
    "duration_minutes": 0,
    "preferred_date": "",
    "venue": "",
    "organizer": ""
  },
  "unknowns": []
}
```

对于用户没有提供的信息，采用以下策略（**优先询问用户，其次使用合理假设**）：
- 活动日期 → 询问用户
- 场地 → 假设校内免费场地
- 现有物资 → 询问或假设基础物资可用
- 参与者画像 → 从活动类型推断

在最终方案中**明确标注所有假设**。

### Step 2：搜索历史活动资料

调用文件搜索工具查找相关历史活动：

```
search_files / glob → 查找历史方案
read → 读取历史活动方案
read → 读取社团人员名单（如存在）
```

提取并记录：
- 历史活动的成功经验
- 过去出现的问题和教训
- 实际预算和支出
- 参与者反馈
- 常用的物资和供应商

### Step 3：判断信息完整性

检查必需信息是否已齐备：
- [ ] 活动目标（必需）
- [ ] 预计参与人数（必需）
- [ ] 预算上限（必需）
- [ ] 活动时长（必需）
- [ ] 目标人群（必需）
- [ ] 活动日期（推荐）
- [ ] 场地信息（推荐）

如果缺少关键信息，向用户提问补齐。

### Step 4：形成活动主题与目标

基于用户需求和历史资料，确定：
- 活动主题（简洁、有吸引力）
- 具体目标（2-3 条可衡量目标）
- 成功指标（参与人数、满意度、产出等）

从已有微信公众号 Skill 中获取标题建议：
- 如相关，调用 `wechat-title-generator` 的流程思路生成活动名称

### Step 5：设计完整活动流程

设计活动的主要环节和详细时间线：

```
活动流程表结构：
| 时间段       | 环节名称     | 内容说明     | 所需物资     | 负责人 |
| ------------ | ------------ | ------------ | ------------ | ------ |
| 13:30-13:50  | 签到入场     | 扫码签到     | 签到表       | 李四   |
```

设计时的检查要点：
- 是否有开场和结束环节
- 每个环节的时长是否合理
- 环节之间的衔接是否自然
- 是否有缓冲时间（建议总时长的 10%）
- 是否考虑了布置和撤场时间
- 同一人是否在同一时间被分配到两个任务

### Step 6：生成预算草案

列出所有预算项目，每个项目可包含以下字段：

```json
{
  "name": "宣纸",
  "category": "material",
  "unit_price": 3,
  "quantity": 100,
  "priority": "required",
  "price_status": "confirmed",
  "notes": ""
}
```

| 字段 | 说明 |
|------|------|
| `name` | 物资名称（必填） |
| `category` | 类别（必填） |
| `unit_price` | 单价（必填） |
| `quantity` | 数量（必填） |
| `priority` | `required` 必需 / `optional` 可选（建议填写） |
| `price_status` | `confirmed` 已确认价 / `estimated` 估价 / `pending_quote` 待询价（建议填写） |
| `notes` | 备注（可选） |

预算类别划分：
- `material` — 物资材料
- `publicity` — 宣传费用
- `food` — 餐饮茶歇
- `equipment` — 设备租赁
- `decoration` — 场地装饰
- `prize` — 奖品/纪念品
- `transport` — 交通
- `emergency` — 应急备用金（建议总预算 10%）

**必须包含应急备用金（reserve）**，比例建议 10%。

### Step 7：调用 `calculate_budget` 工具计算

将预算草案传入 **`calculate_budget`** 工具进行精确计算，**不要自己口头计算**。

参数格式：
```json
{
  "budget_limit": 1000,
  "reserve_ratio": 0.1,
  "items": [
    {"name": "宣纸", "category": "material", "unit_price": 3, "quantity": 100, "priority": "required"},
    {"name": "颜料", "category": "material", "unit_price": 50, "quantity": 4, "priority": "optional"}
  ]
}
```

返回值包含 `subtotal`、`reserve`、`total`、`remaining`、`over_budget`、`category_totals`、`warnings`。

如果 `over_budget` 为 `true`：
1. 分析最大支出项
2. 按以下优先级削减（从优先到不优先）：
   - 将 `priority: "optional"` 的项目删除
   - 纪念品/装饰品
   - 餐饮标准
   - 物资数量
   - 寻找免费替代方案
3. 修改后再次调用预算工具
4. 重复直到 `over_budget` 为 `false`

**关键**：必须让工具给出数字，模型只负责解释和决策。

### Step 8：生成活动排期

调用 **`build_schedule`** 工具生成活动当天时间表：

参数格式：
```json
{
  "event_start": "13:30",
  "event_end": "17:00",
  "buffer_minutes": 15,
  "stages": [
    {
      "stage_id": "checkin",
      "name": "签到入场",
      "duration_minutes": 20,
      "dependencies": [],
      "staff_required": 2
    },
    {
      "stage_id": "opening",
      "name": "开场介绍",
      "duration_minutes": 15,
      "dependencies": ["checkin"],
      "staff_required": 1
    }
  ]
}
```

注意：
- `stage_id` 是每个环节的唯一标识（必填）
- `dependencies` 是依赖的前置环节 ID 列表（数组，不依赖则传空数组）
- `staff_required` 是该环节需要的人数（必填）
- `buffer_minutes` 为缓冲时间，建议至少 15 分钟

工具会进行拓扑排序、检查循环依赖、计算起止时间，并返回 `fits_time_window`。

然后手动补充分工表：
- 每个任务指定负责人
- 每人承担任务数尽量均衡
- 按技能匹配分工
- 可参考历史资料中的人员名单

### Step 9：生成宣传文案

生成以下宣传素材（使用 `publicity-writing` 子 Skill 的指导原则）：
- 活动名称（吸引眼球）
- 公众号推文或招募文案
- 群通知文案
- 海报短文案
- 报名提醒话术

风格要求：
- 不同渠道使用不同语言风格
- 突出活动亮点
- 包含时间、地点、报名方式
- 禁止夸大和虚假承诺

### Step 10：生成风险预案

识别本次活动可能的风险，覆盖以下类别：

| 风险类别 | 示例 |
| -------- | ---- |
| 人员风险 | 主讲人临时缺席 |
| 场地风险 | 场地被占用 |
| 设备风险 | 投影仪故障 |
| 物资风险 | 物资未及时到货 |
| 天气风险 | 户外活动遇雨 |
| 安全风险 | 人员受伤 |
| 舆情风险 | 活动照片被不当传播 |
| 时间风险 | 环节超时 |
| 财务风险 | 实际支出超预算 |

每个风险至少包含：

| 字段 | 含义 |
| ---- | ---- |
| risk | 风险描述 |
| probability | 发生概率（高/中/低） |
| impact | 影响程度（严重/中等/轻微） |
| trigger | 触发信号 |
| prevention | 预防措施 |
| response | 应急处理方案 |
| owner | 责任人 |

### Step 11：调用 `validate_project` 工具校验

构造完整的 `EventProject` 对象，传入 **`validate_project`** 工具进行统一校验：

```json
{
  "project": {
    "brief": {
      "activity_type": "书画交流",
      "goal": "促进成员交流",
      "participants": 40,
      "budget_limit": 1000,
      "duration_minutes": 180,
      "event_start": "13:30",
      "event_end": "17:00",
      "venue": "活动中心 101"
    },
    "plan": {
      "theme": "春日墨韵",
      "objectives": ["提升书画技能", "促进交流"],
      "stages": [
        {"stage_id": "checkin", "name": "签到", "duration_minutes": 20, "dependencies": [], "staff_required": 2}
      ],
      "success_metrics": ["参与人数≥30", "满意度≥80%"]
    },
    "budget": {
      "items": [...],
      "subtotal": 500,
      "reserve": 50,
      "total": 550,
      "remaining": 450
    },
    "schedule": {
      "event_start": "13:30",
      "event_end": "17:00",
      "buffer_minutes": 15,
      "items": [...],
      "total_minutes": 180,
      "fits_time_window": true
    },
    "publicity": {
      "summary": "活动宣传摘要"
    },
    "outputs": {
      "event_project": {"path": "event_project.json"},
      "activity_plan": {"path": "activity_plan.md"}
    }
  }
}
```

工具检查的内容（校验规则）：
1. `brief` — 活动类型、目标、人数、预算、时长、起止时间、地点是否完整
2. `plan` — 主题、目标列表、活动环节、成功指标是否存在
3. `budget` — 预算小计是否等于单价×数量加总、total 是否等于 subtotal+reserve、是否超上限、余额计算是否正确
4. `schedule` — 起止时间是否与 brief 一致、是否通过时间窗口检查、环节是否与 plan 一致、是否有缓冲时间
5. `staffing` — 各环节人数是否一致、是否超过可用人数
6. `publicity` — 至少有一种宣传内容
7. `outputs` — 输出文件路径是否符合要求

工具返回格式：
```json
{
  "valid": false,
  "hard_checks": {
    "brief": true,
    "plan": true,
    "budget": false,
    "schedule": true,
    "staffing": true,
    "publicity": true,
    "outputs": true
  },
  "violations": [
    {
      "module": "budget",
      "severity": "error",
      "code": "BUDGET_EXCEEDED",
      "message": "总预算超过上限 120 元"
    }
  ]
}
```

`valid` 为 `false` 时（存在 `severity: "error"` 的违规）：
1. 逐条修复 violations 中的问题
2. 重新调用相关工具修正（预算重算、排期调整等）
3. 再次调用 `validate_project` 校验
4. 重复直到 `valid` 为 `true`

### Step 12：保存结构化文件


> è¿è¡Œæ—¶ä¼šæä¾›å”¯ä¸€çš„ output/<run-id>/ ç›®å½•ã€‚è¯·ä½¿ç”¨è§„èŒƒ basename
> event_project.json å’Œ activity_plan.md å†™å…¥ï¼Œæ–‡ä»¶å·¥å…·ä¼šè‡ªåŠ¨è·¯ç”±åˆ°æœ¬æ¬¡è¿è¡Œç›®å½•ã€‚
> EventProject.outputs ä¸­ä»åªä¿å­˜ basenameã€‚å¦‚éœ€å‘å¸ƒå…¬ä¼—å·ï¼Œ
> mcp__publish_markdown å¿…é¡»ä½¿ç”¨ write å·¥å…·è¿”å›žçš„å®žé™… output/<run-id>/... è·¯å¾„ã€‚

在活动目录下保存以下文件：

```text
activities/
└── 2026-activity-name/
    ├── brief.json              # 活动需求摘要
    ├── activity_plan.md        # 完整策划书
    ├── budget.json             # 预算原始数据
    ├── budget.md               # 预算报告
    ├── schedule.md             # 活动当天时间表
    ├── assignments.md          # 人员分工表
    ├── publicity.md            # 宣传文案
    ├── risk_plan.md            # 风险预案
    ├── checklist.md            # 执行检查清单
    └── retrospective_template.md  # 复盘模板
```

## 可用的参考模板

以下模板文件位于本 skill 目录下，执行时请参考：
- `templates/activity_plan_template.md` — 策划书模板
- `templates/budget_template.json` — 预算数据结构
- `templates/risk_template.md` — 风险预案模板
- `templates/retrospective_template.md` — 复盘模板
- `references/planning_principles.md` — 策划原则
- `references/common_risks.md` — 常见风险库
- `references/publicity_guidelines.md` — 宣传写作指南
- `rubrics/plan_quality_rubric.json` — 方案质量评分标准

## 可调用的工具

### 必备工具
- `read` / `write` / `edit` — 文件操作
- `glob` / `grep` — 搜索历史方案
- `bash` — 创建目录、运行脚本

### 确定性计算工具（已实现）
- `calculate_budget` — 预算精确计算（单价×数量→小计→分类汇总→备用金→超限判断）
- `build_schedule` — 排期计算（拓扑排序→起止时间→时间窗口检查）
- `validate_project` — 方案完整性校验（检查 brief/plan/budget/schedule/staffing/publicity/outputs）

### 其他工具
- `mcp__publish_markdown` — 如需要发布到公众号

### 相关 Skill
- `wechat-title-generator` — 标题生成
- `wechat-draft-writer` — 初稿写作
- `wechat-publish` — 公众号发布
- `publicity-writing` — 宣传文案（如已安装）

## 注意事项

### 必须做的事
- ✅ 每次数值计算必须调用工具，不要口头计算
- ✅ 发现超预算后必须修改并重新计算
- ✅ 最终方案必须通过 `validate_project` 校验
- ✅ 所有输出文件使用统一格式
- ✅ 标注所有假设条件

### 绝对不能做的事
- ❌ 不要直接返回一段自然语言作为"方案"
- ❌ 不要让模型自己算预算加减法
- ❌ 不要跳过校验步骤直接输出
- ❌ 不要输出格式不一致的文件
- ❌ 不要遗漏复盘模板（活动结束后需要）
- ❌ 不要在活动当天安排同一个人做两件同时进行的事
- ❌ 不要遗漏应急备用金

### 与其他 Skill 的关系
- `wechat-title-generator` → 可用于生成活动名称（非必需）
- `wechat-publish` → 方案确定后如需公众号宣传可调用
- `activity-planning` 是总策划 Skill，其他 Skill 提供专项支持

## 输出格式要求

### brief.json
```json
{
  "event_id": "2026-xxx",
  "title": "活动名称",
  "status": "DRAFT",
  "brief": { ... },
  "assumptions": [ ... ],
  "unknowns": [ ... ]
}
```

### checklist.md 格式
```markdown
## 活动前一周
- [ ] 任务描述
  - 负责人：xxx
  - 截止时间：2026-xx-xx

## 活动当天
- [ ] 任务描述
  - 负责人：xxx
```

### 复盘模板包含
- 目标是否达成
- 参与人数
- 预算偏差
- 流程执行情况
- 参与者反馈
- 突发问题
- 原因分析
- 可保留经验
- 下次改进项
