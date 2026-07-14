"""EventProject v1.0 domain models shared by the coordinator and tools."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class EventBrief(ProjectModel):
    activity_type: str = "待确定活动"
    goal: str = "促进参与者交流"
    participants: int = Field(default=1, gt=0)
    budget_limit: float = Field(default=0, ge=0)
    duration_minutes: int = Field(default=180, gt=0)
    event_start: str = "13:30"
    event_end: str = "16:30"
    venue: str = "校内教室"
    available_staff: int | None = Field(default=None, gt=0)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class PlanStage(ProjectModel):
    stage_id: str
    name: str
    duration_minutes: int = Field(gt=0)
    dependencies: list[str] = Field(default_factory=list)
    staff_required: int = Field(default=1, gt=0)


class EventPlan(ProjectModel):
    theme: str = ""
    objectives: list[str] = Field(default_factory=list)
    stages: list[PlanStage] = Field(default_factory=list)
    required_resources: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)


class EventProject(ProjectModel):
    event_id: str = "event-001"
    status: str = "PLANNING"
    brief: EventBrief = Field(default_factory=EventBrief)
    plan: EventPlan = Field(default_factory=EventPlan)
    budget: dict[str, Any] = Field(default_factory=dict)
    schedule: dict[str, Any] = Field(default_factory=dict)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    members: list[dict[str, Any]] = Field(default_factory=list)
    assignments: list[dict[str, Any]] = Field(default_factory=list)
    publicity: dict[str, Any] = Field(default_factory=dict)
    risks: list[dict[str, Any]] = Field(default_factory=list)
    validation: dict[str, Any] = Field(
        default_factory=lambda: {"valid": False, "violations": []}
    )
    outputs: dict[str, dict[str, str]] = Field(default_factory=lambda: {
        "event_project": {"path": "event_project.json"},
        "activity_plan": {"path": "activity_plan.md"},
    })
    actual_results: dict[str, Any] = Field(default_factory=dict)
    retrospective: dict[str, Any] = Field(default_factory=dict)
