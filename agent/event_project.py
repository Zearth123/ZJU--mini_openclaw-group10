"""EventProject v1.0 领域模型：由协调器和工具共享的数据结构。"""
from __future__ import annotations

from typing import Any          # 通用类型注解

from pydantic import BaseModel, ConfigDict, Field  # Pydantic 数据验证框架


class ProjectModel(BaseModel):
    """基础项目模型：允许额外字段，便于灵活扩展。"""
    model_config = ConfigDict(extra="allow")


class EventBrief(ProjectModel):
    """活动概要：描述活动的基本信息、约束和假设条件。"""
    activity_type: str = "待确定活动"               # 活动类型
    goal: str = "促进参与者交流"                     # 活动目标
    participants: int = Field(default=1, gt=0)       # 参与人数
    budget_limit: float = Field(default=0, ge=0)     # 预算上限
    duration_minutes: int = Field(default=180, gt=0) # 活动时长（分钟）
    event_start: str = "13:30"                       # 活动开始时间
    event_end: str = "16:30"                         # 活动结束时间
    venue: str = "校内教室"                          # 活动场地
    available_staff: int | None = Field(default=None, gt=0)  # 可用工作人员数
    constraints: list[str] = Field(default_factory=list)     # 约束条件列表
    assumptions: list[str] = Field(default_factory=list)     # 假设条件列表


class PlanStage(ProjectModel):
    """活动流程的一个环节：包含标识、名称、时长、依赖关系和所需人员。"""
    stage_id: str                              # 环节唯一标识
    name: str                                  # 环节名称
    duration_minutes: int = Field(gt=0)        # 环节时长（分钟）
    dependencies: list[str] = Field(default_factory=list)  # 前置依赖的环节 ID 列表
    staff_required: int = Field(default=1, gt=0)           # 该环节所需工作人员数


class EventPlan(ProjectModel):
    """活动方案：包含主题、目标、流程环节、所需资源和成功指标。"""
    theme: str = ""                                            # 活动主题
    objectives: list[str] = Field(default_factory=list)         # 活动目标列表
    stages: list[PlanStage] = Field(default_factory=list)       # 流程环节列表
    required_resources: list[str] = Field(default_factory=list) # 所需资源列表
    success_metrics: list[str] = Field(default_factory=list)    # 成功指标列表


class EventProject(ProjectModel):
    """活动项目聚合根：包含从概要、方案到预算、排期、验证的全量信息。"""
    event_id: str = "event-001"                         # 项目唯一标识
    status: str = "PLANNING"                             # 项目状态：PLANNING / 进行中 / 完成
    brief: EventBrief = Field(default_factory=EventBrief)    # 活动概要信息
    plan: EventPlan = Field(default_factory=EventPlan)       # 活动方案
    budget: dict[str, Any] = Field(default_factory=dict)     # 预算计算结果
    schedule: dict[str, Any] = Field(default_factory=dict)   # 排期计算结果
    tasks: list[dict[str, Any]] = Field(default_factory=list)        # 任务列表
    members: list[dict[str, Any]] = Field(default_factory=list)      # 项目成员
    assignments: list[dict[str, Any]] = Field(default_factory=list)  # 分工指派
    publicity: dict[str, Any] = Field(default_factory=dict)          # 宣传方案
    risks: list[dict[str, Any]] = Field(default_factory=list)        # 风险评估
    validation: dict[str, Any] = Field(                               # 统一校验结果
        default_factory=lambda: {"valid": False, "violations": []}
    )
    outputs: dict[str, dict[str, str]] = Field(default_factory=lambda: {
        "event_project": {"path": "event_project.json"},
        "activity_plan": {"path": "activity_plan.md"},
    })
    actual_results: dict[str, Any] = Field(default_factory=dict)     # 实际执行结果
    retrospective: dict[str, Any] = Field(default_factory=dict)      # 回顾总结
